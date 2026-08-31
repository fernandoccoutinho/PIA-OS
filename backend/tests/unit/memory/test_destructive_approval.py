"""
Testes unitários dos contratos de aprovação destrutiva (`E4.9.8`).

```text
PROPOSAL != APPROVAL != EXECUTION != RECEIPT
CONSTRUCTIBLE_VALUE_OBJECT != VERIFIED_EXTERNAL_APPROVAL
```

Todos os invariantes são provados pelo **construtor direto**, não por
factory — lição repetida desde a E4.2.1 e reafirmada pelos quatro
corretivos da E4.9.7.
"""

import uuid
from collections.abc import Callable
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta

import pytest

from app.memory.models.approval_enums import (
    ApprovalBlockerKind,
    AssuranceLevel,
    DestructiveOperation,
    ImpactVolumeKind,
    InputChannel,
    VoiceReviewState,
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
    OPERACAO_DE_GOVERNANCA,
    RESOLUCAO_OCULTA,
    ApprovalContext,
    DestructiveApprovalEnvelope,
    DestructiveApprovalProposal,
    IdentityEvidence,
    PresentedImpact,
    SafeTargetSnapshot,
    SafeVoiceProvenance,
)
from app.memory.schemas.erasure_target import (
    TEXTO_OCULTO,
    ControlScope,
    CustodyNamespace,
    ReferenceProvenance,
)
from app.memory.schemas.governance import GovernanceResolution

TENANT = uuid.UUID("00000000-0000-0000-0000-0000000000a1")
WORKSPACE = uuid.UUID("00000000-0000-0000-0000-0000000000a2")
DOMINIO = uuid.UUID("00000000-0000-0000-0000-0000000000a3")
SUJEITO = uuid.UUID("00000000-0000-0000-0000-0000000000b1")
SUJEITO_2 = uuid.UUID("00000000-0000-0000-0000-0000000000b2")

MARCADOR = "https://user:password@example.invalid/object?token=E498_SECRET"
PRINCIPAL = "principal:humano-1"

MATERIALIZADO = datetime(2026, 8, 18, 10, 0, tzinfo=UTC)
EMITIDO = datetime(2026, 8, 18, 11, 0, tzinfo=UTC)
CONFIRMADO = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)
EXPIRA = datetime(2026, 8, 18, 13, 0, tzinfo=UTC)


def _construir(alvo: Callable[..., object], **kwargs: object) -> object:
    """Construção dinâmica para entradas deliberadamente inválidas.

    Uma função obtida como valor não tem assinatura conhecida, então o
    argumento inválido é expresso sem `# type: ignore` — disciplina da
    E4.9.6.3.
    """
    return alvo(**kwargs)


def _atribuir_campo(alvo: object, campo: str, valor: object) -> None:
    setattr(alvo, campo, valor)


def escopo(**over: object) -> ControlScope:
    base: dict[str, object] = {
        "workspace_id": WORKSPACE,
        "tenant_id": TENANT,
        "control_principal_ref": PRINCIPAL,
    }
    base.update(over)
    feito = _construir(ControlScope, **base)
    assert isinstance(feito, ControlScope)
    return feito


def custodia(**over: object) -> CustodyNamespace:
    base: dict[str, object] = {"provider": "pia-storage", "namespace": "workspace/w1"}
    base.update(over)
    feito = _construir(CustodyNamespace, **base)
    assert isinstance(feito, CustodyNamespace)
    return feito


def resolucao(**over: object) -> GovernanceResolution:
    """Resolução COERENTE com o outcome pedido.

    A própria `GovernanceResolution` (E4.3.2) impõe coerência interna:
    `NOT_APPLICABLE` não cita regra local — se nenhuma se aplicou, não há
    o que citar — e `PROHIBITED` exige ao menos uma capacidade bloqueada,
    porque uma recusa que não diz o que bloqueou é irrecorrível.

    A fábrica respeita isso em vez de contorná-lo: assim os testes de
    outcome exercitam objetos que a E4.3 realmente produziria.
    """
    outcome = over.get("outcome", GovernanceOutcome.ADMISSIBLE)
    base: dict[str, object] = {
        "outcome": GovernanceOutcome.ADMISSIBLE,
        "operation": CognitiveOperation.LEGAL_ERASURE,
        "context_domain_ids": (DOMINIO,),
        "context_actor_ref": PRINCIPAL,
        "context_purpose": "purpose:remocao-titular",
        "safety_boundary_version": 1,
        "policy_key": "ret.default",
        "policy_version": 1,
        "policy_id": uuid.UUID("00000000-0000-0000-0000-0000000000c1"),
        "matched_rule_id": "rule-1",
    }
    if outcome is GovernanceOutcome.NOT_APPLICABLE:
        base.update(
            {
                "policy_key": None,
                "policy_version": None,
                "policy_id": None,
                "matched_rule_id": None,
            }
        )
    elif outcome is GovernanceOutcome.PROHIBITED:
        base.update(
            {
                "policy_key": None,
                "policy_version": None,
                "policy_id": None,
                "matched_rule_id": None,
                "blocked_capabilities": (CriticalCapability.CATASTROPHIC_HARM_ENABLEMENT,),
                "safety_rationale": "capacidade crítica bloqueada pela plataforma",
            }
        )
    base.update(over)
    feito = _construir(GovernanceResolution, **base)
    assert isinstance(feito, GovernanceResolution)
    return feito


def snapshot(**over: object) -> SafeTargetSnapshot:
    base: dict[str, object] = {
        "target_class": ErasureTargetClass.PIA_MANAGED_ARTIFACT,
        "subject_coid": SUJEITO,
        "control_scope": escopo(),
        "custody_namespace": custodia(),
        "origin": ReferenceProvenance(ReferenceOrigin.PAYLOAD_REF),
        # E4.9.8.3 — ver a nota da fábrica de descritor: escolha
        # consciente, e os testes nominais exercitam PROTECTED.
        "legacy_protection_state": LegacyProtectionState.NOT_PROTECTED,
    }
    base.update(over)
    feito = _construir(SafeTargetSnapshot, **base)
    assert isinstance(feito, SafeTargetSnapshot)
    return feito


def contexto(**over: object) -> ApprovalContext:
    base: dict[str, object] = {
        "tenant_id": TENANT,
        "workspace_id": WORKSPACE,
        "domain_id": DOMINIO,
        "purpose_ref": "purpose:remocao-titular",
    }
    base.update(over)
    feito = _construir(ApprovalContext, **base)
    assert isinstance(feito, ApprovalContext)
    return feito


def proveniencia(**over: object) -> SafeVoiceProvenance:
    base: dict[str, object] = {
        "channel": InputChannel.TEXT,
        "voice_review": VoiceReviewState.NOT_APPLICABLE,
    }
    base.update(over)
    feito = _construir(SafeVoiceProvenance, **base)
    assert isinstance(feito, SafeVoiceProvenance)
    return feito


def identidade(**over: object) -> IdentityEvidence:
    base: dict[str, object] = {
        "principal_ref": PRINCIPAL,
        "assurance_level": AssuranceLevel.STEP_UP_VERIFIED,
        "authenticated_at": MATERIALIZADO,
    }
    base.update(over)
    feito = _construir(IdentityEvidence, **base)
    assert isinstance(feito, IdentityEvidence)
    return feito


def proposta(**over: object) -> DestructiveApprovalProposal:
    """Fábrica COERENTE por construção (`E4.9.8.1`).

    A resolução default acompanha a operação, o domínio, a finalidade e o
    principal da proposta — porque, desde este corretivo, uma resolução
    que responda a outra pergunta não forma proposta. Qualquer campo
    continua sobrescritível para exercitar a divergência.
    """
    # A fábrica NÃO assume tipos válidos: `u60` injeta lixo de propósito e
    # precisa alcançar o construtor. O default coerente só é montado
    # quando os valores realmente são os tipos esperados.
    operacao = over.get("operation", DestructiveOperation.PERMANENT_ERASURE)
    ctx = over.get("context") or contexto()
    coerente = isinstance(operacao, DestructiveOperation) and isinstance(ctx, ApprovalContext)
    base: dict[str, object] = {
        "operation": operacao,
        "targets": (snapshot(),),
        "impact": PresentedImpact(1, ImpactVolumeKind.KNOWN, 4096),
        "governance_resolution": (
            resolucao(
                operation=OPERACAO_DE_GOVERNANCA[operacao],
                context_domain_ids=(ctx.domain_id,),
                context_purpose=ctx.purpose_ref,
            )
            if coerente
            else resolucao()
        ),
        "context": ctx,
        "provenance": proveniencia(),
        "blockers": (),
        "materialized_at": MATERIALIZADO,
    }
    base.update(over)
    feito = _construir(DestructiveApprovalProposal, **base)
    assert isinstance(feito, DestructiveApprovalProposal)
    return feito


def envelope(**over: object) -> DestructiveApprovalEnvelope:
    p = over.pop("proposal", None) or proposta()
    assert isinstance(p, DestructiveApprovalProposal)
    base: dict[str, object] = {
        "proposal": p,
        "approval_id": uuid.UUID("00000000-0000-0000-0000-0000000000d1"),
        "nonce": uuid.UUID("00000000-0000-0000-0000-0000000000d2"),
        "identity": identidade(),
        "context": p.context,
        "provenance": p.provenance,
        "issued_at": EMITIDO,
        "confirmed_at": CONFIRMADO,
        "expires_at": EXPIRA,
    }
    base.update(over)
    feito = _construir(DestructiveApprovalEnvelope, **base)
    assert isinstance(feito, DestructiveApprovalEnvelope)
    return feito


# ======================================================================
# Vocabulários fechados
# ======================================================================


def test_u01_operacao_destrutiva_tem_exatamente_duas():
    """`TRASH != LEGAL_ERASURE`."""
    assert [o.value for o in DestructiveOperation] == [
        "move_to_trash",
        "permanent_erasure",
    ]


def test_u02_assurance_e_ordenado_e_sem_generico():
    assert [a.value for a in AssuranceLevel] == [
        "unauthenticated",
        "authenticated",
        "step_up_verified",
    ]
    for proibido in ("UNKNOWN", "OTHER", "GENERIC", "ANY", "DEFAULT"):
        assert proibido not in AssuranceLevel.__members__


@pytest.mark.parametrize(
    ("nivel", "operacao", "esperado"),
    [
        (AssuranceLevel.UNAUTHENTICATED, DestructiveOperation.MOVE_TO_TRASH, False),
        (AssuranceLevel.UNAUTHENTICATED, DestructiveOperation.PERMANENT_ERASURE, False),
        (AssuranceLevel.AUTHENTICATED, DestructiveOperation.MOVE_TO_TRASH, True),
        (AssuranceLevel.AUTHENTICATED, DestructiveOperation.PERMANENT_ERASURE, False),
        (AssuranceLevel.STEP_UP_VERIFIED, DestructiveOperation.MOVE_TO_TRASH, True),
        (AssuranceLevel.STEP_UP_VERIFIED, DestructiveOperation.PERMANENT_ERASURE, True),
    ],
)
def test_u03_matriz_de_assurance(nivel, operacao, esperado):
    """Proporcionalidade, e nenhuma operação sem evidência."""
    assert nivel.satisfies(operacao) is esperado


def test_u04_canais_e_revisao_de_voz_sao_fechados():
    assert [c.value for c in InputChannel] == ["text", "voice"]
    assert [v.value for v in VoiceReviewState] == [
        "not_applicable",
        "not_reviewed",
        "low_confidence",
        "ambiguous",
        "reviewed_and_confirmed",
    ]


def test_u05_bloqueios_sao_vocabulario_fechado_sem_texto_livre():
    """`BLOCKER_KIND != FREE_TEXT_DIAGNOSTIC`."""
    assert len(ApprovalBlockerKind) == 6
    for proibido in ("OTHER", "UNKNOWN", "GENERIC", "DETAIL", "MESSAGE"):
        assert proibido not in ApprovalBlockerKind.__members__


def test_u06_nenhum_enum_novo_duplica_fonte_da_verdade():
    """Nenhum estado de aprovação entrou em `ErasureOutcome`."""
    from app.memory.models.erasure_enums import ErasureOutcome
    from app.memory.models.retention_enums import RetentionExpiryAction

    for proibido in ("APPROVED", "PENDING", "PROPOSED", "SCHEDULED"):
        assert proibido not in ErasureOutcome.__members__
    assert {a.value for a in RetentionExpiryAction}.isdisjoint(
        {o.value for o in DestructiveOperation}
    )


# ======================================================================
# Snapshot seguro
# ======================================================================


def test_u07_snapshot_nao_tem_campo_de_localizador():
    """`SNAPSHOT != ErasureTargetDescriptor`."""
    import dataclasses

    campos = {c.name for c in dataclasses.fields(SafeTargetSnapshot)}
    for proibido in (
        "transient_locator",
        "locator",
        "capability",
        "content",
        "payload",
        "transcript",
        "audio",
    ):
        assert proibido not in campos


@pytest.mark.parametrize(
    "classe",
    [
        ErasureTargetClass.COGNITIVE_METADATA_RECORD,
        ErasureTargetClass.UNRESOLVED_OPAQUE_REFERENCE,
    ],
)
def test_u08_snapshot_recusa_classe_nao_apagavel(classe):
    with pytest.raises(ValueError, match="não é conteúdo apagável"):
        snapshot(target_class=classe)


@pytest.mark.parametrize(
    ("campo", "valor"),
    [
        ("target_class", "pia_managed_artifact"),
        ("subject_coid", str(SUJEITO)),
        ("control_scope", {"workspace_id": WORKSPACE}),
        ("custody_namespace", "pia-storage"),
        ("origin", "payload_ref"),
    ],
)
def test_u09_snapshot_exige_tipos_reais(campo, valor):
    with pytest.raises(TypeError):
        snapshot(**{campo: valor})


# ======================================================================
# Impacto apresentado
# ======================================================================


def test_u10_volume_conhecido_exige_bytes():
    assert PresentedImpact(2, ImpactVolumeKind.KNOWN, 0).bytes_total == 0
    with pytest.raises(ValueError, match="exige bytes_total"):
        PresentedImpact(2, ImpactVolumeKind.KNOWN)


def test_u11_volume_desconhecido_nao_pode_fabricar_bytes():
    """`UNKNOWN_VOLUME != ZERO_VOLUME`."""
    assert PresentedImpact(2, ImpactVolumeKind.UNKNOWN).bytes_total is None
    with pytest.raises(ValueError, match="não pode ter bytes_total"):
        PresentedImpact(2, ImpactVolumeKind.UNKNOWN, 0)


@pytest.mark.parametrize("valor", [True, False, "2", 2.0, None])
def test_u12_quantidade_recusa_bool_e_nao_inteiros(valor):
    """`bool` é subclasse de `int` e não é número aqui."""
    with pytest.raises(TypeError, match="item_count deve ser int"):
        _construir(PresentedImpact, item_count=valor, volume_kind=ImpactVolumeKind.UNKNOWN)


@pytest.mark.parametrize("valor", [True, "10", 10.0])
def test_u13_bytes_recusa_bool_e_nao_inteiros(valor):
    with pytest.raises(TypeError, match="bytes_total deve ser int"):
        _construir(
            PresentedImpact,
            item_count=1,
            volume_kind=ImpactVolumeKind.KNOWN,
            bytes_total=valor,
        )


def test_u14_numeros_negativos_recusados():
    with pytest.raises(ValueError, match=">= 0"):
        PresentedImpact(-1, ImpactVolumeKind.UNKNOWN)
    with pytest.raises(ValueError, match=">= 0"):
        PresentedImpact(1, ImpactVolumeKind.KNOWN, -1)


# ======================================================================
# Proposta
# ======================================================================


def test_u15_proposta_valida_e_aprovavel():
    p = proposta()
    assert p.is_approvable is True
    assert len(p.targets) == 1


def test_u16_lote_vazio_recusado():
    with pytest.raises(ValueError, match="lote não vazio"):
        proposta(targets=(), impact=PresentedImpact(0, ImpactVolumeKind.UNKNOWN))


@pytest.mark.parametrize("valor", [[snapshot()], {snapshot()}, snapshot(), None, "x"])
def test_u17_lote_deve_ser_tupla(valor):
    with pytest.raises(TypeError, match="targets deve ser tuple"):
        proposta(targets=valor)


def test_u18_duplicata_material_recusada():
    """Duplicata torna a quantidade apresentada ambígua."""
    with pytest.raises(ValueError, match="duplicado"):
        proposta(
            targets=(snapshot(), snapshot()),
            impact=PresentedImpact(2, ImpactVolumeKind.UNKNOWN),
        )


def test_u19_ordem_do_lote_e_preservada():
    """A ordem apresentada faz parte do binding."""
    a, b = snapshot(subject_coid=SUJEITO), snapshot(subject_coid=SUJEITO_2)
    p = proposta(targets=(b, a), impact=PresentedImpact(2, ImpactVolumeKind.UNKNOWN))
    assert [t.subject_coid for t in p.targets] == [SUJEITO_2, SUJEITO]


def test_u20_quantidade_deve_bater_com_o_lote():
    with pytest.raises(ValueError, match="diverge do lote"):
        proposta(impact=PresentedImpact(7, ImpactVolumeKind.UNKNOWN))


def test_u21_resolucao_de_governanca_real_exigida():
    for valor in ("admissible", None, 42, {"outcome": "admissible"}):
        with pytest.raises(TypeError, match="GovernanceResolution"):
            proposta(governance_resolution=valor)


def test_u22_bloqueio_deve_ser_vocabulario_fechado():
    with pytest.raises(TypeError, match="ApprovalBlockerKind"):
        proposta(blockers=("legal_hold",))
    with pytest.raises(TypeError, match="blockers deve ser tuple"):
        proposta(blockers=[ApprovalBlockerKind.LEGAL_HOLD])


@pytest.mark.parametrize("bloqueio", list(ApprovalBlockerKind))
def test_u23_qualquer_bloqueio_torna_a_proposta_nao_aprovavel(bloqueio):
    assert proposta(blockers=(bloqueio,)).is_approvable is False


@pytest.mark.parametrize("valor", [datetime(2026, 8, 18, 10, 0), "2026-08-18", 0, None])
def test_u24_materializacao_exige_instante_ciente(valor):
    with pytest.raises((TypeError, ValueError)):
        proposta(materialized_at=valor)


def test_u25_alvo_fora_do_contexto_recusado():
    """Isolamento de tenant e workspace no próprio lote."""
    with pytest.raises(ValueError, match="workspace do alvo diverge"):
        proposta(targets=(snapshot(control_scope=escopo(workspace_id=uuid.uuid4())),))
    with pytest.raises(ValueError, match="tenant do alvo diverge"):
        proposta(targets=(snapshot(control_scope=escopo(tenant_id=uuid.uuid4())),))


def test_u26_proposta_nao_tem_metodo_de_execucao():
    """`PROPOSAL != EXECUTION`."""
    for proibido in ("execute", "apply", "commit", "save", "persist", "delete", "run"):
        assert not hasattr(proposta(), proibido)


# ======================================================================
# Paridade texto/voz
# ======================================================================


@pytest.mark.parametrize(
    ("canal", "revisao"),
    [
        (InputChannel.TEXT, VoiceReviewState.NOT_APPLICABLE),
        (InputChannel.VOICE, VoiceReviewState.REVIEWED_AND_CONFIRMED),
    ],
)
def test_u27_texto_e_voz_produzem_os_mesmos_invariantes(canal, revisao):
    """`TEXT_GOVERNANCE = VOICE_GOVERNANCE`."""
    p = proposta(provenance=proveniencia(channel=canal, voice_review=revisao))
    assert p.is_approvable is True
    e = envelope(proposal=p)
    assert e.proposal.provenance.channel is canal


@pytest.mark.parametrize(
    ("canal", "revisao"),
    [
        (InputChannel.TEXT, VoiceReviewState.NOT_APPLICABLE),
        (InputChannel.VOICE, VoiceReviewState.REVIEWED_AND_CONFIRMED),
    ],
)
@pytest.mark.parametrize("nivel", [AssuranceLevel.UNAUTHENTICATED, AssuranceLevel.AUTHENTICATED])
def test_u28_texto_e_voz_produzem_as_mesmas_recusas(canal, revisao, nivel):
    """A mesma recusa nos dois canais — paridade, não indulgência."""
    p = proposta(provenance=proveniencia(channel=canal, voice_review=revisao))
    with pytest.raises(ValueError, match="não é admissível com assurance"):
        envelope(proposal=p, identity=identidade(assurance_level=nivel))


@pytest.mark.parametrize(
    "revisao",
    [
        VoiceReviewState.NOT_REVIEWED,
        VoiceReviewState.LOW_CONFIDENCE,
        VoiceReviewState.AMBIGUOUS,
    ],
)
def test_u29_voz_nao_revisada_ou_ambigua_nao_forma_proposta(revisao):
    """`ASR_ERROR_MUST_NOT_BECOME_CONSENT`."""
    with pytest.raises(ValueError, match="não forma proposta"):
        proposta(provenance=proveniencia(channel=InputChannel.VOICE, voice_review=revisao))


def test_u30_coerencia_canal_revisao_nos_dois_sentidos():
    """`TEXT` declara `NOT_APPLICABLE`; `VOICE` não pode."""
    with pytest.raises(ValueError, match="canal TEXT exige"):
        proveniencia(
            channel=InputChannel.TEXT, voice_review=VoiceReviewState.REVIEWED_AND_CONFIRMED
        )
    with pytest.raises(ValueError, match="canal VOICE não pode"):
        proveniencia(channel=InputChannel.VOICE, voice_review=VoiceReviewState.NOT_APPLICABLE)


def test_u31_nenhum_objeto_guarda_audio_ou_transcricao():
    import dataclasses

    for classe in (SafeVoiceProvenance, DestructiveApprovalProposal, DestructiveApprovalEnvelope):
        campos = {c.name for c in dataclasses.fields(classe)}
        for proibido in ("audio", "transcript", "transcription", "raw_text", "utterance"):
            assert proibido not in campos


# ======================================================================
# Envelope
# ======================================================================


def test_u32_envelope_incorpora_a_proposta_exata():
    """Binding estrutural, não reconstrução aproximada."""
    p = proposta()
    assert envelope(proposal=p).proposal is p


def test_u33_approval_id_e_nonce_distintos_e_obrigatorios():
    """`NONCE_PRESENT != SINGLE_USE_ENFORCED`."""
    mesmo = uuid.uuid4()
    with pytest.raises(ValueError, match="nonce não pode ser igual"):
        envelope(approval_id=mesmo, nonce=mesmo)
    for campo in ("approval_id", "nonce"):
        with pytest.raises(TypeError, match="deve ser UUID"):
            envelope(**{campo: "opaco"})


def test_u34_step_up_obrigatorio_para_erasure_definitiva():
    for nivel in (AssuranceLevel.UNAUTHENTICATED, AssuranceLevel.AUTHENTICATED):
        with pytest.raises(ValueError, match="não é admissível com assurance"):
            envelope(identity=identidade(assurance_level=nivel))
    assert envelope(identity=identidade(assurance_level=AssuranceLevel.STEP_UP_VERIFIED))


def test_u35_lixeira_aceita_authenticated_mas_nunca_ausencia_de_evidencia():
    """Exigência proporcional — nunca dispensa."""
    p = proposta(operation=DestructiveOperation.MOVE_TO_TRASH)
    assert envelope(proposal=p, identity=identidade(assurance_level=AssuranceLevel.AUTHENTICATED))
    with pytest.raises(ValueError, match="não é admissível com assurance"):
        envelope(
            proposal=p,
            identity=identidade(assurance_level=AssuranceLevel.UNAUTHENTICATED),
        )


@pytest.mark.parametrize("bloqueio", list(ApprovalBlockerKind))
def test_u36_proposta_com_bloqueio_nao_forma_envelope(bloqueio):
    with pytest.raises(ValueError, match="bloqueio não forma envelope"):
        envelope(proposal=proposta(blockers=(bloqueio,)))


@pytest.mark.parametrize("campo", ["tenant_id", "workspace_id", "domain_id"])
def test_u37_contexto_do_envelope_nao_pode_divergir(campo):
    with pytest.raises(ValueError, match="contexto do envelope diverge"):
        envelope(context=contexto(**{campo: uuid.uuid4()}))


def test_u38_finalidade_divergente_recusada():
    with pytest.raises(ValueError, match="contexto do envelope diverge"):
        envelope(context=contexto(purpose_ref="purpose:outra"))


def test_u39_canal_do_envelope_nao_pode_divergir():
    with pytest.raises(ValueError, match="canal do envelope diverge"):
        envelope(
            provenance=proveniencia(
                channel=InputChannel.VOICE,
                voice_review=VoiceReviewState.REVIEWED_AND_CONFIRMED,
            )
        )


@pytest.mark.parametrize(
    ("campo", "valor", "trecho"),
    [
        ("issued_at", MATERIALIZADO - timedelta(hours=1), "issued_at não pode preceder"),
        ("confirmed_at", EMITIDO - timedelta(minutes=1), "confirmed_at não pode preceder"),
        ("expires_at", CONFIRMADO, "expires_at deve ser posterior"),
        ("expires_at", CONFIRMADO - timedelta(minutes=1), "expires_at deve ser posterior"),
    ],
)
def test_u40_ordem_temporal_exigida(campo, valor, trecho):
    with pytest.raises(ValueError, match=trecho):
        envelope(**{campo: valor})


@pytest.mark.parametrize("campo", ["issued_at", "confirmed_at", "expires_at"])
def test_u41_instantes_exigem_timezone(campo):
    with pytest.raises(ValueError, match="timezone-aware"):
        envelope(**{campo: datetime(2026, 8, 18, 12, 0)})


def test_u42_coerencia_temporal_usa_instante_recebido():
    """`EXPIRES_AT_PRESENT != EXPIRY_ENFORCED` — e sem relógio interno."""
    e = envelope()
    assert e.is_temporally_coherent_at(CONFIRMADO) is True
    assert e.is_temporally_coherent_at(CONFIRMADO + timedelta(minutes=30)) is True
    assert e.is_temporally_coherent_at(EXPIRA) is False
    assert e.is_temporally_coherent_at(CONFIRMADO - timedelta(minutes=1)) is False
    with pytest.raises(ValueError, match="timezone-aware"):
        e.is_temporally_coherent_at(datetime(2026, 8, 18, 12, 30))


def test_u43_envelope_nao_tem_execucao_persistencia_consumo_nem_recibo():
    """`APPROVAL != EXECUTION != RECEIPT`."""
    e = envelope()
    for proibido in (
        "execute",
        "apply",
        "consume",
        "revoke",
        "persist",
        "save",
        "commit",
        "to_dict",
        "model_dump",
        "as_record",
        "erasure_record",
    ):
        assert not hasattr(e, proibido), proibido


# ======================================================================
# Assinaturas, defaults e imutabilidade
# ======================================================================


def test_u44_nenhum_campo_de_autoridade_tem_default():
    """Lição direta do A6 da E4.9.7.4."""
    import dataclasses

    com_default: dict[str, set[str]] = {}
    for classe in (
        SafeTargetSnapshot,
        PresentedImpact,
        IdentityEvidence,
        ApprovalContext,
        SafeVoiceProvenance,
        DestructiveApprovalProposal,
        DestructiveApprovalEnvelope,
    ):
        com_default[classe.__name__] = {
            c.name
            for c in dataclasses.fields(classe)
            if c.default is not dataclasses.MISSING or c.default_factory is not dataclasses.MISSING
        }

    assert com_default == {
        "SafeTargetSnapshot": {"version_etag"},
        "PresentedImpact": {"bytes_total"},
        "IdentityEvidence": set(),
        "ApprovalContext": set(),
        "SafeVoiceProvenance": set(),
        "DestructiveApprovalProposal": set(),
        "DestructiveApprovalEnvelope": set(),
    }


def test_u45_omissao_nunca_vira_true_false_ou_aprovado():
    """Omitir campo de autoridade é `TypeError`, nunca valor implícito."""
    import inspect

    for classe, campo in (
        (IdentityEvidence, "assurance_level"),
        (SafeVoiceProvenance, "voice_review"),
        (DestructiveApprovalEnvelope, "identity"),
        (DestructiveApprovalEnvelope, "confirmed_at"),
        (DestructiveApprovalProposal, "blockers"),
    ):
        parametro = inspect.signature(classe).parameters[campo]
        assert parametro.default is inspect.Parameter.empty, f"{classe.__name__}.{campo}"

    with pytest.raises(TypeError):
        _construir(
            IdentityEvidence,
            principal_ref="p:1",
            authenticated_at=MATERIALIZADO,
        )


@pytest.mark.parametrize(
    ("fabrica", "campo"),
    [
        (snapshot, "subject_coid"),
        (custodia, "provider"),
        (contexto, "purpose_ref"),
        (proveniencia, "channel"),
        (identidade, "assurance_level"),
        (proposta, "operation"),
        (envelope, "approval_id"),
    ],
)
def test_u46_todos_os_value_objects_sao_congelados(fabrica, campo):
    with pytest.raises(FrozenInstanceError):
        _atribuir_campo(fabrica(), campo, "outro")


def test_u47_nenhuma_colecao_mutavel_publica():
    """`tuple`/`frozenset`, nunca `list`/`dict`."""
    for alvo in (proposta(), envelope(), snapshot()):
        for valor in vars(alvo).values():
            assert not isinstance(valor, list | dict | set), type(valor)


def test_u48_mutacao_aninhada_impossivel():
    p = proposta()
    with pytest.raises(TypeError):
        p.targets[0] = snapshot(subject_coid=SUJEITO_2)  # type: ignore[index]
    with pytest.raises(FrozenInstanceError):
        _atribuir_campo(p.targets[0], "subject_coid", SUJEITO_2)


def test_u49_mudanca_exige_nova_instancia():
    """Não há mutação: alterar é construir outra proposta."""
    p = proposta()
    outra = proposta(operation=DestructiveOperation.MOVE_TO_TRASH)
    assert p is not outra
    assert p.operation is DestructiveOperation.PERMANENT_ERASURE
    assert not hasattr(p, "with_operation")
    assert not hasattr(p, "replace")


# ======================================================================
# Confidencialidade — direta e composta
# ======================================================================


def _sem_marcador(objeto: object, canal: str) -> None:
    assert MARCADOR not in repr(objeto), f"{canal}: repr"
    assert MARCADOR not in str(objeto), f"{canal}: str"
    assert MARCADOR not in f"{objeto}", f"{canal}: f-string"


def _objetos_com_marcador() -> dict[str, object]:
    """Um objeto por canal textual, com o marcador naquele canal."""
    escopo_m = escopo(control_principal_ref=MARCADOR)
    custodia_m = custodia(provider=MARCADOR)
    snap_m = snapshot(version_etag=MARCADOR)
    ctx_m = contexto(purpose_ref=MARCADOR)
    ident_m = identidade(principal_ref=MARCADOR)
    # A finalidade e o ator do marcador precisam ser COERENTES com a
    # proposta, senão o binding da E4.9.8.1 recusa antes de a prova de
    # confidencialidade acontecer — e a guarda passaria sem medir nada.
    # Por isso cada proposta abaixo monta a sua própria resolução.

    # `escopo_m` põe o marcador no principal de CONTROLE. Desde a
    # E4.9.8.1 isso obriga identidade e ator avaliado a serem o mesmo
    # principal — o binding torna impossível variar um canal isolado, que
    # é precisamente o que "binding" significa.
    p_scope = proposta(
        targets=(snapshot(control_scope=escopo_m),),
        governance_resolution=resolucao(context_actor_ref=MARCADOR),
    )
    p_custodia = proposta(targets=(snapshot(custody_namespace=custodia_m),))
    p_versao = proposta(targets=(snap_m,))
    escopo_marcado = escopo(control_principal_ref=MARCADOR)
    p_ctx = proposta(
        context=ctx_m,
        targets=(snapshot(control_scope=escopo_marcado),),
        governance_resolution=resolucao(context_purpose=MARCADOR, context_actor_ref=MARCADOR),
    )
    p_res = proposta(
        context=ctx_m,
        targets=(snapshot(control_scope=escopo_marcado),),
        governance_resolution=resolucao(
            operation=CognitiveOperation.LEGAL_ERASURE,
            context_domain_ids=(DOMINIO,),
            context_purpose=MARCADOR,
            context_actor_ref=MARCADOR,
        ),
    )

    return {
        "ControlScope.control_principal_ref": escopo_m,
        "CustodyNamespace.provider": custodia_m,
        "SafeTargetSnapshot.version_etag": snap_m,
        "ApprovalContext.purpose_ref": ctx_m,
        "IdentityEvidence.principal_ref": ident_m,
        "GovernanceResolution (fonte E4.3)": None,
        "Proposal→control_scope": p_scope,
        "Proposal→custody_namespace": p_custodia,
        "Proposal→version_etag": p_versao,
        "Proposal→context.purpose_ref": p_ctx,
        "Proposal→governance_resolution": p_res,
        # Chaves ÚNICAS de propósito: uma repetida sobrescreveria a
        # anterior em silêncio e um canal deixaria de ser medido.
        "Envelope→proposal.control_scope": envelope(proposal=p_scope, identity=ident_m),
        "Envelope→proposal.governance_resolution": envelope(
            proposal=p_res, identity=ident_m, context=p_res.context
        ),
        "Envelope→identity.principal_ref": envelope(
            proposal=p_ctx, identity=ident_m, context=p_ctx.context
        ),
        "Envelope→context.purpose_ref": envelope(
            proposal=p_ctx, identity=ident_m, context=p_ctx.context
        ),
    }


def test_u50_nenhum_canal_textual_revela_o_marcador():
    """`DIRECT_REDACTION != COMPOSITE_REDACTION` — os dois provados."""
    for canal, objeto in _objetos_com_marcador().items():
        if objeto is None:
            continue
        _sem_marcador(objeto, canal)


def test_u51_a_resolucao_de_governanca_e_redigida_na_composicao():
    """O caso que o preflight encontrou.

    `GovernanceResolution` é da E4.3, tem onze campos `str` livres
    visíveis no `repr` dela, e **não pode** ser alterada — seria mudança
    de assinatura pública existente. A proposta redige a composição.
    """
    ctx_m = contexto(purpose_ref=MARCADOR)
    res_m = resolucao(
        operation=CognitiveOperation.LEGAL_ERASURE,
        context_domain_ids=(DOMINIO,),
        context_purpose=MARCADOR,
        context_actor_ref=MARCADOR,
    )
    assert MARCADOR in repr(res_m), "a fonte da E4.3 realmente expõe — por isso redigimos"

    p = proposta(
        context=ctx_m,
        governance_resolution=res_m,
        targets=(snapshot(control_scope=escopo(control_principal_ref=MARCADOR)),),
    )
    _sem_marcador(p, "Proposal→governance_resolution")
    _sem_marcador(
        envelope(proposal=p, identity=identidade(principal_ref=MARCADOR)),
        "Envelope→proposal.governance_resolution",
    )
    assert RESOLUCAO_OCULTA in repr(p)
    assert p.governance_resolution is res_m


def test_u52_os_valores_continuam_acessiveis():
    """Redigir a representação não pode inutilizar o contrato."""
    assert contexto(purpose_ref=MARCADOR).purpose_ref == MARCADOR
    assert identidade(principal_ref=MARCADOR).principal_ref == MARCADOR
    assert snapshot(version_etag=MARCADOR).version_etag == MARCADOR


def test_u53_nenhum_campo_de_conteudo_segredo_ou_biometria():
    import dataclasses

    from app.memory.schemas import destructive_approval as modulo

    proibidos = {
        "content",
        "payload",
        "prompt",
        "response",
        "note",
        "audio",
        "transcript",
        "token",
        "secret",
        "password",
        "credential",
        "cookie",
        "api_key",
        "signature",
        "biometric",
        "locator",
        "transient_locator",
        "diagnostic",
    }
    for nome in dir(modulo):
        obj = getattr(modulo, nome)
        if not dataclasses.is_dataclass(obj) or not isinstance(obj, type):
            continue
        # E4.9.8.3 — filtro por MÓDULO DE ORIGEM, acrescentado aqui.
        # `SafeTargetSnapshot.from_descriptor` importou
        # `ErasureTargetDescriptor` para este namespace, e sem o filtro a
        # guarda passava a inspecionar um contrato de OUTRO módulo, cujo
        # `transient_locator` é legítimo e já é provado no lugar certo.
        # Guarda que mede o módulo errado não protege este módulo.
        if obj.__module__ != modulo.__name__:
            continue
        campos = {c.name for c in dataclasses.fields(obj)}
        assert campos.isdisjoint(proibidos), f"{nome}: {campos & proibidos}"


def test_u54_todo_campo_textual_livre_esta_redigido():
    """Inventário por reflexão — campo `str` novo derruba a guarda."""
    import dataclasses

    from app.memory.schemas import destructive_approval as modulo

    textuais: set[tuple[str, str]] = set()
    for nome in dir(modulo):
        obj = getattr(modulo, nome)
        if not dataclasses.is_dataclass(obj) or not isinstance(obj, type):
            continue
        if obj.__module__ != modulo.__name__:
            continue
        for campo in dataclasses.fields(obj):
            if campo.type is str or campo.type == (str | None):
                textuais.add((obj.__name__, campo.name))
                assert campo.repr is False, f"{obj.__name__}.{campo.name}"

    assert textuais == {
        ("SafeTargetSnapshot", "version_etag"),
        ("IdentityEvidence", "principal_ref"),
        ("ApprovalContext", "purpose_ref"),
    }


def test_u55_a_redacao_nao_apaga_o_util():
    """Representação inútil é removida na primeira depuração difícil."""
    e = envelope()
    texto = repr(e)
    assert "permanent_erasure" in repr(e.proposal)
    assert "step_up_verified" in texto
    assert str(e.approval_id) in texto
    assert "2026" in texto
    assert TEXTO_OCULTO in repr(e.identity)


@pytest.mark.parametrize(
    "fabrica",
    [
        lambda: proposta(impact=PresentedImpact(9, ImpactVolumeKind.UNKNOWN)),
        lambda: proposta(targets=(snapshot(), snapshot())),
        lambda: envelope(proposal=proposta(blockers=(ApprovalBlockerKind.LEGAL_HOLD,))),
        lambda: envelope(identity=identidade(assurance_level=AssuranceLevel.AUTHENTICATED)),
    ],
)
def test_u56_excecoes_controladas_nao_vazam_conteudo(fabrica):
    """Nem a mensagem de erro pode transportar o marcador."""
    with pytest.raises((TypeError, ValueError)) as capturado:
        fabrica()
    assert MARCADOR not in str(capturado.value)
    assert not isinstance(capturado.value, KeyError | AttributeError)


# ======================================================================
# Fronteiras de tipo descobertas pela exigência de 100%
#
# Nenhuma é linha morta: cada uma é uma entrada inválida que alguém pode
# escrever, e todas passavam despercebidas porque as fábricas sempre
# entregam o tipo certo.
# ======================================================================


@pytest.mark.parametrize("valor", ["known", 1, None, True])
def test_u57_impacto_exige_volume_kind_tipado(valor):
    with pytest.raises(TypeError, match="volume_kind deve ser um ImpactVolumeKind"):
        _construir(PresentedImpact, item_count=1, volume_kind=valor)


@pytest.mark.parametrize("valor", ["step_up_verified", 2, None])
def test_u58_identidade_exige_assurance_tipado(valor):
    with pytest.raises(TypeError, match="assurance_level deve ser um AssuranceLevel"):
        identidade(assurance_level=valor)


@pytest.mark.parametrize(
    ("campo", "valor", "trecho"),
    [
        ("channel", "text", "channel deve ser um InputChannel"),
        ("channel", 0, "channel deve ser um InputChannel"),
        ("voice_review", "not_applicable", "voice_review deve ser um VoiceReviewState"),
        ("voice_review", None, "voice_review deve ser um VoiceReviewState"),
    ],
)
def test_u59_proveniencia_exige_vocabularios_tipados(campo, valor, trecho):
    with pytest.raises(TypeError, match=trecho):
        proveniencia(**{campo: valor})


@pytest.mark.parametrize(
    ("campo", "valor", "trecho"),
    [
        ("operation", "permanent_erasure", "operation deve ser um DestructiveOperation"),
        ("impact", {"item_count": 1}, "impact deve ser um PresentedImpact"),
        ("context", {"tenant_id": TENANT}, "context deve ser um ApprovalContext"),
        ("provenance", "text", "provenance deve ser um SafeVoiceProvenance"),
    ],
)
def test_u60_proposta_exige_tipos_reais(campo, valor, trecho):
    with pytest.raises(TypeError, match=trecho):
        proposta(**{campo: valor})


def test_u61_lote_com_item_de_tipo_errado_recusado():
    with pytest.raises(TypeError, match=r"targets\[0\] deve ser SafeTargetSnapshot"):
        proposta(targets=({"subject_coid": SUJEITO},))


@pytest.mark.parametrize(
    ("campo", "valor", "trecho"),
    [
        ("identity", {"principal_ref": "p"}, "identity deve ser um IdentityEvidence"),
        ("context", "ctx", "context deve ser um ApprovalContext"),
        ("provenance", "text", "provenance deve ser um SafeVoiceProvenance"),
    ],
)
def test_u62_envelope_exige_tipos_reais(campo, valor, trecho):
    with pytest.raises(TypeError, match=trecho):
        envelope(**{campo: valor})


@pytest.mark.parametrize("valor", ["proposta", {"operation": "x"}, None, 42])
def test_u63_envelope_exige_proposta_real(valor):
    """Construtor direto — a fábrica de teste não é o caminho aqui.

    `envelope()` monta o contexto a partir da proposta, então uma
    proposta falsa nem chegaria ao construtor pela fábrica. É
    exatamente o tipo de caminho que só o construtor direto exercita.
    """
    with pytest.raises(TypeError, match="proposal deve ser um DestructiveApprovalProposal"):
        _construir(
            DestructiveApprovalEnvelope,
            proposal=valor,
            approval_id=uuid.uuid4(),
            nonce=uuid.uuid4(),
            identity=identidade(),
            context=contexto(),
            provenance=proveniencia(),
            issued_at=EMITIDO,
            confirmed_at=CONFIRMADO,
            expires_at=EXPIRA,
        )


def test_u50_1_o_inventario_de_canais_nao_tem_chave_repetida():
    """Uma chave repetida sobrescreveria e o canal sumiria da medição.

    Guarda sobre a própria guarda: `_objetos_com_marcador` é escrita à
    mão, e um `dict` com chave duplicada não avisa. Este teste conta as
    entradas do literal na AST e compara com o dicionário resultante.
    """
    import ast
    import inspect

    (funcao,) = [
        no
        for no in ast.walk(ast.parse(inspect.getsource(_objetos_com_marcador)))
        if isinstance(no, ast.FunctionDef)
    ]
    (retorno,) = [no for no in ast.walk(funcao) if isinstance(no, ast.Return)]
    assert isinstance(retorno.value, ast.Dict)
    chaves = [no.value for no in retorno.value.keys if isinstance(no, ast.Constant)]
    assert len(chaves) == len(set(chaves)), "chave duplicada no inventário de canais"
    assert len(chaves) == len(_objetos_com_marcador())


# ======================================================================
# E4.9.8.1 — binding entre governança, identidade, alvo e tempo
#
# As onze reproduções do reprodutor externo viram regressão aqui, pelo
# CONSTRUTOR DIRETO. A cadeia 85 verificava apenas `isinstance` da
# resolução, enquanto o EDR §5 afirmava que ação, policy, identidade,
# domínio e finalidade estavam vinculados.
#
# GOVERNANCE_RESOLUTION_PRESENT != GOVERNANCE_AUTHORITY_FOR_THIS_ACTION
# HUMAN_CONFIRMATION CANNOT CREATE MISSING AUTHORITY
# ======================================================================


# --- A7/A8 + PROHIBITED: outcome admissível ------------------------------


@pytest.mark.parametrize(
    "outcome",
    [
        GovernanceOutcome.INADMISSIBLE,
        GovernanceOutcome.NOT_APPLICABLE,
        GovernanceOutcome.PROHIBITED,
    ],
)
def test_u64_outcome_nao_admissivel_nao_forma_proposta(outcome):
    """`INADMISSIBLE`, `NOT_APPLICABLE` e `PROHIBITED` recusados.

    `PROHIBITED` é provado **nominalmente**, e não por consequência da
    regra geral: se alguém trocar a checagem por uma lista de outcomes
    aceitáveis mal escrita, ou se `GovernanceOutcome` ganhar membro novo,
    a recusa poderia sumir sem nenhum teste cair.
    """
    with pytest.raises(ValueError, match="exige ADMISSIBLE"):
        proposta(governance_resolution=resolucao(outcome=outcome))


@pytest.mark.parametrize("outcome", list(GovernanceOutcome))
def test_u65_os_quatro_outcomes_um_por_um(outcome):
    """Parametrização DERIVADA do enum.

    Membro novo em `GovernanceOutcome` derruba o teste até haver decisão
    explícita — a alternativa seria descobrir o membro novo em produção.
    """
    if outcome is GovernanceOutcome.ADMISSIBLE:
        assert proposta(governance_resolution=resolucao(outcome=outcome)).is_approvable
        return
    with pytest.raises(ValueError, match="exige ADMISSIBLE"):
        proposta(governance_resolution=resolucao(outcome=outcome))


@pytest.mark.parametrize(
    "outcome",
    [
        GovernanceOutcome.INADMISSIBLE,
        GovernanceOutcome.NOT_APPLICABLE,
        GovernanceOutcome.PROHIBITED,
    ],
)
def test_u66_outcome_nao_admissivel_tambem_nao_forma_envelope(outcome):
    """Nem por caminho indireto: sem proposta, não há envelope."""
    with pytest.raises(ValueError, match="exige ADMISSIBLE"):
        envelope(proposal=proposta(governance_resolution=resolucao(outcome=outcome)))


def test_u67_execution_authorized_e_condicao_independente():
    """Duas condições, verificadas separadamente.

    Hoje `execution_authorized` é derivada do outcome na E4.3, então este
    estado é **impossível** pela construção normal. O dublê existe
    exatamente por isso: sem ele, a segunda condição estaria coberta por
    coincidência com a primeira, e ninguém saberia se ela é verificada.

    Se a E4.3 passar a derivar a propriedade de outra coisa, esta prova
    continua valendo.
    """

    class _ResolucaoSemExecucao(GovernanceResolution):
        """Dublê controlado: admissível, mas execução não autorizada."""

        @property
        def execution_authorized(self) -> bool:
            return False

    base = resolucao()
    dubl = _ResolucaoSemExecucao(
        outcome=base.outcome,
        operation=base.operation,
        context_domain_ids=base.context_domain_ids,
        context_actor_ref=base.context_actor_ref,
        context_purpose=base.context_purpose,
        safety_boundary_version=base.safety_boundary_version,
        policy_key=base.policy_key,
        policy_version=base.policy_version,
        policy_id=base.policy_id,
        matched_rule_id=base.matched_rule_id,
    )
    assert dubl.outcome is GovernanceOutcome.ADMISSIBLE
    assert dubl.execution_authorized is False

    with pytest.raises(ValueError, match="não autoriza execução"):
        proposta(governance_resolution=dubl)


# --- A9: operação exata --------------------------------------------------


def test_u68_a_matriz_de_operacao_e_fonte_unica_e_total():
    """Um membro novo em `DestructiveOperation` sem entrada derruba isto."""
    assert set(OPERACAO_DE_GOVERNANCA) == set(DestructiveOperation)
    assert OPERACAO_DE_GOVERNANCA == {
        DestructiveOperation.MOVE_TO_TRASH: CognitiveOperation.RETENTION_DISPOSITION,
        DestructiveOperation.PERMANENT_ERASURE: CognitiveOperation.LEGAL_ERASURE,
    }


@pytest.mark.parametrize(
    "errada",
    [
        CognitiveOperation.READ,
        CognitiveOperation.RETENTION_ASSESSMENT,
        CognitiveOperation.ACCESSIBILITY_TRANSITION,
        CognitiveOperation.RETENTION_DISPOSITION,
    ],
)
def test_u69_operacao_de_governanca_divergente_recusada_no_erasure(errada):
    """`READ` não autoriza apagamento, e disposição de retenção tampouco."""
    with pytest.raises(ValueError, match="exige resolução de legal_erasure"):
        proposta(
            operation=DestructiveOperation.PERMANENT_ERASURE,
            governance_resolution=resolucao(operation=errada),
        )


@pytest.mark.parametrize("errada", [CognitiveOperation.LEGAL_ERASURE, CognitiveOperation.READ])
def test_u70_operacao_de_governanca_divergente_recusada_na_lixeira(errada):
    with pytest.raises(ValueError, match="exige resolução de retention_disposition"):
        proposta(
            operation=DestructiveOperation.MOVE_TO_TRASH,
            governance_resolution=resolucao(operation=errada),
        )


# --- A10/A11: domínio e finalidade ---------------------------------------


@pytest.mark.parametrize(
    "dominios",
    [
        (),
        (uuid.uuid4(),),
        (DOMINIO, uuid.uuid4()),
        (uuid.uuid4(), DOMINIO),
    ],
)
def test_u71_dominio_divergente_recusado(dominios):
    """Subconjunto, interseção e conjunto mais amplo não são a mesma pergunta."""
    with pytest.raises(ValueError, match="domínio avaliado"):
        proposta(governance_resolution=resolucao(context_domain_ids=dominios))


@pytest.mark.parametrize(
    "finalidade",
    [
        "purpose:outra",
        "purpose:remocao-titular ",
        "Purpose:remocao-titular",
        None,
    ],
)
def test_u72_finalidade_divergente_recusada(finalidade):
    """Sem normalização: espaço e caixa alteram a finalidade."""
    with pytest.raises(ValueError, match="finalidade avaliada"):
        proposta(governance_resolution=resolucao(context_purpose=finalidade))


# --- A12: ator avaliado ↔ identidade externa ------------------------------


@pytest.mark.parametrize("ator", ["principal:outro", "PRINCIPAL:humano-1", None])
def test_u73_ator_avaliado_divergente_recusado(ator):
    with pytest.raises(ValueError, match="ator avaliado"):
        envelope(proposal=proposta(governance_resolution=resolucao(context_actor_ref=ator)))


def test_u74_igualdade_de_ator_nao_promove_actor_ref_a_autenticador():
    """`STRING_EQUALITY != AUTHENTICATION`.

    A igualdade impede que governança, identidade e alvo descrevam
    pessoas diferentes. Não afirma que alguém foi autenticado — a
    evidência externa continua sendo `IdentityEvidence`, e sua verificação
    continua `DEFERRED`.
    """
    e = envelope()
    assert e.proposal.governance_resolution.context_actor_ref == e.identity.principal_ref
    assert e.identity.assurance_level is AssuranceLevel.STEP_UP_VERIFIED
    # Nada no envelope afirma verificação externa realizada.
    for proibido in ("authenticate", "verify", "is_authenticated", "prove"):
        assert not hasattr(e, proibido)
        assert not hasattr(e.identity, proibido)


# --- A17: principal ↔ controle do alvo -----------------------------------


def test_u75_principal_divergente_do_controle_do_alvo_recusado():
    with pytest.raises(ValueError, match="controlado por outro principal"):
        envelope(
            proposal=proposta(
                targets=(snapshot(control_scope=escopo(control_principal_ref="p:outro")),)
            )
        )


def test_u76_qualquer_alvo_divergente_no_lote_recusa():
    """Não basta o primeiro: cada alvo é verificado, com índice."""
    bom = snapshot(subject_coid=SUJEITO)
    ruim = snapshot(subject_coid=SUJEITO_2, control_scope=escopo(control_principal_ref="p:outro"))
    with pytest.raises(ValueError, match=r"alvo\[1\] é controlado"):
        envelope(
            proposal=proposta(
                targets=(bom, ruim), impact=PresentedImpact(2, ImpactVolumeKind.UNKNOWN)
            )
        )


def test_u77_delegacao_nao_e_modelada():
    """Limite declarado, não capacidade escondida."""
    import dataclasses

    from app.memory.schemas import destructive_approval as modulo

    for nome in dir(modulo):
        obj = getattr(modulo, nome)
        if not dataclasses.is_dataclass(obj) or not isinstance(obj, type):
            continue
        campos = {c.name for c in dataclasses.fields(obj)}
        for proibido in ("delegate", "delegation", "role", "group", "on_behalf_of", "admin"):
            assert proibido not in campos, f"{nome}.{proibido}"


# --- A13: frescor mínimo da identidade -----------------------------------


def test_u78_autenticacao_posterior_a_confirmacao_recusada():
    """`AUTHENTICATION_AFTER_CONFIRMATION != PRESENT_AUTHENTICATED_USER`."""
    for instante in (
        CONFIRMADO + timedelta(seconds=1),
        EXPIRA,
        EXPIRA + timedelta(hours=1),
    ):
        with pytest.raises(ValueError, match="posterior à confirmação"):
            envelope(identity=identidade(authenticated_at=instante))


def test_u79_autenticacao_anterior_a_proposta_recusada():
    """Sessão antiga não é step-up vinculado a esta ação."""
    with pytest.raises(ValueError, match="anterior à materialização"):
        envelope(identity=identidade(authenticated_at=MATERIALIZADO - timedelta(seconds=1)))


@pytest.mark.parametrize("instante", [MATERIALIZADO, EMITIDO, CONFIRMADO])
def test_u80_autenticacao_dentro_da_janela_aceita(instante):
    """Os dois extremos inclusive — nenhuma duração canônica inventada."""
    assert envelope(identity=identidade(authenticated_at=instante))


def test_u81_a_ordem_temporal_anterior_continua_valendo():
    """`materialized <= issued <= confirmed < expires` preservada."""
    with pytest.raises(ValueError, match="issued_at não pode preceder"):
        envelope(issued_at=MATERIALIZADO - timedelta(hours=1))
    with pytest.raises(ValueError, match="expires_at deve ser posterior"):
        envelope(expires_at=CONFIRMADO)


# --- A14: blockers sem duplicata -----------------------------------------


@pytest.mark.parametrize("bloqueio", list(ApprovalBlockerKind))
def test_u82_blocker_duplicado_recusado(bloqueio):
    with pytest.raises(ValueError, match="blocker duplicado"):
        proposta(blockers=(bloqueio, bloqueio))


def test_u83_blockers_distintos_preservam_ordem_e_impedem_envelope():
    ordem = (
        ApprovalBlockerKind.LEGAL_HOLD,
        ApprovalBlockerKind.CAUSAL_HISTORY_DEPENDENCY,
        ApprovalBlockerKind.CONTROL_SCOPE_CONFLICT,
    )
    p = proposta(blockers=ordem)
    assert p.blockers == ordem
    assert p.is_approvable is False
    with pytest.raises(ValueError, match="bloqueio não forma envelope"):
        envelope(proposal=p)


def test_u84_duplicata_nao_e_absorvida_nem_reordenada():
    """Nem `set`, nem `frozenset`, nem dedup silenciosa."""
    import ast
    import inspect
    import textwrap

    from app.memory.schemas.destructive_approval import DestructiveApprovalProposal

    corpo = ast.unparse(
        ast.parse(textwrap.dedent(inspect.getsource(DestructiveApprovalProposal.__post_init__)))
    )
    assert "blocker duplicado" in corpo
    assert "sorted(" not in corpo
    assert "frozenset(" not in corpo


# --- A15/A16: helpers públicos estritos ----------------------------------


@pytest.mark.parametrize("valor", ["permanent_erasure", "move_to_trash", None, True, 0, object()])
def test_u85_satisfies_recusa_nao_membro(valor):
    """`ANNOTATION != ENFORCED_TYPE`. String equivalente não é membro."""
    with pytest.raises(TypeError, match="DestructiveOperation"):
        AssuranceLevel.AUTHENTICATED.satisfies(valor)


@pytest.mark.parametrize("valor", ["text", "voice", None, False, 1, object()])
def test_u86_permite_proposta_recusa_nao_membro(valor):
    with pytest.raises(TypeError, match="InputChannel"):
        VoiceReviewState.REVIEWED_AND_CONFIRMED.permite_proposta(valor)


def test_u87_os_helpers_continuam_corretos_com_membros_reais():
    """O endurecimento não alterou a semântica positiva."""
    assert AssuranceLevel.STEP_UP_VERIFIED.satisfies(DestructiveOperation.PERMANENT_ERASURE)
    assert not AssuranceLevel.AUTHENTICATED.satisfies(DestructiveOperation.PERMANENT_ERASURE)
    assert AssuranceLevel.AUTHENTICATED.satisfies(DestructiveOperation.MOVE_TO_TRASH)
    assert not AssuranceLevel.UNAUTHENTICATED.satisfies(DestructiveOperation.MOVE_TO_TRASH)
    assert VoiceReviewState.NOT_APPLICABLE.permite_proposta(InputChannel.TEXT)
    assert not VoiceReviewState.NOT_APPLICABLE.permite_proposta(InputChannel.VOICE)


# --- Positivos paralelos --------------------------------------------------


def test_u88_erasure_completo_forma_envelope():
    """Caminho positivo integral do apagamento definitivo."""
    e = envelope()
    assert e.proposal.operation is DestructiveOperation.PERMANENT_ERASURE
    assert e.proposal.governance_resolution.operation is CognitiveOperation.LEGAL_ERASURE
    assert e.identity.assurance_level is AssuranceLevel.STEP_UP_VERIFIED


def test_u89_lixeira_completa_forma_envelope():
    """Caminho positivo integral da lixeira, com assurance proporcional."""
    p = proposta(operation=DestructiveOperation.MOVE_TO_TRASH)
    e = envelope(proposal=p, identity=identidade(assurance_level=AssuranceLevel.AUTHENTICATED))
    assert e.proposal.governance_resolution.operation is (CognitiveOperation.RETENTION_DISPOSITION)


@pytest.mark.parametrize(
    ("canal", "revisao"),
    [
        (InputChannel.TEXT, VoiceReviewState.NOT_APPLICABLE),
        (InputChannel.VOICE, VoiceReviewState.REVIEWED_AND_CONFIRMED),
    ],
)
def test_u90_texto_e_voz_passam_nos_mesmos_bindings(canal, revisao):
    prov = proveniencia(channel=canal, voice_review=revisao)
    assert envelope(proposal=proposta(provenance=prov), provenance=prov)


@pytest.mark.parametrize(
    ("canal", "revisao"),
    [
        (InputChannel.TEXT, VoiceReviewState.NOT_APPLICABLE),
        (InputChannel.VOICE, VoiceReviewState.REVIEWED_AND_CONFIRMED),
    ],
)
@pytest.mark.parametrize(
    ("quebra", "trecho"),
    [
        ({"governance_resolution": "OUTCOME"}, "exige ADMISSIBLE"),
        ({"governance_resolution": "OPERACAO"}, "exige resolução de"),
        ({"governance_resolution": "DOMINIO"}, "domínio avaliado"),
        ({"governance_resolution": "FINALIDADE"}, "finalidade avaliada"),
    ],
)
def test_u91_texto_e_voz_falham_nos_mesmos_bindings(canal, revisao, quebra, trecho):
    """`TEXT_GOVERNANCE = VOICE_GOVERNANCE` — nas recusas, não só nos aceites."""
    prov = proveniencia(channel=canal, voice_review=revisao)
    variantes = {
        "OUTCOME": resolucao(outcome=GovernanceOutcome.INADMISSIBLE),
        "OPERACAO": resolucao(operation=CognitiveOperation.READ),
        "DOMINIO": resolucao(context_domain_ids=(uuid.uuid4(),)),
        "FINALIDADE": resolucao(context_purpose="purpose:outra"),
    }
    with pytest.raises(ValueError, match=trecho):
        proposta(
            provenance=prov,
            governance_resolution=variantes[quebra["governance_resolution"]],
        )


# ======================================================================
# E4.9.8.2 — matriz de autoridade imutável e contrato estático restaurado
#
# A18: `frozen=True` nos value objects não protege dependência global
#      mutável. A matriz era `dict` público, e trocar um item reabria o
#      binding de operação que a E4.9.8.1 existia para fechar.
# A19/A20: o runtime ficou estrito e a ANOTAÇÃO foi ampliada para
#      `object` — regressão de contrato público que eu relatei como
#      detalhe benigno.
#
# MUTABLE_AUTHORITY_MATRIX = NONE
# STATIC_TYPE_CONTRACT != RUNTIME_TYPE_ENFORCEMENT ; BOTH_REQUIRED = TRUE
# ======================================================================


def _mutar(alvo: object, chave: object, valor: object) -> None:
    """Mutação por índice sem anotar o alvo como mutável.

    O `Mapping` publicado não expõe `__setitem__`; escrever
    `OPERACAO_DE_GOVERNANCA[x] = y` diretamente no teste seria erro de
    tipo estático. `operator.setitem` mede o **runtime** sem enfraquecer a
    assinatura e sem `type: ignore`, `Any` ou `cast`.

    Detalhe que importa: `type(alvo).__setitem__` daria `AttributeError`,
    não `TypeError` — o proxy simplesmente **não tem** o método. A prova
    tem de exercitar a operação, não procurar o atributo.
    """
    import operator

    operator.setitem(alvo, chave, valor)


# --- A18: a matriz não aceita escrita ------------------------------------


def test_u92_a_matriz_e_um_mapping_somente_leitura():
    from collections.abc import Mapping
    from types import MappingProxyType

    assert isinstance(OPERACAO_DE_GOVERNANCA, Mapping)
    assert isinstance(OPERACAO_DE_GOVERNANCA, MappingProxyType)
    assert not isinstance(OPERACAO_DE_GOVERNANCA, dict)


@pytest.mark.parametrize("metodo", ["update", "pop", "clear", "setdefault", "popitem"])
def test_u93_a_matriz_nao_expoe_metodos_mutadores(metodo):
    assert not hasattr(OPERACAO_DE_GOVERNANCA, metodo)


def test_u94_setitem_na_matriz_e_recusado():
    """A reprodução exata da auditoria."""
    with pytest.raises(TypeError):
        _mutar(
            OPERACAO_DE_GOVERNANCA,
            DestructiveOperation.PERMANENT_ERASURE,
            CognitiveOperation.READ,
        )


def test_u95_apos_a_tentativa_a_matriz_continua_intacta():
    with pytest.raises(TypeError):
        _mutar(
            OPERACAO_DE_GOVERNANCA,
            DestructiveOperation.PERMANENT_ERASURE,
            CognitiveOperation.READ,
        )
    assert OPERACAO_DE_GOVERNANCA[DestructiveOperation.PERMANENT_ERASURE] is (
        CognitiveOperation.LEGAL_ERASURE
    )
    assert OPERACAO_DE_GOVERNANCA[DestructiveOperation.MOVE_TO_TRASH] is (
        CognitiveOperation.RETENTION_DISPOSITION
    )


def test_u96_read_continua_recusada_depois_da_tentativa_de_mutacao():
    """O que a auditoria mediu como reproduzido, agora fechado."""
    with pytest.raises(TypeError):
        _mutar(
            OPERACAO_DE_GOVERNANCA,
            DestructiveOperation.PERMANENT_ERASURE,
            CognitiveOperation.READ,
        )
    with pytest.raises(ValueError, match="exige resolução de legal_erasure"):
        proposta(
            operation=DestructiveOperation.PERMANENT_ERASURE,
            governance_resolution=resolucao(operation=CognitiveOperation.READ),
        )


def test_u97_copy_devolve_estrutura_independente():
    """`copy()` é cópia, não o backing — mutá-la não afeta a fonte."""
    copia = dict(OPERACAO_DE_GOVERNANCA)
    copia[DestructiveOperation.PERMANENT_ERASURE] = CognitiveOperation.READ
    assert OPERACAO_DE_GOVERNANCA[DestructiveOperation.PERMANENT_ERASURE] is (
        CognitiveOperation.LEGAL_ERASURE
    )


def test_u98_nenhum_backing_mutavel_alcancavel_no_modulo():
    """O literal subjacente não tem nome — não há atributo por onde chegar.

    Um `_OPERACAO_DE_GOVERNANCA = {...}` privado satisfaria o
    `MappingProxyType` e deixaria a matriz alcançável como atributo de
    módulo, o que não seria `MUTABLE_AUTHORITY_MATRIX = NONE`.
    """
    from collections.abc import Mapping

    from app.memory.schemas import destructive_approval as modulo

    for nome in dir(modulo):
        valor = getattr(modulo, nome)
        if (
            isinstance(valor, dict)
            and valor
            and all(isinstance(chave, DestructiveOperation) for chave in valor)
        ):
            raise AssertionError(f"backing mutável alcançável em {nome}")
    assert isinstance(modulo.OPERACAO_DE_GOVERNANCA, Mapping)


def test_u99_a_matriz_continua_total_e_sem_fallback():
    """Membro novo sem entrada derruba isto antes de virar autorização."""
    assert set(OPERACAO_DE_GOVERNANCA) == set(DestructiveOperation)
    assert dict(OPERACAO_DE_GOVERNANCA) == {
        DestructiveOperation.MOVE_TO_TRASH: CognitiveOperation.RETENTION_DISPOSITION,
        DestructiveOperation.PERMANENT_ERASURE: CognitiveOperation.LEGAL_ERASURE,
    }


# --- A19/A20: contrato estático exato ------------------------------------


def test_u100_a_anotacao_de_satisfies_e_o_enum_exato():
    """`STATIC_TYPE_CONTRACT != RUNTIME_TYPE_ENFORCEMENT`."""
    import typing

    assert typing.get_type_hints(AssuranceLevel.satisfies)["operacao"] is (DestructiveOperation)
    assert typing.get_type_hints(AssuranceLevel.satisfies)["return"] is bool


def test_u101_a_anotacao_de_permite_proposta_e_o_enum_exato():
    import typing

    assert typing.get_type_hints(VoiceReviewState.permite_proposta)["canal"] is (InputChannel)
    assert typing.get_type_hints(VoiceReviewState.permite_proposta)["return"] is bool


def test_u102_nenhuma_anotacao_dos_helpers_e_object():
    """A regressão exata da cadeia 86, fechada nominalmente."""
    import typing

    for funcao, parametro in (
        (AssuranceLevel.satisfies, "operacao"),
        (VoiceReviewState.permite_proposta, "canal"),
    ):
        assert typing.get_type_hints(funcao)[parametro] is not object


@pytest.mark.parametrize("valor", ["permanent_erasure", "move_to_trash", None, True, 0, object()])
def test_u103_satisfies_continua_estrito_em_runtime(valor):
    """Invocação dinâmica: mede o runtime sem enfraquecer a assinatura."""
    chamar = AssuranceLevel.AUTHENTICATED.satisfies
    with pytest.raises(TypeError, match="DestructiveOperation"):
        chamar(valor)


@pytest.mark.parametrize("valor", ["text", "voice", None, False, 1, object()])
def test_u104_permite_proposta_continua_estrito_em_runtime(valor):
    chamar = VoiceReviewState.REVIEWED_AND_CONFIRMED.permite_proposta
    with pytest.raises(TypeError, match="InputChannel"):
        chamar(valor)


# ======================================================================
# E4.9.8.3 — proteção de legado no snapshot e materializador canônico
#
# STRUCTURAL_DISTINGUISHABILITY = IMPLEMENTED_HERE
# EFFECTIVE_INVALIDATION = DEFERRED_TO_E4_9_9_D
# ======================================================================


def _descritor(**over: object):
    """Descritor completo para exercitar `from_descriptor`."""
    from datetime import UTC, datetime

    from app.memory.schemas.erasure_target import (
        ErasureTargetDescriptor,
        VerifiedDeletionCapability,
    )

    base: dict[str, object] = {
        "target_class": ErasureTargetClass.PIA_MANAGED_ARTIFACT,
        "subject_coid": SUJEITO,
        "control_scope": escopo(),
        "custody_namespace": custodia(),
        "capability": VerifiedDeletionCapability("delete_object", "workspace/w1/*", True),
        "resolved_at": datetime(2026, 8, 18, 9, 0, tzinfo=UTC),
        "origin": ReferenceProvenance(ReferenceOrigin.PAYLOAD_REF),
        "legacy_protection_state": LegacyProtectionState.NOT_PROTECTED,
        "transient_locator": "s3://bucket/objeto-real",
    }
    base.update(over)
    feito = _construir(ErasureTargetDescriptor, **base)
    return feito


@pytest.mark.parametrize("estado", list(LegacyProtectionState))
def test_u123_os_dois_estados_sao_construiveis_no_snapshot(estado):
    assert snapshot(legacy_protection_state=estado).legacy_protection_state is estado


@pytest.mark.parametrize("valor", ["protected", "not_protected", True, False, None, 0, object()])
def test_u124_nao_membro_recusado_no_snapshot(valor):
    with pytest.raises(TypeError, match="LegacyProtectionState"):
        snapshot(legacy_protection_state=valor)


def test_u125_campo_obrigatorio_sem_default_no_snapshot():
    import dataclasses
    import inspect

    (campo,) = [
        c for c in dataclasses.fields(SafeTargetSnapshot) if c.name == "legacy_protection_state"
    ]
    assert campo.default is dataclasses.MISSING
    assert campo.default_factory is dataclasses.MISSING
    parametro = inspect.signature(SafeTargetSnapshot).parameters["legacy_protection_state"]
    assert parametro.default is inspect.Parameter.empty


def test_u126_omissao_no_snapshot_e_erro():
    with pytest.raises(TypeError):
        _construir(
            SafeTargetSnapshot,
            target_class=ErasureTargetClass.PIA_MANAGED_ARTIFACT,
            subject_coid=SUJEITO,
            control_scope=escopo(),
            custody_namespace=custodia(),
            origin=ReferenceProvenance(ReferenceOrigin.PAYLOAD_REF),
        )


def test_u127_snapshots_diferem_apenas_pela_protecao():
    """Dois snapshots idênticos exceto pela proteção são **diferentes**."""
    protegido = snapshot(legacy_protection_state=LegacyProtectionState.PROTECTED)
    livre = snapshot(legacy_protection_state=LegacyProtectionState.NOT_PROTECTED)
    assert protegido != livre
    assert protegido == snapshot(legacy_protection_state=LegacyProtectionState.PROTECTED)


# --- materializador canônico ---------------------------------------------


@pytest.mark.parametrize("estado", list(LegacyProtectionState))
def test_u128_from_descriptor_copia_a_protecao(estado):
    d = _descritor(legacy_protection_state=estado)
    s = SafeTargetSnapshot.from_descriptor(d)
    assert s.legacy_protection_state is d.legacy_protection_state is estado


def test_u129_from_descriptor_copia_os_sete_campos():
    d = _descritor(version_etag='W/"v7"')
    s = SafeTargetSnapshot.from_descriptor(d)
    assert s.target_class is d.target_class
    assert s.subject_coid == d.subject_coid
    assert s.control_scope == d.control_scope
    assert s.custody_namespace == d.custody_namespace
    assert s.origin == d.origin
    assert s.legacy_protection_state is d.legacy_protection_state
    assert s.version_etag == d.version_etag


def test_u130_from_descriptor_nao_leva_localizador_capacidade_nem_instante():
    """`LOCATOR_NEVER_CROSSES`."""
    import dataclasses

    d = _descritor()
    s = SafeTargetSnapshot.from_descriptor(d)
    campos = {c.name for c in dataclasses.fields(s)}
    for proibido in ("transient_locator", "capability", "resolved_at"):
        assert proibido not in campos
    assert d.transient_locator not in repr(s)
    assert d.transient_locator not in str(s)


@pytest.mark.parametrize("valor", ["descritor", None, 42, object(), snapshot()])
def test_u131_from_descriptor_recusa_tipo_incorreto(valor):
    with pytest.raises(TypeError, match="ErasureTargetDescriptor"):
        SafeTargetSnapshot.from_descriptor(valor)


def test_u132_from_descriptor_preserva_a_distincao_de_protecao():
    a = SafeTargetSnapshot.from_descriptor(
        _descritor(legacy_protection_state=LegacyProtectionState.PROTECTED)
    )
    b = SafeTargetSnapshot.from_descriptor(
        _descritor(legacy_protection_state=LegacyProtectionState.NOT_PROTECTED)
    )
    assert a != b


# --- proposta: armazena e valida; NÃO compara contra re-resolução --------


def test_u133_a_proposta_preserva_estado_e_ordem_do_lote():
    a = snapshot(subject_coid=SUJEITO, legacy_protection_state=LegacyProtectionState.PROTECTED)
    b = snapshot(
        subject_coid=SUJEITO_2,
        legacy_protection_state=LegacyProtectionState.NOT_PROTECTED,
    )
    p = proposta(targets=(b, a), impact=PresentedImpact(2, ImpactVolumeKind.UNKNOWN))
    assert [t.subject_coid for t in p.targets] == [SUJEITO_2, SUJEITO]
    assert [t.legacy_protection_state for t in p.targets] == [
        LegacyProtectionState.NOT_PROTECTED,
        LegacyProtectionState.PROTECTED,
    ]


def test_u134_lote_misto_com_estados_distintos_e_valido():
    """`PROTECTED` não é bloqueio nesta fatia."""
    p = proposta(
        targets=(
            snapshot(
                subject_coid=SUJEITO,
                legacy_protection_state=LegacyProtectionState.PROTECTED,
            ),
            snapshot(
                subject_coid=SUJEITO_2,
                legacy_protection_state=LegacyProtectionState.NOT_PROTECTED,
            ),
        ),
        impact=PresentedImpact(2, ImpactVolumeKind.UNKNOWN),
    )
    assert p.is_approvable is True
    assert not p.blockers


def test_u135_proposta_com_estado_a_nao_representa_estado_b():
    a = proposta(targets=(snapshot(legacy_protection_state=LegacyProtectionState.PROTECTED),))
    b = proposta(targets=(snapshot(legacy_protection_state=LegacyProtectionState.NOT_PROTECTED),))
    assert a.targets != b.targets
    assert envelope(proposal=a).proposal.targets != envelope(proposal=b).proposal.targets


def test_u136_formar_proposta_nao_muda_a_protecao():
    s = snapshot(legacy_protection_state=LegacyProtectionState.PROTECTED)
    p = proposta(targets=(s,))
    assert p.targets[0].legacy_protection_state is LegacyProtectionState.PROTECTED
    assert p.targets[0] is s


def test_u137_invalidacao_efetiva_e_deferida_e_nao_alegada():
    """`EFFECTIVE_INVALIDATION = DEFERRED_TO_E4_9_9_D`.

    Esta fatia torna estados opostos **distinguíveis**. Comparar o
    snapshot aprovado com uma re-resolução fresca, e recusar a execução
    quando divergirem, é da E4.9.9.d. A proposta armazena e valida; não
    compara contra resolução futura, porque não existe resolução futura.
    """
    p = proposta()
    for proibido in ("compare_with_fresh", "revalidate", "invalidate", "matches"):
        assert not hasattr(p, proibido)
    e = envelope(proposal=p)
    for proibido in ("compare_with_fresh", "revalidate", "invalidate"):
        assert not hasattr(e, proibido)


# --- paridade texto/voz ---------------------------------------------------


@pytest.mark.parametrize(
    ("canal", "revisao"),
    [
        (InputChannel.TEXT, VoiceReviewState.NOT_APPLICABLE),
        (InputChannel.VOICE, VoiceReviewState.REVIEWED_AND_CONFIRMED),
    ],
)
@pytest.mark.parametrize("estado", list(LegacyProtectionState))
def test_u138_texto_e_voz_com_os_mesmos_estados(canal, revisao, estado):
    prov = proveniencia(channel=canal, voice_review=revisao)
    p = proposta(provenance=prov, targets=(snapshot(legacy_protection_state=estado),))
    assert p.targets[0].legacy_protection_state is estado
    assert envelope(proposal=p, provenance=prov)
