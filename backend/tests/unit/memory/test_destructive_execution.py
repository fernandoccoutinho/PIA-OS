"""
Invariantes dos contratos da composição destrutiva (`E4.9.9.d`).

```text
CORRECT_FACTORY_OUTPUT != SAFE_PUBLIC_RESULT_CONSTRUCTOR
```

O construtor **direto** de cada value object é exercitado, não apenas o
caminho feliz do serviço. É a décima ocorrência da lição que a
E4.9.9.c.1 pagou por último: invariante que só vive na fábrica é
contornável por quem chama a classe.
"""

import uuid
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta

import pytest

from app.memory.models.approval_enums import DestructiveOperation
from app.memory.models.approval_lifecycle_enums import ApprovalUsageRefusalReason
from app.memory.models.destructive_execution_enums import (
    AdapterContractViolation,
    PreConsumptionRefusalReason,
    SnapshotDivergenceField,
)
from app.memory.models.erasure_effect_enums import MaterialAttemptRefusalReason
from app.memory.models.erasure_enums import ErasureOutcome, ErasureTargetClass
from app.memory.models.target_resolution_enums import TargetResolutionRefusalReason
from app.memory.schemas.destructive_approval import SafeTargetSnapshot
from app.memory.schemas.destructive_execution import (
    SUFIXO_DE_RESOLUCAO,
    ApprovalConsumptionRefusal,
    DestructiveExecutionReport,
    DestructiveExecutionRequest,
    PartialExecutionEvidence,
    PreConsumptionRefusal,
    TargetAttempted,
    TargetNotAttempted,
    referencia_de_resolucao_de_governanca,
)
from tests.helpers.destructive_execution import (
    SUJEITO_A,
    SUJEITO_B,
    envelope,
    referencia,
    snapshot,
)

MOVER = DestructiveOperation.MOVE_TO_TRASH
INICIO = datetime(2026, 8, 19, 10, 0, tzinfo=UTC)
FIM = INICIO + timedelta(seconds=3)
MARCADOR = "SEGREDO-NAO-DEVE-VAZAR-7f3a"


def _atendido(**overrides: object) -> TargetAttempted:
    base: dict[str, object] = {
        "position": 0,
        "subject_coid": SUJEITO_A,
        "target_class": ErasureTargetClass.PIA_MANAGED_ARTIFACT,
        "outcome": ErasureOutcome.SUCCEEDED,
        "erasure_record_id": uuid.uuid4(),
        "attempted_at": INICIO,
        "completed_at": FIM,
    }
    base.update(overrides)
    return TargetAttempted(**base)  # type: ignore[arg-type]


def _nao_atendido(**overrides: object) -> TargetNotAttempted:
    base: dict[str, object] = {
        "position": 0,
        "subject_coid": SUJEITO_A,
        "reason": MaterialAttemptRefusalReason.ADAPTER_UNAVAILABLE,
        "observed_at": INICIO,
    }
    base.update(overrides)
    return TargetNotAttempted(**base)  # type: ignore[arg-type]


def _evidencia(**overrides: object) -> PartialExecutionEvidence:
    base: dict[str, object] = {
        "approval_id": uuid.uuid4(),
        "failed_position": 1,
        "subject_coid": SUJEITO_B,
        "attempts_observed": 1,
        "receipts_persisted": 1,
    }
    base.update(overrides)
    return PartialExecutionEvidence(**base)  # type: ignore[arg-type]


# ----------------------------------------------------------------------
# Helper puro da referência de resolução
# ----------------------------------------------------------------------


def test_u01_referencia_de_resolucao_tem_forma_canonica():
    identificador = uuid.uuid4()
    assert (
        referencia_de_resolucao_de_governanca(identificador)
        == f"approval:{identificador}:{SUFIXO_DE_RESOLUCAO}"
    )


def test_u02_referencia_de_resolucao_recusa_texto():
    """`str(uuid)` equivalente não é UUID — aceitar reabriria o canal livre."""
    with pytest.raises(TypeError, match="approval_id deve ser UUID"):
        referencia_de_resolucao_de_governanca(str(uuid.uuid4()))


def test_u03_referencia_de_resolucao_nao_e_digest_nem_hash():
    """O identificador aparece **literal**, sem transformação alguma.

    ```text
    RESOLUTION_REF != DIGEST
    ```
    """
    identificador = uuid.uuid4()
    referencia_montada = referencia_de_resolucao_de_governanca(identificador)
    assert str(identificador) in referencia_montada
    assert referencia_montada.count(":") == 2


def test_u04_referencia_de_resolucao_e_deterministica():
    identificador = uuid.uuid4()
    assert referencia_de_resolucao_de_governanca(
        identificador
    ) == referencia_de_resolucao_de_governanca(identificador)


# ----------------------------------------------------------------------
# DestructiveExecutionRequest
# ----------------------------------------------------------------------


def test_u05_request_valido_expoe_aprovacao_e_operacao():
    aprovado = envelope()
    pedido = DestructiveExecutionRequest(aprovado, (referencia(),))
    assert pedido.approval_id == aprovado.approval_id
    assert pedido.operation is MOVER


def test_u06_request_recusa_envelope_de_outro_tipo():
    with pytest.raises(TypeError, match="DestructiveApprovalEnvelope"):
        DestructiveExecutionRequest("aprovado", (referencia(),))  # type: ignore[arg-type]


@pytest.mark.parametrize("colecao", [list, set, tuple])
def test_u07_apenas_tupla_e_admissivel(colecao):
    """`set` perderia a ordem, e a ordem faz parte do binding."""
    itens = colecao([referencia()])
    if colecao is tuple:
        assert DestructiveExecutionRequest(envelope(), itens).references == itens
        return
    with pytest.raises(TypeError, match="tuple"):
        DestructiveExecutionRequest(envelope(), itens)  # type: ignore[arg-type]


def test_u08_lote_vazio_e_recusado():
    with pytest.raises(ValueError, match="ao menos uma referência"):
        DestructiveExecutionRequest(envelope(), ())


def test_u09_referencia_de_outro_tipo_e_recusada():
    with pytest.raises(TypeError, match=r"references\[0\]"):
        DestructiveExecutionRequest(envelope(), ("ref",))  # type: ignore[arg-type]


def test_u10_request_e_congelado():
    pedido = DestructiveExecutionRequest(envelope(), (referencia(),))
    with pytest.raises(FrozenInstanceError):
        pedido.references = ()  # type: ignore[misc]


def test_u11_repr_do_request_nao_expoe_referencia_opaca():
    """`DIRECT_REDACTION != COMPOSITE_REDACTION` — nada delegado."""
    pedido = DestructiveExecutionRequest(
        envelope(), (referencia(opaque_reference=f"ref:{MARCADOR}"),)
    )
    for texto in (repr(pedido), str(pedido)):
        assert MARCADOR not in texto
        assert "reference_count=1" in texto


def test_u12_replace_no_request_revalida():
    """`dataclasses.replace` passa pelo `__post_init__` — não é bypass."""
    pedido = DestructiveExecutionRequest(envelope(), (referencia(),))
    with pytest.raises(ValueError, match="ao menos uma referência"):
        replace(pedido, references=())


# ----------------------------------------------------------------------
# PreConsumptionRefusal — matriz completa
# ----------------------------------------------------------------------


def test_u13_recusa_de_cardinalidade_nao_tem_posicao():
    recusa = PreConsumptionRefusal(
        approval_id=uuid.uuid4(),
        operation=MOVER,
        reason=PreConsumptionRefusalReason.BATCH_CARDINALITY_MISMATCH,
    )
    assert recusa.position is None


def test_u14_cardinalidade_com_posicao_e_recusada():
    with pytest.raises(ValueError, match="não admite position"):
        PreConsumptionRefusal(
            approval_id=uuid.uuid4(),
            operation=MOVER,
            reason=PreConsumptionRefusalReason.BATCH_CARDINALITY_MISMATCH,
            position=0,
        )


def test_u15_governanca_incompleta_tambem_e_recusa_do_lote():
    recusa = PreConsumptionRefusal(
        approval_id=uuid.uuid4(),
        operation=MOVER,
        reason=PreConsumptionRefusalReason.GOVERNANCE_PROVENANCE_INCOMPLETE,
    )
    assert recusa.position is None


@pytest.mark.parametrize(
    "motivo",
    [
        PreConsumptionRefusalReason.DUPLICATE_SUBJECT_IN_BATCH,
        PreConsumptionRefusalReason.REFERENCE_DOES_NOT_MATCH_APPROVED_TARGET,
    ],
)
def test_u16_recusa_por_alvo_exige_posicao(motivo):
    with pytest.raises(ValueError, match="exige position"):
        PreConsumptionRefusal(approval_id=uuid.uuid4(), operation=MOVER, reason=motivo)


def test_u17_divergencia_exige_campo_divergente():
    with pytest.raises(ValueError, match="exige diverged_field"):
        PreConsumptionRefusal(
            approval_id=uuid.uuid4(),
            operation=MOVER,
            reason=PreConsumptionRefusalReason.FRESH_SNAPSHOT_DIVERGED,
            position=0,
        )


def test_u18_campo_divergente_fora_da_divergencia_e_recusado():
    with pytest.raises(ValueError, match="não admite diverged_field"):
        PreConsumptionRefusal(
            approval_id=uuid.uuid4(),
            operation=MOVER,
            reason=PreConsumptionRefusalReason.DUPLICATE_SUBJECT_IN_BATCH,
            position=0,
            diverged_field=SnapshotDivergenceField.VERSION_ETAG,
        )


def test_u19_recusa_de_resolucao_exige_motivo_tipado():
    with pytest.raises(ValueError, match="exige resolution_refusal"):
        PreConsumptionRefusal(
            approval_id=uuid.uuid4(),
            operation=MOVER,
            reason=PreConsumptionRefusalReason.TARGET_RESOLUTION_REFUSED,
            position=0,
        )


def test_u20_motivo_de_resolucao_fora_do_seu_caso_e_recusado():
    with pytest.raises(ValueError, match="não admite resolution_refusal"):
        PreConsumptionRefusal(
            approval_id=uuid.uuid4(),
            operation=MOVER,
            reason=PreConsumptionRefusalReason.DUPLICATE_SUBJECT_IN_BATCH,
            position=0,
            resolution_refusal=TargetResolutionRefusalReason.STALE_RESOLUTION,
        )


def test_u21_motivo_textual_equivalente_nao_e_membro():
    with pytest.raises(TypeError, match="PreConsumptionRefusalReason"):
        PreConsumptionRefusal(
            approval_id=uuid.uuid4(),
            operation=MOVER,
            reason="batch_cardinality_mismatch",  # type: ignore[arg-type]
        )


def test_u22_posicao_negativa_e_recusada():
    with pytest.raises(ValueError, match="position deve ser >= 0"):
        PreConsumptionRefusal(
            approval_id=uuid.uuid4(),
            operation=MOVER,
            reason=PreConsumptionRefusalReason.DUPLICATE_SUBJECT_IN_BATCH,
            position=-1,
        )


def test_u23_bool_nao_e_posicao():
    """`True` é `int` em Python, e não é índice de lote."""
    with pytest.raises(TypeError, match="position deve ser int"):
        PreConsumptionRefusal(
            approval_id=uuid.uuid4(),
            operation=MOVER,
            reason=PreConsumptionRefusalReason.DUPLICATE_SUBJECT_IN_BATCH,
            position=True,
        )


# ----------------------------------------------------------------------
# ApprovalConsumptionRefusal
# ----------------------------------------------------------------------


def test_u24_recusa_de_consumo_usa_vocabulario_da_e4_9_9_a():
    recusa = ApprovalConsumptionRefusal(
        approval_id=uuid.uuid4(),
        operation=MOVER,
        reason=ApprovalUsageRefusalReason.ALREADY_CONSUMED,
    )
    assert recusa.reason is ApprovalUsageRefusalReason.ALREADY_CONSUMED


def test_u25_recusa_de_consumo_recusa_motivo_de_outra_familia():
    with pytest.raises(TypeError, match="ApprovalUsageRefusalReason"):
        ApprovalConsumptionRefusal(
            approval_id=uuid.uuid4(),
            operation=MOVER,
            reason=PreConsumptionRefusalReason.BATCH_CARDINALITY_MISMATCH,  # type: ignore[arg-type]
        )


# ----------------------------------------------------------------------
# Desfecho por alvo
# ----------------------------------------------------------------------


def test_u26_alvo_nao_tentado_nao_tem_onde_guardar_recibo():
    """`NO_MATERIAL_ATTEMPT -> NO_ERASURE_RECORD`, por ausência de campo."""
    campos = set(_nao_atendido().__dataclass_fields__)
    assert "erasure_record_id" not in campos


def test_u27_alvo_tentado_exige_recibo():
    with pytest.raises(TypeError):
        TargetAttempted(  # type: ignore[call-arg]
            position=0,
            subject_coid=SUJEITO_A,
            target_class=ErasureTargetClass.PIA_MANAGED_ARTIFACT,
            outcome=ErasureOutcome.SUCCEEDED,
            attempted_at=INICIO,
            completed_at=FIM,
        )


def test_u28_classe_sem_conteudo_nao_e_tentativa_material():
    with pytest.raises(ValueError, match="não é conteúdo apagável"):
        _atendido(target_class=ErasureTargetClass.COGNITIVE_METADATA_RECORD)


def test_u29_conclusao_antes_do_inicio_e_recusada():
    with pytest.raises(ValueError, match="completed_at anterior"):
        _atendido(attempted_at=FIM, completed_at=INICIO)


def test_u30_instante_ingenuo_e_recusado():
    with pytest.raises(ValueError, match="timezone-aware"):
        _nao_atendido(observed_at=datetime(2026, 8, 19, 10, 0))


def test_u31_motivo_de_nao_tentativa_e_tipado():
    with pytest.raises(TypeError, match="MaterialAttemptRefusalReason"):
        _nao_atendido(reason="adapter_unavailable")


def test_u32_desfecho_por_alvo_e_congelado():
    with pytest.raises(FrozenInstanceError):
        _atendido().outcome = ErasureOutcome.FAILED  # type: ignore[misc]


# ----------------------------------------------------------------------
# DestructiveExecutionReport
# ----------------------------------------------------------------------


def test_u33_relatorio_conta_tentativas_e_recibos():
    relatorio = DestructiveExecutionReport(
        approval_id=uuid.uuid4(),
        operation=MOVER,
        consumed_at=INICIO,
        targets=(_atendido(), _nao_atendido(position=1, subject_coid=SUJEITO_B)),
    )
    assert relatorio.attempts_observed == 1
    assert relatorio.not_attempted == 1
    assert len(relatorio.receipts_persisted) == 1


def test_u34_relatorio_vazio_e_recusado():
    with pytest.raises(ValueError, match="ao menos um alvo"):
        DestructiveExecutionReport(
            approval_id=uuid.uuid4(), operation=MOVER, consumed_at=INICIO, targets=()
        )


def test_u35_posicao_fora_de_ordem_e_recusada():
    """A posição é a do lote aprovado e **não** é reordenada."""
    with pytest.raises(ValueError, match="declara position"):
        DestructiveExecutionReport(
            approval_id=uuid.uuid4(),
            operation=MOVER,
            consumed_at=INICIO,
            targets=(_atendido(position=1),),
        )


def test_u36_sujeito_repetido_no_relatorio_e_recusado():
    with pytest.raises(ValueError, match="Sujeito repetido|sujeito repetido"):
        DestructiveExecutionReport(
            approval_id=uuid.uuid4(),
            operation=MOVER,
            consumed_at=INICIO,
            targets=(_atendido(), _atendido(position=1)),
        )


def test_u37_recibo_repetido_e_recusado():
    """Um recibo registra exatamente uma tentativa observada."""
    recibo = uuid.uuid4()
    with pytest.raises(ValueError, match="[Rr]ecibo repetido"):
        DestructiveExecutionReport(
            approval_id=uuid.uuid4(),
            operation=MOVER,
            consumed_at=INICIO,
            targets=(
                _atendido(erasure_record_id=recibo),
                _atendido(position=1, subject_coid=SUJEITO_B, erasure_record_id=recibo),
            ),
        )


def test_u38_alvo_de_outro_tipo_no_relatorio_e_recusado():
    with pytest.raises(TypeError, match=r"targets\[0\]"):
        DestructiveExecutionReport(
            approval_id=uuid.uuid4(),
            operation=MOVER,
            consumed_at=INICIO,
            targets=("apagado",),  # type: ignore[arg-type]
        )


def test_u39_colecao_mutavel_no_relatorio_e_recusada():
    with pytest.raises(TypeError, match="tuple"):
        DestructiveExecutionReport(
            approval_id=uuid.uuid4(),
            operation=MOVER,
            consumed_at=INICIO,
            targets=[_atendido()],  # type: ignore[arg-type]
        )


def test_u40_recibos_preservam_a_ordem_do_lote():
    primeiro, segundo = uuid.uuid4(), uuid.uuid4()
    relatorio = DestructiveExecutionReport(
        approval_id=uuid.uuid4(),
        operation=MOVER,
        consumed_at=INICIO,
        targets=(
            _atendido(erasure_record_id=primeiro),
            _atendido(position=1, subject_coid=SUJEITO_B, erasure_record_id=segundo),
        ),
    )
    assert relatorio.receipts_persisted == (primeiro, segundo)


def test_u41_replace_no_relatorio_revalida():
    relatorio = DestructiveExecutionReport(
        approval_id=uuid.uuid4(), operation=MOVER, consumed_at=INICIO, targets=(_atendido(),)
    )
    with pytest.raises(ValueError, match="ao menos um alvo"):
        replace(relatorio, targets=())


# ----------------------------------------------------------------------
# PartialExecutionEvidence
# ----------------------------------------------------------------------


def test_u42_evidencia_parcial_conta_o_que_era_fato():
    evidencia = _evidencia(attempts_observed=2, receipts_persisted=2)
    assert evidencia.attempts_observed == 2
    assert evidencia.receipts_persisted == 2


def test_u43_recibos_nao_podem_exceder_tentativas():
    with pytest.raises(ValueError, match="excedem tentativas"):
        _evidencia(attempts_observed=1, receipts_persisted=2)


def test_u44_contagem_negativa_e_recusada():
    with pytest.raises(ValueError, match="não pode ser negativo"):
        _evidencia(attempts_observed=-1, receipts_persisted=0)


def test_u45_evidencia_aceita_recibo_faltante_apos_efeito_observado():
    """`PIA-8049` precisa exprimir efeito observado **sem** recibo."""
    evidencia = _evidencia(attempts_observed=1, receipts_persisted=0)
    assert evidencia.receipts_persisted < evidencia.attempts_observed


# ----------------------------------------------------------------------
# Confidencialidade — direta e composta
# ----------------------------------------------------------------------


def test_u46_nenhum_resultado_expoe_localizador_ou_capacidade():
    """Redação medida com marcador real em canais compostos."""
    aprovado = envelope()
    resultados = (
        PreConsumptionRefusal(
            approval_id=aprovado.approval_id,
            operation=MOVER,
            reason=PreConsumptionRefusalReason.FRESH_SNAPSHOT_DIVERGED,
            position=0,
            diverged_field=SnapshotDivergenceField.VERSION_ETAG,
        ),
        ApprovalConsumptionRefusal(
            approval_id=aprovado.approval_id,
            operation=MOVER,
            reason=ApprovalUsageRefusalReason.EXPIRED,
        ),
        DestructiveExecutionReport(
            approval_id=aprovado.approval_id,
            operation=MOVER,
            consumed_at=INICIO,
            targets=(_atendido(),),
        ),
        _evidencia(),
    )
    for resultado in resultados:
        for texto in (repr(resultado), str(resultado)):
            for proibido in ("locator", "s3://", "capability", "delete_object", MARCADOR):
                assert proibido not in texto, (type(resultado).__name__, proibido)


def test_u47_o_campo_divergente_e_nome_e_nunca_valor():
    """`FIELD_NAME_IS_SAFE · FIELD_VALUE_IS_NOT`."""
    recusa = PreConsumptionRefusal(
        approval_id=uuid.uuid4(),
        operation=MOVER,
        reason=PreConsumptionRefusalReason.FRESH_SNAPSHOT_DIVERGED,
        position=0,
        diverged_field=SnapshotDivergenceField.VERSION_ETAG,
    )
    assert recusa.diverged_field.value == "version_etag"
    assert 'W/"v1"' not in repr(recusa)


def test_u48_os_sete_campos_do_binding_tem_rotulo_proprio():
    """A enumeração cobre exatamente os campos do snapshot aprovado."""
    rotulos = {membro.value for membro in SnapshotDivergenceField}
    assert rotulos == set(SafeTargetSnapshot.__dataclass_fields__)


def test_u49_violacoes_do_adaptador_sao_tres_e_disjuntas():
    assert {membro.value for membro in AdapterContractViolation} == {
        "approval_mismatch",
        "subject_mismatch",
        "target_class_mismatch",
    }


def test_u50_nenhum_vocabulario_tem_membro_coringa():
    """`UNKNOWN`/`OTHER`/`ERROR` absorveriam o caso que ninguém previu."""
    for enumeracao in (
        PreConsumptionRefusalReason,
        SnapshotDivergenceField,
        AdapterContractViolation,
    ):
        nomes = {membro.name for membro in enumeracao}
        assert not nomes & {"UNKNOWN", "OTHER", "ERROR", "UNSPECIFIED"}


def test_u51_snapshot_aprovado_e_o_lote_do_envelope():
    """Guarda de premissa: os sete campos comparados vêm do envelope."""
    aprovado = envelope(alvos=(snapshot(),))
    assert aprovado.proposal.targets[0] == snapshot()


# ----------------------------------------------------------------------
# Tipos exatos — nenhuma equivalência por string ou por valor
# ----------------------------------------------------------------------
#
# ```text
# STRING_EQUIVALENT != ENUM_MEMBER
# ```
#
# Cada ramo de tipo abaixo é alcançado pelo construtor PÚBLICO, com o
# tipo errado passado diretamente. Sem estes casos, um `TypeError`
# nunca exercitado poderia estar quebrado sem que ninguém soubesse — e
# a exigência de 100% nos arquivos novos existe exatamente para isso.


def test_u52_uuid_textual_nao_e_uuid():
    with pytest.raises(TypeError, match="approval_id deve ser UUID"):
        ApprovalConsumptionRefusal(
            approval_id=str(uuid.uuid4()),  # type: ignore[arg-type]
            operation=MOVER,
            reason=ApprovalUsageRefusalReason.EXPIRED,
        )


@pytest.mark.parametrize(
    "construir",
    [
        lambda: PreConsumptionRefusal(
            approval_id=uuid.uuid4(),
            operation="move_to_trash",
            reason=PreConsumptionRefusalReason.BATCH_CARDINALITY_MISMATCH,
        ),
        lambda: ApprovalConsumptionRefusal(
            approval_id=uuid.uuid4(),
            operation="move_to_trash",
            reason=ApprovalUsageRefusalReason.EXPIRED,
        ),
        lambda: DestructiveExecutionReport(
            approval_id=uuid.uuid4(),
            operation="move_to_trash",
            consumed_at=INICIO,
            targets=(_atendido(),),
        ),
    ],
)
def test_u53_operacao_textual_equivalente_nao_e_membro(construir):
    with pytest.raises(TypeError, match="operation deve ser um DestructiveOperation"):
        construir()


def test_u54_campo_divergente_de_outro_vocabulario_e_recusado():
    with pytest.raises(TypeError, match="diverged_field deve ser"):
        PreConsumptionRefusal(
            approval_id=uuid.uuid4(),
            operation=MOVER,
            reason=PreConsumptionRefusalReason.FRESH_SNAPSHOT_DIVERGED,
            position=0,
            diverged_field="version_etag",  # type: ignore[arg-type]
        )


def test_u55_motivo_de_resolucao_de_outro_vocabulario_e_recusado():
    with pytest.raises(TypeError, match="resolution_refusal deve ser"):
        PreConsumptionRefusal(
            approval_id=uuid.uuid4(),
            operation=MOVER,
            reason=PreConsumptionRefusalReason.TARGET_RESOLUTION_REFUSED,
            position=0,
            resolution_refusal="stale_resolution",  # type: ignore[arg-type]
        )


def test_u56_classe_de_alvo_textual_nao_e_membro():
    with pytest.raises(TypeError, match="target_class deve ser"):
        _atendido(target_class="pia_managed_artifact")


def test_u57_desfecho_textual_nao_e_membro():
    """`ErasureOutcome` tem fonte única desde a E4.9.5."""
    with pytest.raises(TypeError, match="outcome deve ser um ErasureOutcome"):
        _atendido(outcome="succeeded")


def test_u58_contagem_nao_inteira_na_evidencia_e_recusada():
    with pytest.raises(TypeError, match="attempts_observed deve ser int"):
        _evidencia(attempts_observed="1")


# ----------------------------------------------------------------------
# GovernanceProvenance — o estreitamento que evita `cast`
# ----------------------------------------------------------------------


def test_u59_proveniencia_exige_os_quatro_valores():
    from app.memory.schemas.destructive_execution import GovernanceProvenance

    provenienca = GovernanceProvenance(
        policy_id=uuid.uuid4(),
        policy_key="gov.erasure",
        policy_version=3,
        matched_rule_id="rule-1",
    )
    assert provenienca.matched_rule_id == "rule-1"


@pytest.mark.parametrize(
    ("campo", "valor", "erro"),
    [
        ("policy_id", "nao-e-uuid", TypeError),
        ("policy_key", 1, TypeError),
        ("policy_key", "   ", ValueError),
        ("matched_rule_id", None, TypeError),
        ("matched_rule_id", "", ValueError),
        ("policy_version", "3", TypeError),
        ("policy_version", True, TypeError),
        ("policy_version", 0, ValueError),
    ],
)
def test_u60_proveniencia_recusa_valor_invalido(campo, valor, erro):
    from app.memory.schemas.destructive_execution import GovernanceProvenance

    base: dict[str, object] = {
        "policy_id": uuid.uuid4(),
        "policy_key": "gov.erasure",
        "policy_version": 3,
        "matched_rule_id": "rule-1",
    }
    base[campo] = valor
    with pytest.raises(erro):
        GovernanceProvenance(**base)  # type: ignore[arg-type]


def test_u61_a_regra_textual_nao_e_convertida_na_proveniencia():
    """`OPAQUE_RULE_REFERENCE != UUID` — atravessa byte a byte."""
    from app.memory.schemas.destructive_execution import GovernanceProvenance

    regra = "rule-Ação/2026 v1"
    assert (
        GovernanceProvenance(
            policy_id=uuid.uuid4(),
            policy_key="gov.erasure",
            policy_version=1,
            matched_rule_id=regra,
        ).matched_rule_id
        == regra
    )
