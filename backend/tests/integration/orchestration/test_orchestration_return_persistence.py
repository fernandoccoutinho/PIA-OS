"""
Persistência da E7.2 contra PostgreSQL real — append-only, constraints,
índice parcial e migration.

```text
APPLICATION_CHECK != DATABASE_GUARANTEE
RESULT_REJECTED != RESULT_DISCARDED
```

O que a aplicação verifica sob lock, o banco também recusa. As duas coisas
não são redundantes: o lock serializa quem passa pelo serviço, o schema
recusa quem chegar por SQL bruto ou por um caminho que ainda não existe.
"""

import json
import threading
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import DataError, IntegrityError

from app.connections.repositories.connection_repository import ConnectionRepository
from app.connections.services.connection_execution_receipt_service import (
    ConnectionExecutionReceiptService,
)
from app.connections.services.connection_profile_service import ConnectionProfileService
from app.database import migrations
from app.database.engine import engine
from app.database.health import check_database_health
from app.database.session import SessionLocal
from app.orchestration.adapters.manual_transport import ManualTransport
from app.orchestration.errors.exceptions import (
    HandoffRecordImmutableError,
    OrchestrationLifecycleViolationError,
    OrchestrationScopeViolationError,
)
from app.orchestration.models.enums import HandoffMode
from app.orchestration.ports.transport import RawReturn
from app.orchestration.repositories.orchestration_repository import OrchestrationRepository
from app.orchestration.schemas.envelope import ContextRef, ScheduleDraft, StepDraft
from app.orchestration.schemas.output_contract import (
    OUTPUT_JSON_OBJECT_V1,
    OUTPUT_NON_EMPTY_TEXT_V1,
)
from app.orchestration.services.command_receipt_service import CommandReceiptService
from app.orchestration.services.handoff_service import HandoffService
from app.orchestration.services.manual_handoff_export_service import ManualHandoffExportService
from app.orchestration.services.return_validation_service import (
    DeclaredAttribution,
    ReturnValidationService,
)
from app.orchestration.services.schedule_service import ScheduleService
from app.repositories.unit_of_work import UnitOfWork

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not check_database_health().available,
        reason="PostgreSQL real indisponível — triggers e índice parcial são a prova.",
    ),
]

_REVISION_E72 = "c3a75e01d248"
_REVISION_E73 = "f2c60d8a41b9"
_MIGRATION_HEAD = "c58d1e0a94f7"
_PARENT = "b8c04e2fd137"
_HASH = "f" * 64
_TABELAS_NOVAS = ("handoff_results", "handoff_attributions")
# ATUALIZADO PELA E7.4-1: o recibo de execução referencia a Attempt
# por FK composta e é append-only — cai PRIMEIRO e com o trigger
# desabilitado, como as demais append-only desta lista.
_APPEND_ONLY = (
    "connection_execution_receipts",
    "audit_opinions",
    "execution_observations",
    "orchestration_control_events",
    *_TABELAS_NOVAS,
    "seal_receipts",
    "service_delegations",
)


def _limpar() -> None:
    with engine.begin() as conexao:
        for tabela in _APPEND_ONLY:
            conexao.execute(sa.text(f"ALTER TABLE {tabela} DISABLE TRIGGER USER"))
            conexao.execute(sa.text(f"DELETE FROM {tabela}"))
            conexao.execute(sa.text(f"ALTER TABLE {tabela} ENABLE TRIGGER USER"))
        for tabela in (
            "handoff_attempts",
            "schedule_steps",
            "schedules",
            "command_receipts",
            # O perfil manual só pode cair DEPOIS do recibo que o referencia.
            "connection_profiles",
        ):
            conexao.execute(sa.text(f"DELETE FROM {tabela}"))


@pytest.fixture(autouse=True)
def _base_limpa():
    _limpar()
    yield
    _limpar()


class _Contexto:
    def __init__(self, uow: UnitOfWork) -> None:
        self.repositorio = OrchestrationRepository(uow.session)
        self.agendas = ScheduleService(self.repositorio)
        self.handoff = HandoffService(self.repositorio)
        conexoes = ConnectionRepository(uow.session)
        self.exportacao = ManualHandoffExportService(
            self.repositorio,
            self.handoff,
            ManualTransport(),
            connection_profiles=ConnectionProfileService(conexoes),
            connection_receipts=ConnectionExecutionReceiptService(conexoes),
        )
        self.validacao = ReturnValidationService(self.repositorio)
        self.comandos = CommandReceiptService(
            self.repositorio, self.agendas, self.handoff, self.exportacao, self.validacao
        )


def _rascunho() -> ScheduleDraft:
    return ScheduleDraft(
        title="t",
        steps=(
            StepDraft(
                role="reviewer",
                instruction_ref="i://1",
                expected_output_contract=OUTPUT_NON_EMPTY_TEXT_V1,
                context_refs=(ContextRef(uri="a://a", sha256=_HASH, bytes=1),),
            ),
            StepDraft(
                role="auditor",
                instruction_ref="i://2",
                expected_output_contract=OUTPUT_JSON_OBJECT_V1,
            ),
        ),
    )


def _preparar(principal: str = "p") -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    schedule_id = uuid.uuid4()
    with UnitOfWork() as uow:
        ctx = _Contexto(uow)
        ctx.agendas.create_schedule(
            schedule_id=schedule_id,
            control_principal_ref=principal,
            draft=_rascunho(),
            execution_mode=HandoffMode.MANUAL_HANDOFF,
        )
        vista = ctx.agendas.activate(control_principal_ref=principal, schedule_id=schedule_id)
        uow.commit()
    return schedule_id, vista.steps[0].step_id, vista.steps[1].step_id


def _exportar_e_importar(
    schedule_id: uuid.UUID, step_id: uuid.UUID, conteudo: str, principal: str = "p"
) -> uuid.UUID:
    with UnitOfWork() as uow:
        ctx = _Contexto(uow)
        _, saida = ctx.comandos.export_handoff_once(
            technical_principal_ref=principal,
            command_key=f"e-{uuid.uuid4()}",
            schedule_id=schedule_id,
            step_id=step_id,
            sealer_ref=principal,
        )
        attempt_id = saida.exported.attempt_id
        uow.commit()
    with UnitOfWork() as uow:
        ctx = _Contexto(uow)
        ctx.comandos.import_return_once(
            technical_principal_ref=principal,
            command_key=f"i-{uuid.uuid4()}",
            schedule_id=schedule_id,
            step_id=step_id,
            attempt_id=attempt_id,
            raw=RawReturn(media_type="text/plain", content=conteudo),
            attribution=DeclaredAttribution(declared_instance_id="inst"),
        )
        uow.commit()
    return attempt_id


# --- append-only ------------------------------------------------------------


@pytest.mark.parametrize("tabela", _TABELAS_NOVAS)
@pytest.mark.parametrize("operacao", ["UPDATE", "DELETE", "TRUNCATE"])
def test_e72p01_as_tres_operacoes_sao_recusadas_nas_duas_tabelas(tabela, operacao) -> None:
    schedule_id, step_id, _ = _preparar()
    _exportar_e_importar(schedule_id, step_id, "parecer")
    coluna = "output_bytes = 99" if tabela == "handoff_results" else "role = 'forjado'"
    sql = {
        "UPDATE": f"UPDATE {tabela} SET {coluna}",
        "DELETE": f"DELETE FROM {tabela}",
        "TRUNCATE": f"TRUNCATE {tabela}",
    }[operacao]
    # ATUALIZADO PELA E7.3: `audit_opinions` referencia `handoff_results`,
    # e o PostgreSQL recusa TRUNCATE de tabela referenciada ANTES de
    # chegar ao trigger. A recusa continua sendo recusa; o que muda é
    # quem recusa primeiro. `TRUNCATE ... CASCADE` alcança o trigger.
    if operacao == "TRUNCATE" and tabela == "handoff_results":
        sql = f"TRUNCATE {tabela} CASCADE"
    with pytest.raises(Exception, match="append-only"), engine.begin() as conexao:
        conexao.execute(sa.text(sql))


def test_e72p02_o_repositorio_recusa_antes_de_tocar_o_banco() -> None:
    """Segunda camada: recusa explícita com PIA-8061."""
    with UnitOfWork() as uow:
        repositorio = OrchestrationRepository(uow.session)
        for metodo in ("update_handoff_record", "delete_handoff_record"):
            with pytest.raises(HandoffRecordImmutableError) as capturado:
                getattr(repositorio, metodo)(record_id=uuid.uuid4())
            assert capturado.value.error_code.code == "PIA-8061"


# --- constraints por SQL bruto ----------------------------------------------


def _um_attempt() -> uuid.UUID:
    schedule_id, step_id, _ = _preparar()
    with UnitOfWork() as uow:
        ctx = _Contexto(uow)
        _, saida = ctx.comandos.export_handoff_once(
            technical_principal_ref="p",
            command_key="e1",
            schedule_id=schedule_id,
            step_id=step_id,
            sealer_ref="p",
        )
        uow.commit()
    return saida.exported.attempt_id


_INSERT_RESULT = (
    "INSERT INTO handoff_results (id, attempt_id, status, expected_output_contract, "
    "output_media_type, output_sha256, output_bytes, validation_codes) VALUES "
    "(gen_random_uuid(), :a, :status, 'c', 'text/plain', :hash, :bytes, CAST(:codes AS jsonb))"
)


@pytest.mark.parametrize(
    ("nome", "parametros"),
    [
        ("validated com código", {"status": "validated", "codes": '["media_type_mismatch"]'}),
        ("rejected sem código", {"status": "rejected", "codes": "[]"}),
        ("hash não hexadecimal", {"status": "validated", "hash": "ZZZ", "codes": "[]"}),
        ("bytes negativo", {"status": "validated", "bytes": -1, "codes": "[]"}),
    ],
)
def test_e72p03_o_banco_recusa_resultado_incoerente(nome, parametros) -> None:
    attempt_id = _um_attempt()
    valores = {"a": attempt_id, "hash": _HASH, "bytes": 1, **parametros}
    with pytest.raises(IntegrityError), engine.begin() as conexao:
        conexao.execute(sa.text(_INSERT_RESULT), valores)


def test_e72p04_o_banco_recusa_atribuicao_sem_autodeclaracao() -> None:
    """`SELF_DECLARED != VERIFIED_IDENTITY`, imposto por `CHECK`."""
    attempt_id = _um_attempt()
    with pytest.raises(IntegrityError), engine.begin() as conexao:
        conexao.execute(
            sa.text(
                "INSERT INTO handoff_attributions (id, attempt_id, role, declared_instance_id, "
                "declared_at, self_declared) VALUES (gen_random_uuid(), :a, 'r', 'i', now(), false)"
            ),
            {"a": attempt_id},
        )


def test_e72p05_um_resultado_e_uma_atribuicao_por_tentativa() -> None:
    schedule_id, step_id, _ = _preparar()
    attempt_id = _exportar_e_importar(schedule_id, step_id, "parecer")
    with pytest.raises(Exception, match="uq_handoff_results_attempt"), engine.begin() as conexao:
        conexao.execute(
            sa.text(_INSERT_RESULT),
            {"a": attempt_id, "status": "validated", "hash": _HASH, "bytes": 1, "codes": "[]"},
        )


def test_e72p06_a_atribuicao_exige_tentativa_existente() -> None:
    """FK positiva e negativa."""
    with pytest.raises(Exception, match="fk_handoff_attributions_attempt"), engine.begin() as c:
        c.execute(
            sa.text(
                "INSERT INTO handoff_attributions (id, attempt_id, role, declared_instance_id, "
                "declared_at, self_declared) VALUES (gen_random_uuid(), :a, 'r', 'i', now(), true)"
            ),
            {"a": uuid.uuid4()},
        )
    attempt_id = _um_attempt()
    with engine.begin() as conexao:
        conexao.execute(
            sa.text(
                "INSERT INTO handoff_attributions (id, attempt_id, role, declared_instance_id, "
                "declared_at, self_declared) VALUES (gen_random_uuid(), :a, 'r', 'i', now(), true)"
            ),
            {"a": attempt_id},
        )


def test_e72p07_provenance_record_ref_aceita_valor_arbitrario_e_a_e7_nunca_o_usa() -> None:
    """Referência opaca: sem FK, e sem writer.

    ```text
    REFERENCE != FOREIGN_KEY
    E7_2_NON_NULL_WRITER = NONE
    ```

    Custo declarado da ausência de FK: o banco aceita um UUID que não
    corresponde a proveniência alguma. A E7.2 compensa não expondo nem
    produzindo qualquer caminho de preenchimento — o que este teste mede
    é justamente que a coluna fica `NULL` em tudo que a E7 cria.
    """
    schedule_id, step_id, _ = _preparar()
    _exportar_e_importar(schedule_id, step_id, "parecer")
    with engine.connect() as conexao:
        nao_nulos = conexao.execute(
            sa.text(
                "SELECT count(*) FROM handoff_attributions WHERE provenance_record_ref IS NOT NULL"
            )
        ).scalar_one()
    assert nao_nulos == 0


# --- índice parcial sob concorrência ---------------------------------------


def test_e72p08_o_indice_parcial_recusa_duas_tentativas_abertas() -> None:
    schedule_id, step_id, _ = _preparar()
    with pytest.raises(Exception, match="single_open"), engine.begin() as conexao:
        for numero in (90, 91):
            conexao.execute(
                sa.text(
                    "INSERT INTO handoff_attempts (id, schedule_id, step_id, attempt_number, "
                    "envelope_version, content_sha256, state) VALUES "
                    "(gen_random_uuid(), :s, :p, :n, '1', :h, 'open')"
                ),
                {"s": schedule_id, "p": step_id, "n": numero, "h": _HASH},
            )


def test_e72p09_exports_concorrentes_no_servico_abrem_no_maximo_uma() -> None:
    schedule_id, step_id, _ = _preparar()
    barreira = threading.Barrier(2)
    erros: list[BaseException] = []
    sucessos: list[uuid.UUID] = []

    def exportar(indice: int) -> None:
        try:
            with UnitOfWork(session_factory=SessionLocal) as uow:
                ctx = _Contexto(uow)
                barreira.wait(timeout=15)
                _, saida = ctx.comandos.export_handoff_once(
                    technical_principal_ref="p",
                    command_key=f"conc-{indice}",
                    schedule_id=schedule_id,
                    step_id=step_id,
                    sealer_ref="p",
                )
                uow.commit()
                if saida is not None:
                    sucessos.append(saida.exported.attempt_id)
        except BaseException as exc:  # noqa: BLE001 - esperado num dos dois
            erros.append(exc)

    linhas = [threading.Thread(target=exportar, args=(i,)) for i in range(2)]
    for linha in linhas:
        linha.start()
    for linha in linhas:
        linha.join(timeout=45)
    with engine.connect() as conexao:
        abertas = conexao.execute(
            sa.text("SELECT count(*) FROM handoff_attempts WHERE state = 'open'")
        ).scalar_one()
    assert abertas <= 1
    assert len(sucessos) <= 1
    assert len(sucessos) + len(erros) == 2


def test_e72p10_rollback_apos_falha_nao_deixa_comando_nem_estado_parcial() -> None:
    """Reivindicação, efeito e transições vivem na mesma transação."""
    schedule_id, step_id, _ = _preparar()
    with UnitOfWork() as uow:
        ctx = _Contexto(uow)
        with pytest.raises(OrchestrationScopeViolationError):
            ctx.comandos.import_return_once(
                technical_principal_ref="p",
                command_key="falha",
                schedule_id=schedule_id,
                step_id=step_id,
                attempt_id=uuid.uuid4(),  # tentativa inexistente
                raw=RawReturn(media_type="text/plain", content="x"),
                attribution=DeclaredAttribution(declared_instance_id="i"),
            )
    with engine.connect() as conexao:
        assert conexao.execute(sa.text("SELECT count(*) FROM command_receipts")).scalar_one() == 0
        assert conexao.execute(sa.text("SELECT count(*) FROM handoff_results")).scalar_one() == 0
        assert (
            conexao.execute(sa.text("SELECT count(*) FROM handoff_attributions")).scalar_one() == 0
        )
        estados = {
            linha[0] for linha in conexao.execute(sa.text("SELECT state FROM schedule_steps"))
        }
    assert estados == {"pending"}


# --- migration --------------------------------------------------------------


def test_e72p11_head_unica_e_filha_de_b8c04e2fd137() -> None:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(Config("alembic.ini"))
    # ATUALIZADO PELA E7.4-1: a folha passou a ser `b47e9c05d3fa`; antes
    # `a91d3f7c26be` (corretivo R1 da E7.3).
    # O que este teste protege é a ANCESTRALIDADE da migration da E7.2,
    # que não mudou; head única é medida por `e72p18`.
    assert script.get_revision(_REVISION_E72).down_revision == _PARENT
    assert migrations.current_revision() == _MIGRATION_HEAD


def test_e72p12_round_trip_upgrade_downgrade_upgrade() -> None:
    _limpar()
    with engine.begin() as conexao:
        conexao.execute(sa.text("DELETE FROM command_receipts"))
    migrations.downgrade(_PARENT)
    assert migrations.current_revision() == _PARENT
    presentes = set(sa.inspect(engine).get_table_names())
    assert not (set(_TABELAS_NOVAS) & presentes)
    with engine.connect() as conexao:
        indices = {
            linha[0]
            for linha in conexao.execute(
                sa.text("SELECT indexname FROM pg_indexes WHERE tablename = 'handoff_attempts'")
            )
        }
    assert "ix_handoff_attempts_single_open" not in indices
    migrations.upgrade("head")
    assert migrations.current_revision() == _MIGRATION_HEAD
    assert set(_TABELAS_NOVAS) <= set(sa.inspect(engine).get_table_names())
    with engine.connect() as conexao:
        indices = {
            linha[0]
            for linha in conexao.execute(
                sa.text("SELECT indexname FROM pg_indexes WHERE tablename = 'handoff_attempts'")
            )
        }
        gatilhos = {
            linha[0]
            for linha in conexao.execute(
                sa.text("SELECT tgname FROM pg_trigger WHERE NOT tgisinternal")
            )
        }
    assert "ix_handoff_attempts_single_open" in indices
    assert {
        "trg_handoff_results_append_only",
        "trg_handoff_results_no_truncate",
        "trg_handoff_attributions_append_only",
        "trg_handoff_attributions_no_truncate",
    } <= gatilhos


@pytest.mark.parametrize("tabela", _TABELAS_NOVAS)
def test_e72p13_downgrade_recusa_com_linha_em_cada_tabela(tabela) -> None:
    schedule_id, step_id, _ = _preparar()
    _exportar_e_importar(schedule_id, step_id, "parecer")
    with engine.connect() as conexao:
        assert conexao.execute(sa.text(f"SELECT count(*) FROM {tabela}")).scalar_one() >= 1
    # A folha E7.3 recusa antes de chegar à E7.2 — e a recusa é o ponto.
    with pytest.raises(RuntimeError, match="downgrade recusado"):
        migrations.downgrade(_PARENT)
    assert migrations.current_revision() == _MIGRATION_HEAD


def test_e72p14_sem_drift_entre_orm_e_schema() -> None:
    import app.cognitive.models  # noqa: F401
    import app.memory.models  # noqa: F401
    import app.orchestration.models  # noqa: F401
    import app.predictive_accessibility.reconfiguration  # noqa: F401
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext
    from app.database.base import Base

    with engine.connect() as conexao:
        diferencas = compare_metadata(MigrationContext.configure(conexao), Base.metadata)
    reais = [d for d in diferencas if "test_" not in str(d)]
    assert reais == [], f"schema/ORM drift: {reais}"


# --- corretivo R1: canonicidade de validation_codes no banco ----------------

_REVISION_E72_R1 = "d1f6a83b70c5"


def _inserir_resultado(attempt_id: uuid.UUID, status: str, codes: str) -> None:
    with engine.begin() as conexao:
        conexao.execute(
            sa.text(
                "INSERT INTO handoff_results (id, attempt_id, status, "
                "expected_output_contract, output_media_type, output_sha256, output_bytes, "
                "validation_codes) VALUES (gen_random_uuid(), :a, :s, 'c', 'text/plain', "
                ":h, 1, CAST(:c AS jsonb))"
            ),
            {"a": attempt_id, "s": status, "h": _HASH, "c": codes},
        )


@pytest.mark.parametrize(
    ("nome", "status", "codes"),
    [
        ("código fora do vocabulário", "rejected", '["inventado"]'),
        ("elemento não textual", "rejected", "[1]"),
        ("elemento objeto", "rejected", '[{"x": 1}]'),
        ("duplicata", "rejected", '["media_type_mismatch","media_type_mismatch"]'),
        ("ordem não canônica", "rejected", '["media_type_mismatch","expected_json_object"]'),
        ("vazio em rejected", "rejected", "[]"),
        ("não vazio em validated", "validated", '["media_type_mismatch"]'),
        ("não é array", "rejected", '"media_type_mismatch"'),
    ],
)
def test_e72p15_o_banco_recusa_validation_codes_nao_canonico(nome, status, codes) -> None:
    """Achado C3: `COUNT_CHECK != VOCABULARY_CHECK`.

    O `CHECK` original via array e quantidade. Vocabulário, tipo de
    elemento, duplicata e ordem passavam por SQL bruto — e o
    `TypeDecorator` não é integridade, porque o que não passa pelo ORM não
    passa por ele.
    """
    attempt_id = _um_attempt()
    with pytest.raises(IntegrityError):
        _inserir_resultado(attempt_id, status, codes)


@pytest.mark.parametrize(
    ("status", "codes"),
    [
        ("validated", "[]"),
        ("rejected", '["media_type_mismatch"]'),
        ("rejected", '["expected_json_object","media_type_mismatch"]'),
        (
            "rejected",
            '["expected_json_object","expected_non_empty_text","media_type_mismatch",'
            '"non_canonical_json_number","unsupported_output_contract"]',
        ),
    ],
)
def test_e72p16_o_banco_aceita_a_forma_canonica(status, codes) -> None:
    """Não-vacuidade: a constraint recusa o incoerente, não tudo."""
    _inserir_resultado(_um_attempt(), status, codes)
    with engine.connect() as conexao:
        assert conexao.execute(sa.text("SELECT count(*) FROM handoff_results")).scalar_one() == 1


def test_e72p17_o_vinculo_de_requisicao_e_persistido_como_hash() -> None:
    """`request_sha256` guarda impressão digital, nunca corpo."""
    schedule_id, step_id, _ = _preparar()
    _exportar_e_importar(schedule_id, step_id, "conteúdo do parecer")
    with engine.connect() as conexao:
        linhas = list(
            conexao.execute(
                sa.text("SELECT operation, request_sha256 FROM command_receipts ORDER BY operation")
            )
        )
    assert linhas, "nenhum recibo de comando"
    for operacao, impressao in linhas:
        assert impressao is not None, operacao
        assert len(impressao) == 64
        assert all(caractere in "0123456789abcdef" for caractere in impressao)
    with engine.connect() as conexao:
        texto = json.dumps(
            [
                dict(linha._mapping)
                for linha in conexao.execute(sa.text("SELECT * FROM command_receipts"))
            ],
            default=str,
        )
    assert "conteúdo do parecer" not in texto


def test_e72p18_head_unica_e_filha_de_c3a75e01d248() -> None:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(Config("alembic.ini"))
    assert tuple(script.get_heads()) == ("c58d1e0a94f7",)
    assert script.get_revision(_REVISION_E72_R1).down_revision == _REVISION_E72
    assert script.get_revision(_REVISION_E72_R2).down_revision == _REVISION_E72_R1


def test_e72p19_round_trip_da_migration_corretiva() -> None:
    _limpar()
    with engine.begin() as conexao:
        conexao.execute(sa.text("DELETE FROM command_receipts"))
    migrations.downgrade(_REVISION_E72)
    assert migrations.current_revision() == _REVISION_E72
    with engine.connect() as conexao:
        colunas = {
            linha[0]
            for linha in conexao.execute(
                sa.text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'command_receipts'"
                )
            )
        }
    assert "request_sha256" not in colunas
    migrations.upgrade("head")
    assert migrations.current_revision() == _MIGRATION_HEAD
    with engine.connect() as conexao:
        colunas = {
            linha[0]
            for linha in conexao.execute(
                sa.text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'command_receipts'"
                )
            )
        }
        funcoes = {
            linha[0]
            for linha in conexao.execute(
                sa.text("SELECT proname FROM pg_proc WHERE proname LIKE 'orchestration_%'")
            )
        }
    assert "request_sha256" in colunas
    assert "orchestration_validation_codes_are_canonical" in funcoes


def test_e72p20_downgrade_recusa_com_vinculo_de_requisicao_gravado() -> None:
    schedule_id, step_id, _ = _preparar()
    _exportar_e_importar(schedule_id, step_id, "parecer")
    with pytest.raises(RuntimeError, match="downgrade recusado"):
        migrations.downgrade(_REVISION_E72)
    assert migrations.current_revision() == _MIGRATION_HEAD


# --- corretivo R2: sealer_ref na digital e hexadecimal no banco -------------

_REVISION_E72_R2 = "e5b21c9704af"


def _exportar_uma_vez(
    schedule_id: uuid.UUID, step_id: uuid.UUID, chave: str, sealer: str, principal: str = "p"
):
    with UnitOfWork() as uow:
        ctx = _Contexto(uow)
        recibo, saida = ctx.comandos.export_handoff_once(
            technical_principal_ref=principal,
            command_key=chave,
            schedule_id=schedule_id,
            step_id=step_id,
            sealer_ref=sealer,
        )
        uow.commit()
    return recibo, saida


def _snapshot_completo() -> dict[str, list[tuple[object, ...]]]:
    consultas = {
        "schedules": "SELECT id, state, updated_at FROM schedules ORDER BY id",
        "schedule_steps": "SELECT id, state, updated_at FROM schedule_steps ORDER BY id",
        "handoff_attempts": (
            "SELECT id, step_id, attempt_number, state, content_sha256, created_at, updated_at "
            "FROM handoff_attempts ORDER BY id"
        ),
        "seal_receipts": (
            "SELECT id, attempt_id, content_sha256, sealed_at, sealer_ref, created_at "
            "FROM seal_receipts ORDER BY id"
        ),
        "handoff_results": (
            "SELECT id, attempt_id, status, created_at FROM handoff_results ORDER BY id"
        ),
        "handoff_attributions": (
            "SELECT id, attempt_id, role, declared_instance_id, declared_at, self_declared, "
            "created_at FROM handoff_attributions ORDER BY id"
        ),
        "command_receipts": (
            "SELECT id, operation, command_key, outcome_ref, request_sha256, created_at, "
            "updated_at FROM command_receipts ORDER BY id"
        ),
    }
    with engine.connect() as conexao:
        return {
            nome: [tuple(linha) for linha in conexao.execute(sa.text(sql))]
            for nome, sql in consultas.items()
        }


def test_e72p21_export_com_mesmo_selador_e_replay_exato() -> None:
    """Mesma chave + mesmo `sealer_ref` = replay, zero efeito adicional."""
    schedule_id, step_id, _ = _preparar()
    primeiro, saida = _exportar_uma_vez(schedule_id, step_id, "e1", "selador-a")
    assert primeiro.replayed is False and saida is not None
    antes = _snapshot_completo()
    segundo, repetida = _exportar_uma_vez(schedule_id, step_id, "e1", "selador-a")
    assert segundo.replayed is True
    assert repetida is None, "replay não pode reexecutar o efeito"
    assert segundo.receipt_id == primeiro.receipt_id
    assert segundo.outcome_ref == primeiro.outcome_ref
    assert _snapshot_completo() == antes
    with engine.connect() as conexao:
        assert conexao.execute(sa.text("SELECT count(*) FROM handoff_attempts")).scalar_one() == 1
        assert conexao.execute(sa.text("SELECT count(*) FROM seal_receipts")).scalar_one() == 1


def test_e72p22_export_com_selador_diferente_recusa_sem_mutar() -> None:
    """`WHO_SEALED_IS_PART_OF_WHAT_WAS_REQUESTED`.

    Pelo caminho HTTP o `sealer_ref` deriva do principal, que já compõe a
    tripla — a colisão nem existiria. O serviço, porém, recebe o selador
    como parâmetro próprio, e é aí que a digital precisa cobri-lo.
    """
    schedule_id, step_id, _ = _preparar()
    _exportar_uma_vez(schedule_id, step_id, "e1", "selador-a")
    antes = _snapshot_completo()
    with UnitOfWork() as uow:
        ctx = _Contexto(uow)
        with pytest.raises(OrchestrationLifecycleViolationError):
            ctx.comandos.export_handoff_once(
                technical_principal_ref="p",
                command_key="e1",
                schedule_id=schedule_id,
                step_id=step_id,
                sealer_ref="selador-INTRUSO",
            )
    assert _snapshot_completo() == antes
    with engine.connect() as conexao:
        seladores = {
            linha[0] for linha in conexao.execute(sa.text("SELECT sealer_ref FROM seal_receipts"))
        }
    assert seladores == {"selador-a"}


def test_e72p23_seal_handoff_com_selador_diferente_recusa_sem_mutar() -> None:
    """O mesmo para `SEAL_HANDOFF`, cuja semântica E7.1 é preservada."""
    schedule_id, step_id, _ = _preparar()
    with UnitOfWork() as uow:
        ctx = _Contexto(uow)
        primeiro = ctx.comandos.seal_handoff_once(
            technical_principal_ref="p",
            command_key="s1",
            schedule_id=schedule_id,
            step_id=step_id,
            sealer_ref="selador-a",
        )
        uow.commit()
    assert primeiro.replayed is False
    antes = _snapshot_completo()
    with UnitOfWork() as uow:
        ctx = _Contexto(uow)
        repetido = ctx.comandos.seal_handoff_once(
            technical_principal_ref="p",
            command_key="s1",
            schedule_id=schedule_id,
            step_id=step_id,
            sealer_ref="selador-a",
        )
        uow.commit()
    assert repetido.replayed is True
    assert repetido.receipt_id == primeiro.receipt_id
    assert _snapshot_completo() == antes
    with UnitOfWork() as uow:
        ctx = _Contexto(uow)
        with pytest.raises(OrchestrationLifecycleViolationError):
            ctx.comandos.seal_handoff_once(
                technical_principal_ref="p",
                command_key="s1",
                schedule_id=schedule_id,
                step_id=step_id,
                sealer_ref="outro-selador",
            )
    assert _snapshot_completo() == antes


def test_e72p24_a_atribuicao_imutavel_original_permanece_intacta() -> None:
    """Recusa por selador divergente não toca veredito nem atribuição."""
    schedule_id, step_id, _ = _preparar()
    _exportar_e_importar(schedule_id, step_id, "parecer completo")
    antes = _snapshot_completo()
    with UnitOfWork() as uow:
        ctx = _Contexto(uow)
        with pytest.raises(OrchestrationLifecycleViolationError):
            (
                ctx.comandos.export_handoff_once(
                    technical_principal_ref="p",
                    command_key="e-conflito",
                    schedule_id=schedule_id,
                    step_id=step_id,
                    sealer_ref="selador-a",
                )
                if False
                else ctx.comandos.seal_handoff_once(
                    technical_principal_ref="p",
                    command_key="s-nova",
                    schedule_id=schedule_id,
                    step_id=step_id,
                    sealer_ref="x",
                )
            )
    assert _snapshot_completo()["handoff_attributions"] == antes["handoff_attributions"]
    assert _snapshot_completo()["handoff_results"] == antes["handoff_results"]


@pytest.mark.parametrize(
    ("nome", "valor"),
    [
        ("não hexadecimal", "z" * 64),
        ("maiúsculas", "A" * 64),
        ("mistura de caixa", "aB" * 32),
        ("curto demais", "a" * 63),
        ("longo demais", "a" * 65),
    ],
)
def test_e72p25_o_banco_recusa_request_sha256_fora_da_forma_canonica(nome, valor) -> None:
    """`LENGTH_CHECK != FORMAT_CHECK`; `UPPERCASE_DIGEST != CANONICAL_DIGEST`.

    `DataError` para o valor longo demais: o tipo `varchar(64)` barra
    antes do `CHECK`. Recusa por tipo é recusa — o que não pode existir é
    a linha.
    """
    with pytest.raises((IntegrityError, DataError)), engine.begin() as conexao:
        conexao.execute(
            sa.text(
                "INSERT INTO command_receipts (id, technical_principal_ref, operation, "
                "command_key, outcome_ref, request_sha256) VALUES "
                "(gen_random_uuid(), 'p', 'orchestration.seal_handoff', :k, 'x', :h)"
            ),
            {"k": f"k-{nome}", "h": valor},
        )


@pytest.mark.parametrize("valor", [None, "a" * 64, "0123456789abcdef" * 4])
def test_e72p26_o_banco_aceita_null_historico_e_digest_canonico(valor) -> None:
    """Não-vacuidade: recusa o inválido, não tudo. `NULL` histórico segue."""
    with engine.begin() as conexao:
        conexao.execute(
            sa.text(
                "INSERT INTO command_receipts (id, technical_principal_ref, operation, "
                "command_key, outcome_ref, request_sha256) VALUES "
                "(gen_random_uuid(), 'p', 'orchestration.seal_handoff', :k, 'x', :h)"
            ),
            {"k": f"ok-{valor}", "h": valor},
        )
    with engine.connect() as conexao:
        assert conexao.execute(sa.text("SELECT count(*) FROM command_receipts")).scalar_one() == 1


def test_e72p27_head_unica_e_filha_de_a91d3f7c26be() -> None:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(Config("alembic.ini"))
    assert tuple(script.get_heads()) == (_MIGRATION_HEAD,)
    assert script.get_revision(_REVISION_E72_R2).down_revision == "d1f6a83b70c5"
    assert script.get_revision(_REVISION_E73).down_revision == _REVISION_E72_R2
    assert migrations.current_revision() == _MIGRATION_HEAD
