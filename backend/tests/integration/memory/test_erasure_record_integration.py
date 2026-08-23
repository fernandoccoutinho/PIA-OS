"""
E4.9.5 — testes de integração contra PostgreSQL real.

Cobrem o que só o banco pode demonstrar: as onze constraints, a
trigger append-only que vale **em SQL bruto**, o round trip da
migration e a ausência de qualquer FK que pudesse destruir o recibo
junto com o sujeito.

A trigger é a razão principal deste arquivo. As camadas ORM e
repositório já são cobertas pelos unitários; a terceira camada só
existe no PostgreSQL, e é a única que continua valendo quando alguém
escreve por fora da aplicação.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa

from app.database import migrations
from app.database.engine import engine
from app.database.health import check_database_health
from app.memory.errors.exceptions import ErasureRecordImmutableError
from app.memory.models.erasure_enums import ErasureOutcome, ErasureTargetClass
from app.memory.models.erasure_record import ErasureRecord
from app.memory.repositories.erasure_record_repository import ErasureRecordRepository
from app.memory.schemas.erasure_record import ErasureRecordAppend
from app.repositories.unit_of_work import UnitOfWork

ATTEMPTED = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)
COMPLETED = ATTEMPTED + timedelta(seconds=5)


def _available() -> bool:
    return check_database_health().available


pytestmark = pytest.mark.skipif(
    not _available(),
    reason="PostgreSQL real indisponível — E4.9.5 valida constraints e trigger reais.",
)


@pytest.fixture(autouse=True)
def _clean():
    migrations.upgrade("head")
    _truncate()
    yield
    _truncate()


def _truncate() -> None:
    with engine.begin() as conn:
        conn.execute(sa.text("TRUNCATE erasure_records CASCADE"))


def entrada(**overrides: object) -> ErasureRecordAppend:
    base: dict[str, object] = {
        "subject_identifier": "coid:9f1c",
        "target_class": ErasureTargetClass.PIA_MANAGED_ARTIFACT,
        "scope_token": "scope:controlled-copies-v1",
        "outcome": ErasureOutcome.SUCCEEDED,
        "governance_policy_id": uuid.uuid4(),
        "governance_policy_key": "gov.erasure",
        "governance_policy_version": 3,
        "governance_rule_id": "rule-1",
        "governance_resolution_ref": "res:7c2a",
        "approval_ref": "appr:2b19",
        "executor_ref": "exec:local-artifact-store",
        "attempted_at": ATTEMPTED,
        "completed_at": COMPLETED,
    }
    base.update(overrides)
    return ErasureRecordAppend(**base)  # type: ignore[arg-type]


def _insert_raw(conn, **overrides: object) -> uuid.UUID:
    """Insert por SQL bruto — contorna schema, ORM e repositório."""
    valores: dict[str, object] = {
        "id": uuid.uuid4(),
        "subject_identifier": "coid:raw",
        "target_class": "pia_managed_artifact",
        "scope_token": "scope:raw",
        "outcome": "succeeded",
        "retention_policy_id": None,
        "retention_policy_key": None,
        "retention_policy_version": None,
        "governance_policy_id": uuid.uuid4(),
        "governance_policy_key": "gov.erasure",
        "governance_policy_version": 1,
        "governance_rule_id": "rule-raw",
        "governance_resolution_ref": "res:raw",
        "approval_ref": "appr:raw",
        "executor_ref": "exec:raw",
        "attempted_at": ATTEMPTED,
        "completed_at": COMPLETED,
        "failure_code": None,
    }
    valores.update(overrides)
    colunas = ", ".join(valores)
    binds = ", ".join(f":{c}" for c in valores)
    conn.execute(sa.text(f"INSERT INTO erasure_records ({colunas}) VALUES ({binds})"), valores)
    return valores["id"]  # type: ignore[return-value]


# --- Schema --------------------------------------------------------------


def test_i01_tabela_existe_apos_upgrade():
    with engine.connect() as conn:
        assert conn.execute(sa.text("SELECT to_regclass('erasure_records')")).scalar() is not None


def test_i02_nenhuma_foreign_key():
    """`SUBJECT_LINK = HISTORICAL_IDENTIFIER_NOT_FK`.

    Uma FK faria o recibo depender da sobrevivência do sujeito: ou
    sumiria junto com o que registra, ou impediria a própria operação
    que registra.
    """
    with engine.connect() as conn:
        fks = (
            conn.execute(
                sa.text(
                    "SELECT conname FROM pg_constraint "
                    "WHERE conrelid = 'erasure_records'::regclass AND contype = 'f'"
                )
            )
            .scalars()
            .all()
        )
    assert fks == []


def test_i03_indices_essenciais_existem():
    with engine.connect() as conn:
        indices = set(
            conn.execute(
                sa.text("SELECT indexname FROM pg_indexes WHERE tablename = 'erasure_records'")
            ).scalars()
        )
    assert {
        "ix_erasure_records_subject_identifier",
        "ix_erasure_records_outcome",
        "ix_erasure_records_approval_ref",
        "ix_erasure_records_attempted_at_id",
    } <= indices


def test_i04_completed_at_e_not_null_no_banco():
    with engine.connect() as conn:
        nullable = conn.execute(
            sa.text(
                "SELECT is_nullable FROM information_schema.columns "
                "WHERE table_name = 'erasure_records' AND column_name = 'completed_at'"
            )
        ).scalar()
    assert nullable == "NO"


def test_i05_timestamps_sao_timezone_aware_no_banco():
    with engine.connect() as conn:
        tipos = dict(
            conn.execute(
                sa.text(
                    "SELECT column_name, data_type FROM information_schema.columns "
                    "WHERE table_name = 'erasure_records' "
                    "AND column_name IN ('attempted_at', 'completed_at')"
                )
            ).all()
        )
    assert tipos == {
        "attempted_at": "timestamp with time zone",
        "completed_at": "timestamp with time zone",
    }


# --- Append e leitura ----------------------------------------------------


def test_i06_append_e_leitura():
    with UnitOfWork() as uow:
        gravado = ErasureRecordRepository(uow.session).append_observed(entrada())
        rid = gravado.id
        uow.commit()

    with UnitOfWork() as uow:
        lido = ErasureRecordRepository(uow.session).get_by_id(rid)
        assert lido is not None
        # Igualdade de valor, não identidade: com `native_enum=False` o
        # SQLAlchemy devolve a string crua na releitura, e `StrEnum`
        # compara igual a ela. Exigir identidade testaria o carregador
        # do ORM, não o contrato do recibo.
        assert lido.outcome == ErasureOutcome.SUCCEEDED
        assert lido.subject_identifier == "coid:9f1c"
        assert lido.failure_code is None


def test_i07_consultas_por_sujeito_aprovacao_e_outcome():
    with UnitOfWork() as uow:
        repo = ErasureRecordRepository(uow.session)
        repo.append_observed(entrada(subject_identifier="coid:a", approval_ref="appr:x"))
        repo.append_observed(
            entrada(
                subject_identifier="coid:b",
                approval_ref="appr:x",
                outcome=ErasureOutcome.PARTIAL,
                failure_code="replica_unverified",
            )
        )
        uow.commit()

    with UnitOfWork() as uow:
        repo = ErasureRecordRepository(uow.session)
        assert len(repo.list_by_subject_identifier("coid:a")) == 1
        assert len(repo.list_by_approval_ref("appr:x")) == 2
        assert len(repo.list_by_outcome(ErasureOutcome.PARTIAL)) == 1


def test_i08_ordenacao_deterministica_com_instantes_iguais():
    """Recibos de um mesmo lote têm `attempted_at` idêntico.

    `now()` do PostgreSQL é o timestamp de **início da transação**
    (lição da E4.6.3), e um lote nasce numa transação só. Ordenar
    apenas por tempo faria a paginação repetir ou pular linhas; o
    desempate por `id ASC` é o que torna a ordem estável.
    """
    with UnitOfWork() as uow:
        repo = ErasureRecordRepository(uow.session)
        for _ in range(5):
            repo.append_observed(entrada(subject_identifier="coid:lote"))
        uow.commit()

    with UnitOfWork() as uow:
        repo = ErasureRecordRepository(uow.session)
        todos = repo.list_by_subject_identifier("coid:lote", limit=10)
        ids = [r.id for r in todos]
        assert ids == sorted(ids)

        pagina1 = repo.list_by_subject_identifier("coid:lote", limit=2, offset=0)
        pagina2 = repo.list_by_subject_identifier("coid:lote", limit=2, offset=2)
        assert [r.id for r in pagina1] + [r.id for r in pagina2] == ids[:4]


def test_i09_inserts_independentes_concorrentes():
    """Sem unique constraint entre recibos: duas tentativas do mesmo
    sujeito são dois fatos, não uma duplicata."""
    with UnitOfWork() as uow:
        ErasureRecordRepository(uow.session).append_observed(entrada(subject_identifier="coid:c"))
        uow.commit()
    with UnitOfWork() as uow:
        ErasureRecordRepository(uow.session).append_observed(entrada(subject_identifier="coid:c"))
        uow.commit()

    with UnitOfWork() as uow:
        assert len(ErasureRecordRepository(uow.session).list_by_subject_identifier("coid:c")) == 2


def test_i10_rollback_nao_deixa_residuo():
    with pytest.raises(RuntimeError), UnitOfWork() as uow:
        ErasureRecordRepository(uow.session).append_observed(entrada())
        raise RuntimeError("aborta")

    with engine.connect() as conn:
        assert conn.execute(sa.text("SELECT count(*) FROM erasure_records")).scalar() == 0


# --- Trigger: camada 3 ---------------------------------------------------


def test_i11_trigger_existe():
    with engine.connect() as conn:
        gatilhos = (
            conn.execute(
                sa.text(
                    "SELECT tgname FROM pg_trigger "
                    "WHERE tgrelid = 'erasure_records'::regclass AND NOT tgisinternal"
                )
            )
            .scalars()
            .all()
        )
    assert gatilhos == ["trg_erasure_records_append_only"]


def test_i12_update_bruto_bloqueado_pela_trigger():
    """A camada que vale fora do ORM.

    `GovernancePolicy` registra honestamente que SQL bruto continua
    possível. Para o recibo de um apagamento isso não bastaria: é
    justamente o registro que alguém teria motivo para reescrever.
    """
    with engine.begin() as conn:
        _insert_raw(conn)

    with pytest.raises(sa.exc.DatabaseError) as info, engine.begin() as conn:
        conn.execute(sa.text("UPDATE erasure_records SET outcome = 'succeeded'"))
    assert "append-only" in str(info.value)


def test_i13_delete_bruto_bloqueado_pela_trigger():
    with engine.begin() as conn:
        _insert_raw(conn)

    with pytest.raises(sa.exc.DatabaseError) as info, engine.begin() as conn:
        conn.execute(sa.text("DELETE FROM erasure_records"))
    assert "append-only" in str(info.value)

    with engine.connect() as conn:
        assert conn.execute(sa.text("SELECT count(*) FROM erasure_records")).scalar() == 1


def test_i14_insert_bruto_permitido():
    """Append-only é *append* only — inserir continua sendo o caminho."""
    with engine.begin() as conn:
        _insert_raw(conn)
    with engine.connect() as conn:
        assert conn.execute(sa.text("SELECT count(*) FROM erasure_records")).scalar() == 1


def test_i15_orm_e_repositorio_tambem_recusam():
    with UnitOfWork() as uow:
        gravado = ErasureRecordRepository(uow.session).append_observed(entrada())
        rid = gravado.id
        uow.commit()

    with UnitOfWork() as uow:
        repo = ErasureRecordRepository(uow.session)
        alvo = repo.get_by_id(rid)
        assert alvo is not None
        with pytest.raises(ErasureRecordImmutableError):
            repo.update(alvo)
        with pytest.raises(ErasureRecordImmutableError):
            repo.delete(alvo)


def test_i16_mutacao_por_fora_do_repositorio_e_pega_pelo_mapper():
    """Carregar, mutar o atributo e dar commit contorna o repositório —
    defeito reproduzido de verdade na E4.3.1."""
    with UnitOfWork() as uow:
        rid = ErasureRecordRepository(uow.session).append_observed(entrada()).id
        uow.commit()

    with pytest.raises(ErasureRecordImmutableError), UnitOfWork() as uow:
        alvo = uow.session.get(ErasureRecord, rid)
        assert alvo is not None
        alvo.outcome = ErasureOutcome.FAILED
        uow.session.flush()


# --- Constraints via SQL bruto -------------------------------------------


@pytest.mark.parametrize(
    ("overrides", "constraint"),
    [
        ({"subject_identifier": "   "}, "subject_identifier_not_blank"),
        ({"scope_token": " "}, "scope_token_not_blank"),
        ({"governance_policy_key": ""}, "governance_policy_key_not_blank"),
        ({"governance_resolution_ref": " "}, "governance_resolution_ref_not_blank"),
        ({"approval_ref": ""}, "approval_ref_not_blank"),
        ({"executor_ref": "  "}, "executor_ref_not_blank"),
        ({"governance_policy_version": 0}, "governance_version_positive"),
        (
            {
                "retention_policy_id": uuid.uuid4(),
                "retention_policy_key": "ret",
                "retention_policy_version": 0,
            },
            "retention_version_positive",
        ),
        ({"retention_policy_key": "ret"}, "retention_trio_all_or_none"),
        ({"completed_at": ATTEMPTED - timedelta(seconds=1)}, "completed_after_attempted"),
        ({"failure_code": "x"}, "failure_code_matches_outcome"),
        ({"outcome": "failed", "failure_code": None}, "failure_code_matches_outcome"),
    ],
)
def test_i17_constraints_rejeitam_em_sql_bruto(overrides, constraint):
    """O banco repete os invariantes que o schema já validou.

    Defesa em profundidade: a validação Python só protege quem passa
    por ela.
    """
    with pytest.raises(sa.exc.IntegrityError) as info, engine.begin() as conn:
        _insert_raw(conn, **overrides)
    assert constraint in str(info.value)


def test_i18_outcome_fora_do_vocabulario_rejeitado():
    """`pending` é `FORBIDDEN_OUTCOME` (E4.9.0) e o banco recusa.

    O `CHECK` explícito de vocabulário é necessário: medido na
    baseline, `Enum(native_enum=False)` do SQLAlchemy 2.x **não** cria
    verificação (`cognitive_objects` tem zero `CHECK`). Sem ele, este
    INSERT bruto passaria.
    """
    with pytest.raises(sa.exc.IntegrityError) as info, engine.begin() as conn:
        _insert_raw(conn, outcome="pending")
    # Duas constraints alcançam este INSERT — o vocabulário e a matriz
    # outcome/failure_code — e qual dispara primeiro é decisão do
    # PostgreSQL. Afirmar uma delas seria testar a ordem de avaliação;
    # o que importa é que a linha não entra.
    texto = str(info.value)
    assert "outcome_vocabulary" in texto or "failure_code_matches_outcome" in texto

    with engine.connect() as conn:
        assert conn.execute(sa.text("SELECT count(*) FROM erasure_records")).scalar() == 0


def test_i19_target_class_fora_do_vocabulario_rejeitado():
    with pytest.raises(sa.exc.IntegrityError) as info, engine.begin() as conn:
        _insert_raw(conn, target_class="whatever")
    assert "target_class_vocabulary" in str(info.value)


def test_i20_trio_de_retencao_completo_aceito():
    with engine.begin() as conn:
        _insert_raw(
            conn,
            retention_policy_id=uuid.uuid4(),
            retention_policy_key="ret.default",
            retention_policy_version=2,
        )
    with engine.connect() as conn:
        assert conn.execute(sa.text("SELECT count(*) FROM erasure_records")).scalar() == 1


# --- Migration -----------------------------------------------------------


def test_i21_round_trip_da_migration():
    """upgrade → downgrade → upgrade, removendo trigger e função."""
    # Atualizado pela E4.9.6: `erasure_records` deixou de ser a última
    # migração, então `downgrade -1` agora remove `retention_policies`.
    # Descer DUAS revisões é o que exercita de novo o round trip desta
    # tabela — e o teste continua provando o mesmo: a tabela some, a
    # função não fica órfã, e o reupgrade restaura tudo.
    # ATUALIZADO PELA E4.9.9.a: o head passou a ser `a1f7c2d40e93`, e um
    # `-N` relativo quebra a cada migration nova. O alvo passa a ser
    # EXPLÍCITO — a revisão anterior a `erasure_records` —, que é o que o
    # teste sempre quis dizer.
    migrations.upgrade("head")
    migrations.downgrade("7b2e4c9a15df")

    with engine.connect() as conn:
        assert conn.execute(sa.text("SELECT to_regclass('erasure_records')")).scalar() is None
        orfas = (
            conn.execute(
                sa.text(
                    "SELECT proname FROM pg_proc WHERE proname = 'reject_erasure_record_mutation'"
                )
            )
            .scalars()
            .all()
        )
        assert orfas == [], "função órfã após downgrade"

    migrations.upgrade("head")
    with engine.connect() as conn:
        assert conn.execute(sa.text("SELECT to_regclass('erasure_records')")).scalar() is not None


def test_i22_single_head():
    # Atualizado pela E4.9.6 — head único, agora `c8a3f5017e94`.
    assert migrations.head_revision() == "a91d3f7c26be"
    assert migrations.current_revision() == "a91d3f7c26be"


# --- Guardas do §15.3 ----------------------------------------------------


def test_i23_tabela_vazia_apos_migrations_da_baseline():
    """Nenhum recibo nasce por existir schema.

    A migration cria a tabela e nada mais: não há seed, data migration
    nem default que fabrique registro.
    """
    migrations.upgrade("head")
    with engine.connect() as conn:
        assert conn.execute(sa.text("SELECT count(*) FROM erasure_records")).scalar() == 0


def test_i24_fluxos_e3_e4_congelados_nao_criam_recibo():
    """Exercita patrimônio real da E3/E4 e confere que a tabela segue vazia.

    É a diferença entre "nenhum serviço importa o repositório" — provado
    estaticamente — e "nenhum caminho de execução real produz recibo",
    que só um fluxo de verdade demonstra.
    """
    from app.cognitive.models.cognitive_object import CognitiveObject
    from app.cognitive.repositories.object_repository import ObjectRepository
    from app.memory.models.memory_domain import MemoryDomain
    from app.memory.repositories.memory_domain_repository import MemoryDomainRepository

    with UnitOfWork() as uow:
        objeto = ObjectRepository(uow.session).add(CognitiveObject())
        # `MemoryDomain` tem contrato mínimo por decisão da E4.1 — só
        # `id` e `name`. `description` foi deliberadamente recusado lá.
        MemoryDomainRepository(uow.session).add(
            MemoryDomain(name=f"dominio-{uuid.uuid4().hex[:8]}")
        )
        uow.commit()
        assert objeto.id is not None

    with engine.connect() as conn:
        assert conn.execute(sa.text("SELECT count(*) FROM erasure_records")).scalar() == 0

    with engine.begin() as conn:
        conn.execute(sa.text("TRUNCATE cognitive_objects, memory_domains CASCADE"))


def test_i25_delete_pela_sessao_e_pego_pelo_evento_de_mapper():
    """Camada 1 contra `session.delete()` — sem passar pelo repositório.

    `repo.delete()` recusa antes de o ORM agir, então só um delete
    emitido pela própria sessão exercita o `before_delete`. É o
    caminho que a E4.3.1 provou existir: quem contorna o repositório
    contorna o override, não o evento.
    """
    with UnitOfWork() as uow:
        rid = ErasureRecordRepository(uow.session).append_observed(entrada()).id
        uow.commit()

    with pytest.raises(ErasureRecordImmutableError), UnitOfWork() as uow:
        alvo = uow.session.get(ErasureRecord, rid)
        assert alvo is not None
        uow.session.delete(alvo)
        uow.session.flush()

    with engine.connect() as conn:
        assert conn.execute(sa.text("SELECT count(*) FROM erasure_records")).scalar() == 1
