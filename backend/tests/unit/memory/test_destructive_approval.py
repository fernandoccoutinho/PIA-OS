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
from app.memory.models.governance_enums import CognitiveOperation, GovernanceOutcome
from app.memory.models.target_resolution_enums import ReferenceOrigin
from app.memory.schemas.destructive_approval import (
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
        "control_principal_ref": "principal:controle-1",
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
    base: dict[str, object] = {
        "outcome": GovernanceOutcome.ADMISSIBLE,
        "operation": CognitiveOperation.LEGAL_ERASURE,
        "context_domain_ids": (DOMINIO,),
        "context_actor_ref": "actor:1",
        "context_purpose": "titular pediu remoção",
        "safety_boundary_version": 1,
        "policy_key": "ret.default",
        "policy_version": 1,
        "policy_id": uuid.UUID("00000000-0000-0000-0000-0000000000c1"),
        "matched_rule_id": "rule-1",
    }
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
        "principal_ref": "principal:humano-1",
        "assurance_level": AssuranceLevel.STEP_UP_VERIFIED,
        "authenticated_at": MATERIALIZADO,
    }
    base.update(over)
    feito = _construir(IdentityEvidence, **base)
    assert isinstance(feito, IdentityEvidence)
    return feito


def proposta(**over: object) -> DestructiveApprovalProposal:
    base: dict[str, object] = {
        "operation": DestructiveOperation.PERMANENT_ERASURE,
        "targets": (snapshot(),),
        "impact": PresentedImpact(1, ImpactVolumeKind.KNOWN, 4096),
        "governance_resolution": resolucao(),
        "context": contexto(),
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
    res_m = resolucao(context_actor_ref=MARCADOR, context_purpose=MARCADOR)

    p_scope = proposta(targets=(snapshot(control_scope=escopo_m),))
    p_custodia = proposta(targets=(snapshot(custody_namespace=custodia_m),))
    p_versao = proposta(targets=(snap_m,))
    p_ctx = proposta(context=ctx_m)
    p_res = proposta(governance_resolution=res_m)

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
        "Envelope→proposal.control_scope": envelope(proposal=p_scope),
        "Envelope→proposal.governance_resolution": envelope(proposal=p_res),
        "Envelope→identity.principal_ref": envelope(identity=ident_m),
        "Envelope→context.purpose_ref": envelope(proposal=p_ctx, context=p_ctx.context),
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
    res_m = resolucao(context_actor_ref=MARCADOR, context_purpose=MARCADOR)
    assert MARCADOR in repr(res_m), "a fonte da E4.3 realmente expõe — por isso redigimos"

    p = proposta(governance_resolution=res_m)
    _sem_marcador(p, "Proposal→governance_resolution")
    _sem_marcador(envelope(proposal=p), "Envelope→proposal.governance_resolution")
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
