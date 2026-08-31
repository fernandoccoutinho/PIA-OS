"""
Testes unitários da fundação `ErasureRecord` (`E4.9.5`).

O que estes testes protegem, acima de tudo: que o recibo só saiba
registrar o que foi **observado**, e que nada nele possa guardar o
conteúdo que ele diz ter sido apagado.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.memory.errors.codes import PIA_8041_ERASURE_RECORD_IMMUTABLE
from app.memory.errors.exceptions import ErasureRecordImmutableError
from app.memory.models.erasure_enums import ErasureOutcome, ErasureTargetClass
from app.memory.models.erasure_record import (
    MAX_FAILURE_CODE_LENGTH,
    MAX_IDENTIFIER_LENGTH,
    ErasureRecord,
)
from app.memory.repositories.erasure_record_repository import ErasureRecordRepository
from app.memory.schemas.erasure_record import ErasureRecordAppend, ErasureRecordView

ATTEMPTED = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)
COMPLETED = ATTEMPTED + timedelta(seconds=5)


def entrada(**overrides: object) -> ErasureRecordAppend:
    """Entrada válida mínima; `overrides` altera um campo por vez."""
    base: dict[str, object] = {
        "subject_identifier": "coid:9f1c",
        "target_class": ErasureTargetClass.PIA_MANAGED_ARTIFACT,
        "scope_token": "scope:controlled-copies-v1",
        "outcome": ErasureOutcome.SUCCEEDED,
        "governance_policy_id": uuid.uuid4(),
        "governance_policy_key": "gov.erasure",
        "governance_policy_version": 3,
        # E4.9.9.d: OPAQUE_RULE_REFERENCE != UUID. A fonte real é
        # `GovernanceResolution.matched_rule_id`, que é `str`.
        "governance_rule_id": "rule-1",
        "governance_resolution_ref": "res:7c2a",
        "approval_ref": "appr:2b19",
        "executor_ref": "exec:local-artifact-store",
        "attempted_at": ATTEMPTED,
        "completed_at": COMPLETED,
    }
    base.update(overrides)
    return ErasureRecordAppend(**base)  # type: ignore[arg-type]


# --- Enums ---------------------------------------------------------------


def test_u01_erasure_outcome_tem_exatamente_tres_membros():
    """`PENDING`/`PROPOSED`/`APPROVED`/`SCHEDULED` são proibidos (E4.9.0)."""
    assert [o.value for o in ErasureOutcome] == ["succeeded", "failed", "partial"]
    for proibido in ("PENDING", "PROPOSED", "APPROVED", "SCHEDULED"):
        assert proibido not in ErasureOutcome.__members__


def test_u02_erasure_target_class_tem_as_quatro_classes_da_e4_9_1():
    assert [c.value for c in ErasureTargetClass] == [
        "pia_managed_artifact",
        "authorized_connector_referent",
        "cognitive_metadata_record",
        "unresolved_opaque_reference",
    ]


def test_u03_enums_sao_strings_estaveis():
    assert ErasureOutcome.PARTIAL == "partial"
    assert ErasureTargetClass.COGNITIVE_METADATA_RECORD == "cognitive_metadata_record"


# --- Construção válida ---------------------------------------------------


@pytest.mark.parametrize(
    ("outcome", "failure_code"),
    [
        (ErasureOutcome.SUCCEEDED, None),
        (ErasureOutcome.FAILED, "provider_denied"),
        (ErasureOutcome.PARTIAL, "replica_unverified"),
    ],
)
def test_u04_constroi_para_os_tres_outcomes(outcome, failure_code):
    e = entrada(outcome=outcome, failure_code=failure_code)
    assert e.outcome is outcome
    assert e.failure_code == failure_code


def test_u05_entrada_e_congelada():
    e = entrada()
    with pytest.raises(ValidationError):
        e.outcome = ErasureOutcome.FAILED  # type: ignore[misc]


def test_u06_campo_extra_e_rejeitado():
    """`extra="forbid"` fecha a porta do campo livre por acréscimo."""
    with pytest.raises(ValidationError):
        entrada(effect_digest="sha256:deadbeef")


# --- Strings opacas ------------------------------------------------------


@pytest.mark.parametrize(
    "campo",
    [
        "subject_identifier",
        "scope_token",
        "governance_policy_key",
        "governance_resolution_ref",
        "approval_ref",
        "executor_ref",
    ],
)
@pytest.mark.parametrize("valor", ["", "   ", "\t"])
def test_u07_strings_vazias_ou_brancas_recusadas(campo, valor):
    with pytest.raises(ValidationError):
        entrada(**{campo: valor})


@pytest.mark.parametrize("valor", ["a\x00b", "linha\nquebrada", "tab\there", "del\x7f"])
def test_u08_caracteres_de_controle_recusados(valor):
    with pytest.raises(ValidationError):
        entrada(subject_identifier=valor)


def test_u09_tamanho_maximo_respeitado():
    entrada(subject_identifier="x" * MAX_IDENTIFIER_LENGTH)
    with pytest.raises(ValidationError):
        entrada(subject_identifier="x" * (MAX_IDENTIFIER_LENGTH + 1))


def test_u10_failure_code_tem_teto_proprio():
    entrada(outcome=ErasureOutcome.FAILED, failure_code="f" * MAX_FAILURE_CODE_LENGTH)
    with pytest.raises(ValidationError):
        entrada(outcome=ErasureOutcome.FAILED, failure_code="f" * (MAX_FAILURE_CODE_LENGTH + 1))


def test_u11_retention_key_em_branco_recusada():
    with pytest.raises(ValidationError):
        entrada(
            retention_policy_id=uuid.uuid4(),
            retention_policy_key="  ",
            retention_policy_version=1,
        )


# --- Tempo ---------------------------------------------------------------


@pytest.mark.parametrize("campo", ["attempted_at", "completed_at"])
def test_u12_datetime_naive_recusado(campo):
    with pytest.raises(ValidationError):
        entrada(**{campo: datetime(2026, 8, 17, 12, 0)})


def test_u13_completed_antes_de_attempted_recusado():
    with pytest.raises(ValidationError):
        entrada(completed_at=ATTEMPTED - timedelta(seconds=1))


def test_u14_completed_igual_a_attempted_aceito():
    """Efeito instantâneo observado é legítimo; a constraint é `>=`."""
    assert entrada(completed_at=ATTEMPTED).completed_at == ATTEMPTED


# --- Matriz outcome × failure_code --------------------------------------


def test_u15_succeeded_com_failure_code_recusado():
    with pytest.raises(ValidationError):
        entrada(outcome=ErasureOutcome.SUCCEEDED, failure_code="oops")


@pytest.mark.parametrize("outcome", [ErasureOutcome.FAILED, ErasureOutcome.PARTIAL])
def test_u16_failed_e_partial_exigem_failure_code(outcome):
    with pytest.raises(ValidationError):
        entrada(outcome=outcome, failure_code=None)


# --- Trio de retenção all-or-none ---------------------------------------


def test_u17_trio_todo_nulo_aceito():
    e = entrada()
    assert (e.retention_policy_id, e.retention_policy_key, e.retention_policy_version) == (
        None,
        None,
        None,
    )


def test_u18_trio_todo_preenchido_aceito():
    e = entrada(
        retention_policy_id=uuid.uuid4(),
        retention_policy_key="ret.default",
        retention_policy_version=2,
    )
    assert e.retention_policy_version == 2


@pytest.mark.parametrize(
    "parcial",
    [
        {"retention_policy_id": uuid.uuid4()},
        {"retention_policy_key": "ret.default"},
        {"retention_policy_version": 1},
        {"retention_policy_id": uuid.uuid4(), "retention_policy_key": "ret.default"},
        {"retention_policy_key": "ret.default", "retention_policy_version": 1},
    ],
)
def test_u19_trio_parcial_recusado(parcial):
    with pytest.raises(ValidationError):
        entrada(**parcial)


# --- Versões -------------------------------------------------------------


@pytest.mark.parametrize("valor", [0, -1])
def test_u20_versao_de_governanca_deve_ser_positiva(valor):
    with pytest.raises(ValidationError):
        entrada(governance_policy_version=valor)


@pytest.mark.parametrize("valor", [0, -3])
def test_u21_versao_de_retencao_deve_ser_positiva(valor):
    with pytest.raises(ValidationError):
        entrada(
            retention_policy_id=uuid.uuid4(),
            retention_policy_key="ret.default",
            retention_policy_version=valor,
        )


# --- Modelo: ausência de campos proibidos -------------------------------


def test_u22_modelo_nao_tem_campo_livre():
    """Prova estrutural: nenhuma coluna capaz de guardar conteúdo.

    Um campo livre acabaria recebendo o trecho "só para contexto", e o
    recibo viraria o último lugar onde o apagado sobreviveu.
    """
    proibidos = {
        "metadata",
        "meta",
        "details",
        "detail",
        "payload",
        "message",
        "description",
        "notes",
        "content",
        "body",
        "prompt",
        "response",
        "locator",
        "uri",
        "url",
        "path",
        "bucket",
        "key",
        "payload_ref",
        "source_ref",
        "evidence_refs",
        "input_refs",
        "output_refs",
        "effect_digest",
        "digest",
        "hash",
        "credential",
        "token",
        "secret",
    }
    colunas = {c.name for c in ErasureRecord.__table__.columns}
    assert colunas & proibidos == set()


def test_u23_modelo_nao_tem_coluna_json():
    from sqlalchemy import JSON
    from sqlalchemy.dialects.postgresql import JSONB

    for coluna in ErasureRecord.__table__.columns:
        assert not isinstance(coluna.type, JSON | JSONB), coluna.name


def test_u24_sujeito_nao_tem_foreign_key():
    """`SUBJECT_LINK = HISTORICAL_IDENTIFIER_NOT_FK`."""
    assert ErasureRecord.__table__.foreign_keys == set()
    assert ErasureRecord.__table__.c.subject_identifier.foreign_keys == set()


def test_u25_completed_at_e_not_null():
    """Nullable admitiria um `PENDING` disfarçado."""
    assert ErasureRecord.__table__.c.completed_at.nullable is False


def test_u26_view_e_congelada_e_nao_expoe_campo_extra():
    v = ErasureRecordView(
        id=uuid.uuid4(),
        subject_identifier="coid:9f1c",
        target_class=ErasureTargetClass.PIA_MANAGED_ARTIFACT,
        scope_token="scope:x",
        outcome=ErasureOutcome.SUCCEEDED,
        governance_policy_id=uuid.uuid4(),
        governance_policy_key="gov.erasure",
        governance_policy_version=1,
        governance_rule_id="rule-1",
        governance_resolution_ref="res:1",
        approval_ref="appr:1",
        executor_ref="exec:1",
        attempted_at=ATTEMPTED,
        completed_at=COMPLETED,
        retention_policy_id=None,
        retention_policy_key=None,
        retention_policy_version=None,
        failure_code=None,
    )
    with pytest.raises(ValidationError):
        v.outcome = ErasureOutcome.FAILED  # type: ignore[misc]
    assert set(v.model_dump()) == {c.name for c in ErasureRecord.__table__.columns} - {
        "created_at",
        "updated_at",
    }


# --- Imutabilidade: erro e repositório ----------------------------------


def test_u27_erro_de_imutabilidade_usa_pia_8041():
    rid = uuid.uuid4()
    exc = ErasureRecordImmutableError(rid, operation="update")
    assert exc.error_code is PIA_8041_ERASURE_RECORD_IMMUTABLE
    assert exc.error_code.code == "PIA-8041"
    assert "imutável" in str(exc)
    assert exc.detail == {"record_id": str(rid), "operation": "update"}


def test_u28_erro_aceita_id_nulo():
    exc = ErasureRecordImmutableError(None, operation="bulk_update")
    assert exc.detail == {"record_id": None, "operation": "bulk_update"}


@pytest.mark.parametrize(
    "operacao", ["update", "delete", "soft_delete", "bulk_update", "bulk_delete"]
)
def test_u29_repositorio_recusa_toda_mutacao(operacao):
    repo = ErasureRecordRepository.__new__(ErasureRecordRepository)
    alvo = ErasureRecord(id=uuid.uuid4())
    with pytest.raises(ErasureRecordImmutableError) as info:
        getattr(repo, operacao)(alvo)
    assert info.value.operation == operacao


def test_u30_append_observed_recusa_dicionario_livre():
    """Kwargs livres aceitariam o campo que o modelo existe para não ter."""
    repo = ErasureRecordRepository.__new__(ErasureRecordRepository)
    with pytest.raises(TypeError):
        repo.append_observed({"subject_identifier": "coid:1"})  # type: ignore[arg-type]


@pytest.mark.parametrize(("limit", "offset"), [(0, 0), (-1, 0), (1, -1)])
def test_u31_paginacao_rejeita_parametros_invalidos(limit, offset):
    repo = ErasureRecordRepository.__new__(ErasureRecordRepository)
    with pytest.raises(ValueError):
        repo._listar(limit=limit, offset=offset)


def test_u32_validador_de_retention_key_aceita_none_explicito():
    """Passar `None` explicitamente exercita o ramo do validador.

    Pydantic só roda o `field_validator` quando o campo é fornecido —
    confiar no default deixaria este caminho sem cobertura.
    """
    e = entrada(retention_policy_key=None, failure_code=None)
    assert e.retention_policy_key is None
