"""
E4.9.6 — testes de integração contra PostgreSQL real.

Cobrem o que só o banco demonstra: constraints, `UNIQUE` sob
concorrência, a trigger append-only que vale **em SQL bruto**, e o
round trip da migration sem tocar `erasure_records`.
"""

import threading
import uuid
from collections.abc import Callable
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


def _chamar(alvo: object, metodo: str, **kwargs: object) -> object:
    """Chamada dinâmica para entradas deliberadamente inválidas (`E4.9.6.3`).

    Uma função obtida por `getattr` não tem assinatura conhecida, então o
    argumento inválido é expresso sem `# type: ignore`.
    """
    funcao: Callable[..., object] = getattr(alvo, metodo)
    return funcao(**kwargs)


def _atribuir_campo(alvo: object, campo: str, valor: object) -> None:
    """`setattr` com o nome em variável: sem supressão e sem reescrita do ruff."""
    setattr(alvo, campo, valor)


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
    assert migrations.head_revision() == "a7f31c05be24"
    assert migrations.current_revision() == "a7f31c05be24"


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
    das regras é garantia do tipo — e um INSERT bruto com JSON
    estruturalmente válido mas semanticamente inválido entra. A
    reconstrução tipada é quem o recusa.

    Atualizado pela E4.9.6.1: a recusa passou a ocorrer **na própria
    leitura**, dentro de `RetentionRulesType.process_result_value`, e
    não mais só quando alguém pedisse `typed_rules`. A linha inválida
    deixou de ser observável como objeto — que é mais estrito, não
    menos.

    Atualizado pela E4.9.6.2: a recusa continua na carga, mas o erro
    passou de `KeyError` — incidental, vindo do acesso à chave — para
    `ValueError` do contrato, que diz **quais** chaves faltam. A
    auditoria da cadeia 77 exigiu erro controlado em toda fronteira, e
    `KeyError` não é nem `TypeError` nem `ValueError`.
    """
    import json

    with engine.begin() as conn:
        _insert_raw(conn, policy_key="ret.bruta", rules=json.dumps([{"lixo": True}]))

    with pytest.raises(ValueError, match="chaves obrigatórias"), UnitOfWork() as uow:
        RetentionPolicyRepository(uow.session).get_version("ret.bruta", 1)


# --- Round trip da migration --------------------------------------------


def test_i21_round_trip_sem_tocar_erasure_records():
    # ATUALIZADO PELA E4.9.9.a: alvo EXPLÍCITO em vez de `-1`. Com o head
    # em `a1f7c2d40e93`, um passo relativo removeria as tabelas de
    # aprovação e não as de retenção, que é o que este teste mede.
    migrations.upgrade("head")
    with engine.connect() as conn:
        assert conn.execute(sa.text("SELECT to_regclass('erasure_records')")).scalar() is not None

    migrations.downgrade("9d4f1a7c2be8")
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


# ======================================================================
# E4.9.6.1 — corretivo, contra PostgreSQL real
# ======================================================================


def test_i23_chave_com_controle_recusada_antes_do_banco():
    """Achado A1: a fronteira tipada recusa antes de chegar à persistência."""
    with pytest.raises(ValueError, match="caracteres de controle"), UnitOfWork() as uow:
        RetentionPolicyRepository(uow.session).add_policy(
            policy_key="ret\nembedded",
            version=1,
            governance_policy_key="gov\tkey",
            rules=(regra(),),
        )

    with engine.connect() as conn:
        assert conn.execute(sa.text("SELECT count(*) FROM retention_policies")).scalar() == 0


def test_i24_leitura_de_policy_commitada_e_profundamente_imutavel():
    """Achado A2, no caminho real: publicar, commitar, reler, tentar mutar."""
    pid = _publicar()

    with UnitOfWork() as uow:
        lida = RetentionPolicyRepository(uow.session).get_by_id(pid)
        assert lida is not None
        assert isinstance(lida.rules, tuple)
        antes = lida.rules[0].minimum_age_days

        with pytest.raises(TypeError):
            lida.rules[0]["minimum_age_days"] = 0  # type: ignore[index]
        with pytest.raises(TypeError):
            lida.rules[0] = regra(rule_id="outra")  # type: ignore[index]

        assert lida.rules[0].minimum_age_days == antes


def test_i25_duas_leituras_na_mesma_sessao_nao_divergem():
    """A superfície pública não pode divergir do banco dentro da sessão.

    Era o risco real do A2: hoje não há avaliador; amanhã, um avaliador
    na mesma sessão poderia ler uma policy diferente da persistida.
    """
    pid = _publicar()

    with UnitOfWork() as uow:
        repo = RetentionPolicyRepository(uow.session)
        primeira = repo.get_by_id(pid)
        assert primeira is not None
        with pytest.raises(TypeError):
            primeira.rules[0]["minimum_age_days"] = 0  # type: ignore[index]

        segunda = repo.get_version("ret.default", 1)
        assert segunda is not None
        assert segunda.rules[0].minimum_age_days == 30
        assert primeira.rules[0].minimum_age_days == 30


def test_i26_nova_sessao_ve_os_bytes_persistidos_originais():
    pid = _publicar()
    with UnitOfWork() as uow:
        lida = RetentionPolicyRepository(uow.session).get_by_id(pid)
        assert lida is not None

    with engine.connect() as conn:
        bruto = conn.execute(
            sa.text("SELECT rules FROM retention_policies WHERE id = :i"), {"i": pid}
        ).scalar_one()
    assert bruto[0]["minimum_age_days"] == 30
    assert bruto[0]["rule_id"] == "ret-001"


def test_i27_metodos_herdados_nao_dao_escape_mutavel():
    """`get_by_id`, `get_by_id_or_raise`, `list`, `paginate`, `refresh`.

    O congelamento vive na fronteira do ORM, então **todo** método
    herdado de `BaseRepository` devolve a estrutura já imutável — sem
    que nenhuma assinatura precisasse mudar.
    """
    pid = _publicar()

    with UnitOfWork() as uow:
        repo = RetentionPolicyRepository(uow.session)
        superficies = [
            repo.get_by_id(pid),
            repo.get_by_id_or_raise(pid),
            repo.list()[0],
            repo.paginate(page=1, page_size=10).items[0],
            repo.refresh(repo.get_by_id_or_raise(pid)),
            repo.get_version("ret.default", 1),
            repo.list_versions("ret.default")[0],
            repo.effective_version_at("ret.default", AGORA),
        ]
        for superficie in superficies:
            assert superficie is not None
            assert isinstance(superficie.rules, tuple)
            with pytest.raises(TypeError):
                superficie.rules[0]["minimum_age_days"] = 0  # type: ignore[index]


def test_i28_publicacao_devolve_superficie_imutavel_e_preserva_id():
    """A escrita também não devolve superfície mutável (§4.3)."""
    with UnitOfWork() as uow:
        gravada = RetentionPolicyRepository(uow.session).add_policy(
            policy_key="ret.escrita",
            version=1,
            governance_policy_key="gov.default",
            rules=(regra(),),
        )
        assert gravada.id is not None
        assert isinstance(gravada.rules, tuple)
        with pytest.raises(TypeError):
            gravada.rules[0]["minimum_age_days"] = 0  # type: ignore[index]
        uow.commit()


def test_i29_migration_head_e_schema_identicos_a_cadeia_76():
    """`MIGRATION_DELTA = 0`, `DATABASE_SCHEMA_DELTA = 0`."""
    assert migrations.head_revision() == "a7f31c05be24"

    with engine.connect() as conn:
        tipo = conn.execute(
            sa.text(
                "SELECT data_type FROM information_schema.columns "
                "WHERE table_name='retention_policies' AND column_name='rules'"
            )
        ).scalar()
        checks = conn.execute(
            sa.text(
                "SELECT count(*) FROM pg_constraint "
                "WHERE conrelid='retention_policies'::regclass AND contype='c'"
            )
        ).scalar()
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
    assert tipo == "jsonb"
    assert checks == 4
    assert gatilhos == ["trg_retention_policies_append_only"]


def test_i30_trigger_e_colisao_de_versao_seguem_valendo():
    """O corretivo não afrouxou nada da cadeia 76."""
    _publicar()

    with pytest.raises(RetentionPolicyVersionExistsError), UnitOfWork() as uow:
        RetentionPolicyRepository(uow.session).add_policy(
            policy_key="ret.default",
            version=1,
            governance_policy_key="gov.default",
            rules=(regra(),),
        )

    with pytest.raises(sa.exc.DatabaseError) as info, engine.begin() as conn:
        conn.execute(sa.text("UPDATE retention_policies SET version = 99"))
    assert "append-only" in str(info.value)


# ======================================================================
# E4.9.6.2 — completude de fronteira contra PostgreSQL real
# ======================================================================


def test_i31_publicar_commitar_e_reler_devolve_a_forma_tipada():
    """Fronteira 5: o repositório, ponta a ponta."""
    _publicar(policy_key="ret.tipada")

    with UnitOfWork() as uow:
        lida = RetentionPolicyRepository(uow.session).get_version("ret.tipada", 1)
        assert lida is not None
        assert isinstance(lida.rules, tuple)
        assert isinstance(lida.rules[0], RetentionRule)
        assert isinstance(lida.rules[0].domain_ids, frozenset)
        assert lida.typed_rules is lida.rules


def test_i32_os_sete_metodos_herdados_devolvem_a_forma_tipada():
    """Nenhum escape herdado de `BaseRepository` devolve JSON cru."""
    pid = _publicar(policy_key="ret.herdados")

    with UnitOfWork() as uow:
        repo = RetentionPolicyRepository(uow.session)
        observados = [
            repo.get_by_id(pid),
            repo.get_by_id_or_raise(pid),
            *repo.list(),
            *repo.paginate(page=1, page_size=10).items,
            *repo.list_versions("ret.herdados"),
            repo.effective_version_at("ret.herdados", AGORA),
        ]
        for entidade in observados:
            assert entidade is not None
            assert isinstance(entidade.rules, tuple), type(entidade.rules)
            assert all(isinstance(r, RetentionRule) for r in entidade.rules)


def test_i33_nova_sessao_observa_os_bytes_originais_apos_tentativa_de_mutacao():
    """A tentativa é recusada em memória e nada muda no disco.

    Atualizado pela E4.9.6.3: numa instância **carregada** a recusa
    agora é de autoridade, não de forma. `has_identity` é verdadeiro,
    então qualquer reatribuição para — inclusive uma tupla válida — e o
    erro é `ValueError`, não mais o `TypeError` de forma.
    """
    _publicar(policy_key="ret.imutavel")

    with UnitOfWork() as uow:
        lida = RetentionPolicyRepository(uow.session).get_version("ret.imutavel", 1)
        assert lida is not None
        antes = lida.rules
        with pytest.raises(ValueError, match="não pode ser reatribuída"):
            _atribuir_campo(lida, "rules", [{"rule_id": "r1"}])
        with pytest.raises(ValueError, match="não pode ser reatribuída"):
            lida.rules = (regra(rule_id="outra"),)
        assert lida.rules is antes

    with engine.connect() as conn:
        bruto = conn.execute(
            sa.text("SELECT rules FROM retention_policies WHERE policy_key = 'ret.imutavel'")
        ).scalar_one()
    assert bruto == RetentionPolicy.serialize_rules((regra(),))

    with UnitOfWork() as uow:
        relida = RetentionPolicyRepository(uow.session).get_version("ret.imutavel", 1)
        assert relida is not None
        assert relida.rules[0].minimum_age_days == 30


def test_i34_duas_leituras_na_mesma_sessao_nao_divergem():
    _publicar(policy_key="ret.coerente")

    with UnitOfWork() as uow:
        repo = RetentionPolicyRepository(uow.session)
        primeira = repo.get_version("ret.coerente", 1)
        assert primeira is not None
        with pytest.raises((TypeError, ValueError)):
            primeira.rules = ()
        segunda = repo.get_version("ret.coerente", 1)
        assert segunda is not None
        assert primeira.rules == segunda.rules


def test_i35_publicacao_com_representacao_nao_tipada_e_recusada_antes_do_banco():
    """Nada chega ao INSERT — a recusa é de contrato, não da constraint."""
    with pytest.raises(TypeError), UnitOfWork() as uow:
        _chamar(
            RetentionPolicyRepository(uow.session),
            "add_policy",
            policy_key="ret.naotipada",
            version=1,
            governance_policy_key="gov.default",
            rules=[{"rule_id": "r1"}],
        )

    with engine.connect() as conn:
        total = conn.execute(
            sa.text("SELECT count(*) FROM retention_policies WHERE policy_key = 'ret.naotipada'")
        ).scalar_one()
    assert total == 0


@pytest.mark.parametrize("invisivel", ["\u0085", "\u200b", "\u2028", "\u2029", "\u202e"])
def test_i36_invisiveis_unicode_nao_chegam_ao_banco(invisivel):
    chave = f"ret{invisivel}oculta"
    with pytest.raises(ValueError), UnitOfWork() as uow:
        RetentionPolicyRepository(uow.session).add_policy(
            policy_key=chave,
            version=1,
            governance_policy_key="gov.default",
            rules=(regra(),),
        )

    with engine.connect() as conn:
        total = conn.execute(sa.text("SELECT count(*) FROM retention_policies")).scalar_one()
    assert total == 0


def test_i37_chave_acentuada_persiste_byte_a_byte():
    """`VALIDATED OPAQUE KEY != NORMALIZED KEY` — provado no disco."""
    chave = "retenção.produção.São_Paulo"
    _publicar(policy_key=chave)

    with engine.connect() as conn:
        persistida = conn.execute(sa.text("SELECT policy_key FROM retention_policies")).scalar_one()
    assert persistida == chave
    assert persistida.encode("utf-8") == chave.encode("utf-8")


def test_i38_trigger_e_colisao_de_versao_continuam_valendo():
    """Nada do que a E4.9.6 garantiu foi relaxado pelo corretivo."""
    _publicar(policy_key="ret.guardas")

    with pytest.raises(RetentionPolicyVersionExistsError):
        _publicar(policy_key="ret.guardas")

    with pytest.raises(sa.exc.DatabaseError) as capturado, engine.begin() as conn:
        conn.execute(
            sa.text("UPDATE retention_policies SET version = 9 WHERE policy_key = 'ret.guardas'")
        )
    assert "append-only" in str(capturado.value)

    with pytest.raises(sa.exc.DatabaseError) as removido, engine.begin() as conn:
        conn.execute(sa.text("DELETE FROM retention_policies WHERE policy_key = 'ret.guardas'"))
    assert "append-only" in str(removido.value)


def test_i39_schema_e_migration_head_identicos_a_cadeia_77():
    """`MIGRATION_DELTA = 0` e `DATABASE_SCHEMA_DELTA = 0`."""
    with engine.connect() as conn:
        head = conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one()
        assert head == "a7f31c05be24"

        tipo = conn.execute(
            sa.text(
                "SELECT data_type FROM information_schema.columns "
                "WHERE table_name = 'retention_policies' AND column_name = 'rules'"
            )
        ).scalar_one()
        assert tipo == "jsonb"

        checks = conn.execute(
            sa.text(
                "SELECT count(*) FROM information_schema.table_constraints "
                "WHERE table_name = 'retention_policies' AND constraint_type = 'CHECK' "
                "AND constraint_name LIKE 'ck_%'"
            )
        ).scalar_one()
        assert checks == 4

        gatilho = conn.execute(
            sa.text(
                "SELECT count(*) FROM information_schema.triggers "
                "WHERE event_object_table = 'retention_policies' "
                "AND trigger_name = 'trg_retention_policies_append_only'"
            )
        ).scalar_one()
        assert gatilho >= 1


def test_i40_erasure_records_permanece_intacta():
    with engine.connect() as conn:
        assert conn.execute(sa.text("SELECT to_regclass('erasure_records')")).scalar() is not None


# ======================================================================
# E4.9.6.3 — fronteiras de atribuição e de result, contra PostgreSQL real
# ======================================================================


def test_i41_reatribuicao_valida_recusada_em_instancia_persistida():
    """`VALID_TUPLE != AUTHORITY_TO_REWRITE_PUBLISHED_POLICY`."""
    _publicar(policy_key="ret.reatrib")

    with UnitOfWork() as uow:
        lida = RetentionPolicyRepository(uow.session).get_version("ret.reatrib", 1)
        assert lida is not None
        anterior = lida.rules
        with pytest.raises(ValueError, match="não pode ser reatribuída"):
            lida.rules = (regra(rule_id="nova"),)
        assert lida.rules is anterior
        assert lida.rules[0].rule_id == "ret-001"


def test_i42_instancia_expirada_nao_abre_escape_de_reatribuicao():
    """O escape que o §11.5 do prompt manda evitar.

    Depois de `expire()`, `rules` some do `__dict__`. Um mecanismo que
    olhasse só o `__dict__` trataria a próxima atribuição como primeira
    inicialização e aceitaria a substituição.
    """
    _publicar(policy_key="ret.expirada")

    with UnitOfWork() as uow:
        repo = RetentionPolicyRepository(uow.session)
        lida = repo.get_version("ret.expirada", 1)
        assert lida is not None

        uow.session.expire(lida)
        assert "rules" not in lida.__dict__

        with pytest.raises(ValueError, match="não pode ser reatribuída"):
            lida.rules = (regra(rule_id="nova"),)

        # A leitura seguinte recarrega do banco e traz o valor original.
        assert lida.rules[0].rule_id == "ret-001"
        assert isinstance(lida.rules, tuple)


def test_i43_refresh_e_carregamento_continuam_funcionais():
    """A recusa é do evento de atributo; o loading não passa por ele."""
    _publicar(policy_key="ret.refresh")

    with UnitOfWork() as uow:
        repo = RetentionPolicyRepository(uow.session)
        lida = repo.get_version("ret.refresh", 1)
        assert lida is not None
        uow.session.refresh(lida)
        assert isinstance(lida.rules, tuple)
        assert isinstance(lida.rules[0], RetentionRule)
        assert lida.rules[0].rule_id == "ret-001"


def test_i44_duas_leituras_na_mesma_sessao_veem_o_valor_persistido():
    _publicar(policy_key="ret.duasleituras")

    with UnitOfWork() as uow:
        repo = RetentionPolicyRepository(uow.session)
        primeira = repo.get_version("ret.duasleituras", 1)
        assert primeira is not None
        with pytest.raises(ValueError):
            primeira.rules = (regra(rule_id="nova"),)
        segunda = repo.get_version("ret.duasleituras", 1)
        assert segunda is not None
        assert primeira.rules == segunda.rules
        assert segunda.rules[0].rule_id == "ret-001"


def test_i45_domain_ids_objeto_gravado_por_sql_bruto_recusado_na_carga():
    """A reprodução do A4b, do disco para dentro.

    ```text
    JSON ITERABLE != CANONICAL JSON ARRAY
    ```
    """
    import json

    payload = [
        {
            "rule_id": "r1",
            "scope_kind": "memory_domain_set",
            "domain_ids": {str(D1): "valor ignorado"},
            "anchor": "created_at",
            "minimum_age_days": 30,
            "on_expiry_action": "assess_and_inform",
        }
    ]
    with engine.begin() as conn:
        _insert_raw(conn, policy_key="ret.objeto", rules=json.dumps(payload))

    with pytest.raises(TypeError, match="lista JSON"), UnitOfWork() as uow:
        RetentionPolicyRepository(uow.session).get_version("ret.objeto", 1)


@pytest.mark.parametrize(
    ("nome", "regra_json"),
    [
        ("rule_id_lista", {"rule_id": []}),
        ("idade_bool", {"minimum_age_days": True}),
        ("dominio_nao_uuid", {"scope_kind": "memory_domain_set", "domain_ids": ["x"]}),
        ("dominio_string", {"domain_ids": "nao"}),
    ],
)
def test_i46_forma_invalida_gravada_por_sql_bruto_recusada_na_carga(nome, regra_json):
    """Erro sempre de contrato — nunca `KeyError` nem `unhashable`."""
    import json

    canonico = {
        "rule_id": "r1",
        "scope_kind": "all_local_patrimony",
        "domain_ids": [],
        "anchor": "created_at",
        "minimum_age_days": 30,
        "on_expiry_action": "assess_and_inform",
    }
    with engine.begin() as conn:
        _insert_raw(conn, policy_key=f"ret.{nome}", rules=json.dumps([{**canonico, **regra_json}]))

    with pytest.raises((TypeError, ValueError)) as capturado, UnitOfWork() as uow:
        RetentionPolicyRepository(uow.session).get_version(f"ret.{nome}", 1)
    assert not isinstance(capturado.value, KeyError | AttributeError)


def test_i47_nova_sessao_ve_os_bytes_originais_apos_tentativa_de_reatribuicao():
    _publicar(policy_key="ret.bytes")

    with UnitOfWork() as uow:
        lida = RetentionPolicyRepository(uow.session).get_version("ret.bytes", 1)
        assert lida is not None
        with pytest.raises(ValueError):
            lida.rules = (regra(rule_id="nova"),)

    with engine.connect() as conn:
        bruto = conn.execute(
            sa.text("SELECT rules FROM retention_policies WHERE policy_key = 'ret.bytes'")
        ).scalar_one()
    assert bruto == RetentionPolicy.serialize_rules((regra(),))


def test_i48_trigger_colisao_e_schema_permanecem_inalterados():
    _publicar(policy_key="ret.inalterado")

    with pytest.raises(RetentionPolicyVersionExistsError):
        _publicar(policy_key="ret.inalterado")

    with pytest.raises(sa.exc.DatabaseError) as atualizado, engine.begin() as conn:
        conn.execute(
            sa.text("UPDATE retention_policies SET version = 9 WHERE policy_key = 'ret.inalterado'")
        )
    assert "append-only" in str(atualizado.value)

    with engine.connect() as conn:
        assert conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one() == (
            "a7f31c05be24"
        )
        assert (
            conn.execute(
                sa.text(
                    "SELECT data_type FROM information_schema.columns "
                    "WHERE table_name = 'retention_policies' AND column_name = 'rules'"
                )
            ).scalar_one()
            == "jsonb"
        )
