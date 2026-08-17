"""
E4.9.6 — testes de integração contra PostgreSQL real.

Cobrem o que só o banco demonstra: constraints, `UNIQUE` sob
concorrência, a trigger append-only que vale **em SQL bruto**, e o
round trip da migration sem tocar `erasure_records`.
"""

import threading
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa

from app.database import migrations
from app.database.engine import engine
from app.database.health import check_database_health
from app.memory.errors.exceptions import (
    RetentionPolicyImmutableError,
    RetentionPolicyVersionExistsError,
)
from app.memory.models.retention_enums import RetentionScopeKind
from app.memory.models.retention_policy import RetentionPolicy
from app.memory.repositories.retention_policy_repository import RetentionPolicyRepository
from app.memory.schemas.retention import RetentionRule
from app.repositories.unit_of_work import UnitOfWork

D1 = uuid.uuid4()
AGORA = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)


def _available() -> bool:
    return check_database_health().available


pytestmark = pytest.mark.skipif(
    not _available(),
    reason="PostgreSQL real indisponível — E4.9.6 valida constraints e trigger reais.",
)


@pytest.fixture(autouse=True)
def _clean():
    migrations.upgrade("head")
    _truncate()
    yield
    _truncate()


def _truncate() -> None:
    with engine.begin() as conn:
        conn.execute(sa.text("TRUNCATE retention_policies CASCADE"))


def regra(**overrides: object) -> RetentionRule:
    base: dict[str, object] = {
        "rule_id": "ret-001",
        "scope_kind": RetentionScopeKind.ALL_LOCAL_PATRIMONY,
        "minimum_age_days": 30,
    }
    base.update(overrides)
    return RetentionRule(**base)  # type: ignore[arg-type]


def _publicar(**overrides: object) -> uuid.UUID:
    base: dict[str, object] = {
        "policy_key": "ret.default",
        "version": 1,
        "governance_policy_key": "gov.default",
        "rules": (regra(),),
    }
    base.update(overrides)
    with UnitOfWork() as uow:
        pid = RetentionPolicyRepository(uow.session).add_policy(**base).id  # type: ignore[arg-type]
        uow.commit()
    return pid


def _insert_raw(conn, **overrides: object) -> uuid.UUID:
    """Insert por SQL bruto — contorna schema, ORM e repositório."""
    import json

    valores: dict[str, object] = {
        "id": uuid.uuid4(),
        "policy_key": "ret.raw",
        "version": 1,
        "governance_policy_key": "gov.default",
        "rules": json.dumps(RetentionPolicy.serialize_rules((regra(),))),
        "effective_from": None,
        "effective_until": None,
    }
    valores.update(overrides)
    colunas = ", ".join(valores)
    binds = ", ".join(f":{c}" for c in valores)
    conn.execute(sa.text(f"INSERT INTO retention_policies ({colunas}) VALUES ({binds})"), valores)
    return valores["id"]  # type: ignore[return-value]


# --- Schema --------------------------------------------------------------


def test_i01_tabela_e_indice_existem():
    with engine.connect() as conn:
        assert (
            conn.execute(sa.text("SELECT to_regclass('retention_policies')")).scalar() is not None
        )
        indices = set(
            conn.execute(
                sa.text("SELECT indexname FROM pg_indexes WHERE tablename='retention_policies'")
            ).scalars()
        )
    assert "ix_retention_policies_policy_key" in indices
    assert "uq_retention_policies_key_version" in indices


def test_i02_nenhuma_foreign_key():
    """Referências a governança e domínio são declarativas."""
    with engine.connect() as conn:
        fks = (
            conn.execute(
                sa.text(
                    "SELECT conname FROM pg_constraint "
                    "WHERE conrelid='retention_policies'::regclass AND contype='f'"
                )
            )
            .scalars()
            .all()
        )
    assert fks == []


def test_i03_migration_head_e_down_revision():
    assert migrations.head_revision() == "c8a3f5017e94"
    assert migrations.current_revision() == "c8a3f5017e94"


# --- Publicação e consulta ----------------------------------------------


def test_i04_publica_e_le_regras_tipadas():
    pid = _publicar()
    with UnitOfWork() as uow:
        lida = RetentionPolicyRepository(uow.session).get_by_id(pid)
        assert lida is not None
        assert lida.typed_rules[0].minimum_age_days == 30
        assert lida.typed_rules[0].scope_kind is RetentionScopeKind.ALL_LOCAL_PATRIMONY


def test_i05_versao_duplicada_traduzida_por_sinal_do_driver():
    _publicar()
    with pytest.raises(RetentionPolicyVersionExistsError) as info, UnitOfWork() as uow:
        RetentionPolicyRepository(uow.session).add_policy(
            policy_key="ret.default",
            version=1,
            governance_policy_key="gov.default",
            rules=(regra(),),
        )
    assert info.value.version == 1


def test_i06_corrida_de_duas_sessoes_so_permite_uma():
    """A constraint é a única coisa que vale sob concorrência real."""
    erros: list[Exception] = []
    ok: list[uuid.UUID] = []

    def publicar() -> None:
        try:
            with UnitOfWork() as uow:
                pid = (
                    RetentionPolicyRepository(uow.session)
                    .add_policy(
                        policy_key="ret.race",
                        version=1,
                        governance_policy_key="gov.default",
                        rules=(regra(),),
                    )
                    .id
                )
                uow.commit()
                ok.append(pid)
        except Exception as exc:  # noqa: BLE001 - o teste classifica depois
            erros.append(exc)

    threads = [threading.Thread(target=publicar) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(ok) == 1
    assert len(erros) == 1
    with engine.connect() as conn:
        total = conn.execute(
            sa.text("SELECT count(*) FROM retention_policies WHERE policy_key='ret.race'")
        ).scalar()
    assert total == 1


def test_i07_max_version_e_list_versions():
    _publicar(version=1)
    _publicar(version=2)
    with UnitOfWork() as uow:
        repo = RetentionPolicyRepository(uow.session)
        assert repo.max_version("ret.default") == 2
        assert [p.version for p in repo.list_versions("ret.default")] == [1, 2]
        assert repo.max_version("inexistente") == 0
        assert repo.get_version("ret.default", 9) is None


def test_i08_versao_vigente_respeita_janela_com_fim_exclusivo():
    """Fim exclusivo: no instante da virada, só a nova vale."""
    virada = AGORA + timedelta(days=10)
    _publicar(version=1, effective_from=AGORA, effective_until=virada)
    _publicar(version=2, effective_from=virada)

    with UnitOfWork() as uow:
        repo = RetentionPolicyRepository(uow.session)
        assert repo.effective_version_at("ret.default", AGORA).version == 1
        assert repo.effective_version_at("ret.default", virada).version == 2
        assert repo.effective_version_at("ret.default", AGORA - timedelta(days=1)) is None


def test_i09_versao_vigente_desempata_pela_maior():
    """Janelas sobrepostas continuam possíveis; a resposta é determinística."""
    _publicar(version=1, effective_from=AGORA)
    _publicar(version=2, effective_from=AGORA)
    with UnitOfWork() as uow:
        vigente = RetentionPolicyRepository(uow.session).effective_version_at(
            "ret.default", AGORA + timedelta(days=1)
        )
        assert vigente is not None
        assert vigente.version == 2


# --- Imutabilidade: três camadas ----------------------------------------


def test_i10_trigger_existe():
    with engine.connect() as conn:
        gatilhos = (
            conn.execute(
                sa.text(
                    "SELECT tgname FROM pg_trigger "
                    "WHERE tgrelid='retention_policies'::regclass AND NOT tgisinternal"
                )
            )
            .scalars()
            .all()
        )
    assert gatilhos == ["trg_retention_policies_append_only"]


def test_i11_update_bruto_bloqueado():
    _publicar()
    with pytest.raises(sa.exc.DatabaseError) as info, engine.begin() as conn:
        conn.execute(sa.text("UPDATE retention_policies SET version = 99"))
    assert "append-only" in str(info.value)


def test_i12_delete_bruto_bloqueado():
    _publicar()
    with pytest.raises(sa.exc.DatabaseError) as info, engine.begin() as conn:
        conn.execute(sa.text("DELETE FROM retention_policies"))
    assert "append-only" in str(info.value)
    with engine.connect() as conn:
        assert conn.execute(sa.text("SELECT count(*) FROM retention_policies")).scalar() == 1


def test_i13_insert_bruto_permitido():
    with engine.begin() as conn:
        _insert_raw(conn)
    with engine.connect() as conn:
        assert conn.execute(sa.text("SELECT count(*) FROM retention_policies")).scalar() == 1


def test_i14_mutacao_por_fora_do_repositorio_e_pega_pelo_mapper():
    """Carregar, mutar e dar commit contorna o repositório (E4.3.1)."""
    pid = _publicar()
    with pytest.raises(RetentionPolicyImmutableError), UnitOfWork() as uow:
        alvo = uow.session.get(RetentionPolicy, pid)
        assert alvo is not None
        alvo.version = 7
        uow.session.flush()


def test_i15_delete_pela_sessao_e_pego_pelo_mapper():
    pid = _publicar()
    with pytest.raises(RetentionPolicyImmutableError), UnitOfWork() as uow:
        alvo = uow.session.get(RetentionPolicy, pid)
        assert alvo is not None
        uow.session.delete(alvo)
        uow.session.flush()


def test_i16_repositorio_recusa_update_e_delete():
    pid = _publicar()
    with UnitOfWork() as uow:
        repo = RetentionPolicyRepository(uow.session)
        alvo = repo.get_by_id(pid)
        assert alvo is not None
        with pytest.raises(RetentionPolicyImmutableError):
            repo.update(alvo)
        with pytest.raises(RetentionPolicyImmutableError):
            repo.delete(alvo)


# --- Constraints por SQL bruto ------------------------------------------


@pytest.mark.parametrize(
    ("overrides", "constraint"),
    [
        ({"version": 0}, "version_positive"),
        ({"policy_key": "   "}, "policy_key_not_blank"),
        ({"governance_policy_key": ""}, "governance_key_not_blank"),
        (
            {"effective_from": AGORA, "effective_until": AGORA - timedelta(days=1)},
            "effective_window",
        ),
    ],
)
def test_i17_constraints_rejeitam_em_sql_bruto(overrides, constraint):
    with pytest.raises(sa.exc.IntegrityError) as info, engine.begin() as conn:
        _insert_raw(conn, **overrides)
    assert constraint in str(info.value)


def test_i18_unique_vale_em_sql_bruto():
    with engine.begin() as conn:
        _insert_raw(conn, policy_key="ret.x", version=1)
    with pytest.raises(sa.exc.IntegrityError) as info, engine.begin() as conn:
        _insert_raw(conn, policy_key="ret.x", version=1)
    assert "uq_retention_policies_key_version" in str(info.value)


def test_i19_rules_nao_pode_ser_nulo_no_banco():
    with pytest.raises(sa.exc.IntegrityError), engine.begin() as conn:
        _insert_raw(conn, rules=None)


def test_i20_limite_declarado_o_banco_nao_verifica_a_forma_das_regras():
    """Honestidade sobre o alcance real da constraint.

    O banco garante que `rules` é JSON válido e não nulo. A **forma**
    das regras é garantia do tipo, na serialização — e um INSERT bruto
    com JSON estruturalmente válido mas semanticamente inválido entra.
    A desserialização tipada é quem o recusa depois.

    Documentar isso é melhor do que afirmar uma constraint que o banco
    não tem.
    """
    import json

    with engine.begin() as conn:
        _insert_raw(conn, policy_key="ret.bruta", rules=json.dumps([{"lixo": True}]))

    with UnitOfWork() as uow:
        lida = RetentionPolicyRepository(uow.session).get_version("ret.bruta", 1)
        assert lida is not None
        with pytest.raises(KeyError):
            _ = lida.typed_rules


# --- Round trip da migration --------------------------------------------


def test_i21_round_trip_sem_tocar_erasure_records():
    migrations.upgrade("head")
    with engine.connect() as conn:
        assert conn.execute(sa.text("SELECT to_regclass('erasure_records')")).scalar() is not None

    migrations.downgrade("-1")
    with engine.connect() as conn:
        assert conn.execute(sa.text("SELECT to_regclass('retention_policies')")).scalar() is None
        orfas = (
            conn.execute(
                sa.text(
                    "SELECT proname FROM pg_proc WHERE proname='reject_retention_policy_mutation'"
                )
            )
            .scalars()
            .all()
        )
        assert orfas == [], "função órfã após downgrade"
        # A fatia anterior permanece intacta.
        assert conn.execute(sa.text("SELECT to_regclass('erasure_records')")).scalar() is not None
        assert conn.execute(
            sa.text("SELECT proname FROM pg_proc WHERE proname='reject_erasure_record_mutation'")
        ).scalars().all() == ["reject_erasure_record_mutation"]

    migrations.upgrade("head")
    with engine.connect() as conn:
        assert (
            conn.execute(sa.text("SELECT to_regclass('retention_policies')")).scalar() is not None
        )
        gatilhos = (
            conn.execute(
                sa.text(
                    "SELECT tgname FROM pg_trigger "
                    "WHERE tgrelid='retention_policies'::regclass AND NOT tgisinternal"
                )
            )
            .scalars()
            .all()
        )
        assert gatilhos == ["trg_retention_policies_append_only"]


def test_i22_nenhum_erasure_record_criado_por_esta_fatia():
    """Publicar policy não produz recibo — nem poderia."""
    _publicar()
    with engine.connect() as conn:
        assert conn.execute(sa.text("SELECT count(*) FROM erasure_records")).scalar() == 0
