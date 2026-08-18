"""
Testes unitários da aprovação persistente (`E4.9.9.a`).

```text
PERSISTED_APPROVAL != AUTHENTICATED_USER
PERSISTED_APPROVAL != EXECUTION
APPROVAL_RECORD    != ERASURE_RECORD
```

Estes testes cobrem vocabulários, forma do schema e ausência de campo
proibido. O comportamento concorrente e as garantias de banco vivem em
`tests/integration/memory/test_approval_record_integration.py`, porque
`clock_timestamp()` e trigger só existem no PostgreSQL.
"""

import dataclasses
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.memory.models.approval_enums import (
    AssuranceLevel,
    DestructiveOperation,
    ImpactVolumeKind,
    InputChannel,
    VoiceReviewState,
)
from app.memory.models.approval_lifecycle_enums import (
    ApprovalLifecycleState,
    ApprovalUsageRefusalReason,
    GovernanceItemKind,
)
from app.memory.models.approval_record import (
    ApprovalRecord,
    ApprovalRecordGovernanceItem,
    ApprovalRecordTarget,
)
from app.memory.models.erasure_enums import ErasureTargetClass
from app.memory.models.governance_enums import (
    CognitiveOperation,
    CriticalCapability,
    GovernanceOutcome,
)
from app.memory.models.target_resolution_enums import (
    LegacyProtectionState,
    ReferenceOrigin,
)
from app.memory.schemas.destructive_approval import (
    ApprovalContext,
    DestructiveApprovalEnvelope,
    DestructiveApprovalProposal,
    IdentityEvidence,
    PresentedImpact,
    SafeTargetSnapshot,
    SafeVoiceProvenance,
)
from app.memory.schemas.erasure_target import (
    ControlScope,
    CustodyNamespace,
    ReferenceProvenance,
)
from app.memory.schemas.governance import GovernanceResolution

TENANT = uuid.UUID("00000000-0000-0000-0000-00000000aa01")
WORKSPACE = uuid.UUID("00000000-0000-0000-0000-00000000aa02")
DOMINIO = uuid.UUID("00000000-0000-0000-0000-00000000aa03")
PRINCIPAL = "principal:humano-1"
FINALIDADE = "purpose:remocao-titular"
ANTES = datetime(2026, 8, 18, 10, 0, tzinfo=UTC)
DEPOIS = datetime(2026, 8, 18, 18, 0, tzinfo=UTC)


def resolucao(**over: object) -> GovernanceResolution:
    base: dict[str, object] = {
        "outcome": GovernanceOutcome.ADMISSIBLE,
        "operation": CognitiveOperation.LEGAL_ERASURE,
        "context_domain_ids": (DOMINIO,),
        "context_actor_ref": PRINCIPAL,
        "context_purpose": FINALIDADE,
        "safety_boundary_version": 1,
        "safety_rationale": "titular pediu remoção",
        "policy_key": "ret.default",
        "policy_version": 1,
        "policy_id": uuid.UUID("00000000-0000-0000-0000-00000000bb01"),
        "matched_rule_id": "rule-1",
        "admissible_alternatives": ("mover para lixeira",),
        "constraints": ("preservar rastro causal",),
        "declared_preservations": ("registro histórico",),
        "declared_losses": ("conteúdo do artefato",),
    }
    base.update(over)
    return GovernanceResolution(**base)  # type: ignore[arg-type]


def snapshot(indice: int = 0, **over: object) -> SafeTargetSnapshot:
    base: dict[str, object] = {
        "target_class": ErasureTargetClass.PIA_MANAGED_ARTIFACT,
        "subject_coid": uuid.UUID(f"00000000-0000-0000-0000-0000000{indice:05d}"),
        "control_scope": ControlScope(WORKSPACE, TENANT, PRINCIPAL),
        "custody_namespace": CustodyNamespace("pia-storage", f"workspace/w1/{indice}"),
        "origin": ReferenceProvenance(ReferenceOrigin.OUTPUT_REFS, indice),
        # Escolha CONSCIENTE por alvo — o lote misto é exercitado em u07.
        "legacy_protection_state": LegacyProtectionState.NOT_PROTECTED,
        "version_etag": f'W/"v{indice}"',
    }
    base.update(over)
    return SafeTargetSnapshot(**base)  # type: ignore[arg-type]


def envelope(
    *,
    operacao: DestructiveOperation = DestructiveOperation.PERMANENT_ERASURE,
    assurance: AssuranceLevel = AssuranceLevel.STEP_UP_VERIFIED,
    alvos: tuple[SafeTargetSnapshot, ...] | None = None,
    canal: InputChannel = InputChannel.TEXT,
    revisao: VoiceReviewState = VoiceReviewState.NOT_APPLICABLE,
    approval_id: uuid.UUID | None = None,
    nonce: uuid.UUID | None = None,
    governanca: GovernanceResolution | None = None,
    impacto: PresentedImpact | None = None,
) -> DestructiveApprovalEnvelope:
    """Envelope **integralmente válido** pelos construtores públicos.

    Nenhum estado é fabricado por `object.__setattr__`, monkeypatch ou
    bypass: toda variante usada nos testes de divergência é um envelope
    que a E4.9.8.1 aceitaria por si.
    """
    from app.memory.schemas.destructive_approval import OPERACAO_DE_GOVERNANCA

    alvos = alvos or (snapshot(0), snapshot(1))
    contexto = ApprovalContext(TENANT, WORKSPACE, DOMINIO, FINALIDADE)
    proveniencia = SafeVoiceProvenance(canal, revisao)
    proposta = DestructiveApprovalProposal(
        operation=operacao,
        targets=alvos,
        impact=impacto or PresentedImpact(len(alvos), ImpactVolumeKind.KNOWN, 4096),
        governance_resolution=governanca or resolucao(operation=OPERACAO_DE_GOVERNANCA[operacao]),
        context=contexto,
        provenance=proveniencia,
        blockers=(),
        materialized_at=ANTES,
    )
    return DestructiveApprovalEnvelope(
        proposal=proposta,
        approval_id=approval_id or uuid.uuid4(),
        nonce=nonce or uuid.uuid4(),
        identity=IdentityEvidence(PRINCIPAL, assurance, ANTES),
        context=contexto,
        provenance=proveniencia,
        issued_at=ANTES,
        confirmed_at=ANTES,
        expires_at=DEPOIS,
    )


# ======================================================================
# Vocabulários fechados
# ======================================================================


def test_u01_lifecycle_tem_tres_membros_e_nenhum_de_execucao():
    """`ACTIVE | CONSUMED | REVOKED` — e nada de execução ou recibo."""
    assert [m.value for m in ApprovalLifecycleState] == [
        "active",
        "consumed",
        "revoked",
    ]
    for proibido in (
        "EXPIRED",
        "EXECUTING",
        "SUCCEEDED",
        "FAILED",
        "PARTIAL",
        "RECEIPTED",
        "PENDING",
        "APPROVED",
    ):
        assert proibido not in ApprovalLifecycleState.__members__


def test_u02_expiracao_nao_e_estado_persistido():
    """`EXPIRY_IS_DERIVED_NOT_STORED`.

    Um estado exigiria scheduler para existir — e, entre o vencimento real
    e a passagem dele, a linha diria `ACTIVE` sobre aprovação já vencida.
    """
    assert "EXPIRED" not in ApprovalLifecycleState.__members__
    colunas = {c.name for c in ApprovalRecord.__table__.columns}
    assert "expired_at" not in colunas
    assert "expires_at" in colunas


@pytest.mark.parametrize(
    ("estado", "terminal"),
    [
        (ApprovalLifecycleState.ACTIVE, False),
        (ApprovalLifecycleState.CONSUMED, True),
        (ApprovalLifecycleState.REVOKED, True),
    ],
)
def test_u03_terminalidade(estado, terminal):
    assert estado.is_terminal is terminal


def test_u04_kinds_de_governanca_cobrem_as_seis_tuplas():
    assert [m.value for m in GovernanceItemKind] == [
        "domain_id",
        "blocked_capability",
        "admissible_alternative",
        "constraint",
        "declared_preservation",
        "declared_loss",
    ]
    campos_tupla = {
        c.name for c in dataclasses.fields(GovernanceResolution) if str(c.type).startswith("tuple")
    }
    assert len(campos_tupla) == len(GovernanceItemKind)


@pytest.mark.parametrize("kind", list(GovernanceItemKind))
def test_u05_cada_kind_declara_uma_coluna_de_valor(kind):
    assert kind.coluna_de_valor in {"value_uuid", "value_enum", "value_text"}


def test_u06_motivos_de_recusa_sao_fechados_e_sem_bool():
    """`BOOLEAN_OUTCOME = FORBIDDEN`."""
    assert len(ApprovalUsageRefusalReason) == 7
    for proibido in ("OTHER", "UNKNOWN", "GENERIC", "FAILED"):
        assert proibido not in ApprovalUsageRefusalReason.__members__


# ======================================================================
# Forma do schema — o que NUNCA entra em coluna
# ======================================================================


PROIBIDOS = {
    "content",
    "payload",
    "prompt",
    "response",
    "note",
    "transcript",
    "transcription",
    "audio",
    "utterance",
    "raw_text",
    "command_text",
    "token",
    "secret",
    "password",
    "credential",
    "cookie",
    "api_key",
    "signature",
    "biometric",
    "transient_locator",
    "locator",
    "capability",
    "step_up_material",
    "pickle",
}


@pytest.mark.parametrize(
    "modelo", [ApprovalRecord, ApprovalRecordTarget, ApprovalRecordGovernanceItem]
)
def test_u07_nenhuma_coluna_proibida(modelo):
    """Medido sobre o schema **real**, não sobre a docstring."""
    colunas = {c.name for c in modelo.__table__.columns}
    assert colunas.isdisjoint(PROIBIDOS), colunas & PROIBIDOS


def test_u08_o_lote_nao_carrega_localizador_capacidade_nem_instante():
    """`LOCATOR_NEVER_PERSISTED`."""
    colunas = {c.name for c in ApprovalRecordTarget.__table__.columns}
    for proibido in ("transient_locator", "capability", "resolved_at"):
        assert proibido not in colunas
    for exigido in ("legacy_protection_state", "version_etag", "position"):
        assert exigido in colunas


def test_u09_subject_coid_nao_tem_fk_para_o_objeto_material():
    """Uma FK faria o apagamento futuro destruir a prova da aprovação."""
    coluna = ApprovalRecordTarget.__table__.columns["subject_coid"]
    assert not coluna.foreign_keys


def test_u10_as_filhas_apontam_para_o_pai_com_restricao():
    for modelo in (ApprovalRecordTarget, ApprovalRecordGovernanceItem):
        (fk,) = modelo.__table__.columns["approval_record_id"].foreign_keys
        assert fk.column.table.name == "approval_records"
        assert fk.ondelete == "RESTRICT"


def test_u11_ordem_e_unicidade_do_lote_no_schema():
    nomes = {c.name for c in ApprovalRecordTarget.__table__.constraints}
    assert "uq_approval_targets_position" in nomes
    assert "uq_approval_targets_subject" in nomes


def test_u12_ordem_e_unicidade_da_governanca_no_schema():
    nomes = {c.name for c in ApprovalRecordGovernanceItem.__table__.constraints}
    assert "uq_approval_gov_items_order" in nomes


def test_u13_tres_tabelas_e_nenhuma_coluna_json():
    """`JSON_STORAGE = FORBIDDEN`.

    A E4.9.6 gastou três corretivos fechando as fronteiras de um único
    campo JSON. A tabela-filha genérica existe para não reabri-las.
    """
    import sqlalchemy as sa

    for modelo in (ApprovalRecord, ApprovalRecordTarget, ApprovalRecordGovernanceItem):
        for coluna in modelo.__table__.columns:
            assert not isinstance(coluna.type, sa.JSON), f"{modelo.__tablename__}.{coluna.name}"


def test_u14_colunas_de_valor_sao_mutuamente_exclusivas_por_check():
    checks = {
        c.name
        for c in ApprovalRecordGovernanceItem.__table__.constraints
        if c.__class__.__name__ == "CheckConstraint"
    }
    assert "ck_approval_gov_items_value_matches_kind" in checks


def test_u15_estado_e_instante_sao_coerentes_por_check():
    """Um estado sem o seu instante seria estado impossível materializado."""
    checks = {
        c.name
        for c in ApprovalRecord.__table__.constraints
        if c.__class__.__name__ == "CheckConstraint"
    }
    assert "ck_approval_records_state_timestamp_coherent" in checks
    assert "ck_approval_records_temporal_order" in checks
    assert "ck_approval_records_volume_coherent" in checks
    assert "ck_approval_records_nonce_distinct" in checks


# ======================================================================
# Envelopes alternativos — todos válidos pelos construtores públicos
# ======================================================================


def test_u16_envelope_de_erasure_e_de_lixeira_sao_ambos_validos():
    """As variantes usadas nos testes de divergência não são fabricadas.

    ```text
    ALTERNATIVE_ENVELOPE != PATCHED_INVALID_STATE
    ```
    """
    erasure = envelope()
    lixeira = envelope(
        operacao=DestructiveOperation.MOVE_TO_TRASH,
        assurance=AssuranceLevel.AUTHENTICATED,
    )
    assert erasure.proposal.operation is DestructiveOperation.PERMANENT_ERASURE
    assert lixeira.proposal.operation is DestructiveOperation.MOVE_TO_TRASH
    assert lixeira.identity.assurance_level is AssuranceLevel.AUTHENTICATED


def test_u17_variantes_de_assurance_para_a_mesma_operacao():
    """Lixeira aceita `AUTHENTICATED` e `STEP_UP_VERIFIED` — as duas válidas.

    É assim que se testa divergência **de assurance** isolando a operação:
    dois envelopes legítimos que diferem só nesse campo.
    """
    for nivel in (AssuranceLevel.AUTHENTICATED, AssuranceLevel.STEP_UP_VERIFIED):
        e = envelope(operacao=DestructiveOperation.MOVE_TO_TRASH, assurance=nivel)
        assert e.identity.assurance_level is nivel


@pytest.mark.parametrize(
    ("canal", "revisao"),
    [
        (InputChannel.TEXT, VoiceReviewState.NOT_APPLICABLE),
        (InputChannel.VOICE, VoiceReviewState.REVIEWED_AND_CONFIRMED),
    ],
)
def test_u18_texto_e_voz_produzem_envelope_persistivel(canal, revisao):
    """`TEXT_GOVERNANCE = VOICE_GOVERNANCE`, também na persistência."""
    e = envelope(canal=canal, revisao=revisao)
    assert e.provenance.channel is canal
    assert e.provenance.voice_review is revisao


def test_u19_lote_misto_de_protecao_e_valido():
    e = envelope(
        alvos=(
            snapshot(0, legacy_protection_state=LegacyProtectionState.PROTECTED),
            snapshot(1, legacy_protection_state=LegacyProtectionState.NOT_PROTECTED),
        )
    )
    assert [t.legacy_protection_state for t in e.proposal.targets] == [
        LegacyProtectionState.PROTECTED,
        LegacyProtectionState.NOT_PROTECTED,
    ]


def test_u20_governanca_com_capacidades_bloqueadas_e_valida():
    """`PROHIBITED` exige capacidade bloqueada — fixture coerente."""
    r = resolucao(
        outcome=GovernanceOutcome.PROHIBITED,
        policy_key=None,
        policy_version=None,
        policy_id=None,
        matched_rule_id=None,
        blocked_capabilities=(CriticalCapability.CATASTROPHIC_HARM_ENABLEMENT,),
        safety_rationale="capacidade crítica bloqueada",
    )
    assert r.blocked_capabilities


# ======================================================================
# Esta fatia não executa nada
# ======================================================================


def test_u21_o_modelo_nao_tem_metodo_de_execucao():
    """`PERSISTED_APPROVAL != EXECUTION`."""
    for proibido in (
        "execute",
        "apply",
        "erase",
        "purge",
        "delete_target",
        "move_to_trash",
        "run",
    ):
        assert not hasattr(ApprovalRecord, proibido)


def test_u22_nenhum_estado_de_recibo_no_registro():
    """`APPROVAL_RECORD != ERASURE_RECORD`."""
    colunas = {c.name for c in ApprovalRecord.__table__.columns}
    for proibido in ("outcome", "attempted_at", "completed_at", "failure_code", "executor_ref"):
        assert proibido not in colunas


def test_u23_o_registro_nao_responde_se_o_efeito_ocorreu():
    """Nenhuma coluna descreve efeito material."""
    from app.memory.models.erasure_record import ErasureRecord

    aprovacao = {c.name for c in ApprovalRecord.__table__.columns}
    recibo = {c.name for c in ErasureRecord.__table__.columns}
    exclusivas_do_recibo = {
        "outcome",
        "attempted_at",
        "completed_at",
        "failure_code",
        "executor_ref",
    }
    assert aprovacao.isdisjoint(exclusivas_do_recibo)
    assert exclusivas_do_recibo <= recibo


def test_u24_expiracao_e_janela_temporal_do_envelope():
    """A janela vem do envelope, não de duração canônica inventada."""
    e = envelope()
    assert e.expires_at == DEPOIS
    assert e.confirmed_at < e.expires_at
    curta = envelope()
    assert curta.expires_at - curta.confirmed_at == timedelta(hours=8)
