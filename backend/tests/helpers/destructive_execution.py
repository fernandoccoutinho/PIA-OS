"""
Construtores compartilhados da composição destrutiva (`E4.9.9.d`).

```text
ALTERNATIVE_ENVELOPE != PATCHED_INVALID_STATE
```

Toda variante usada nos testes de divergência é montada pelos
**construtores públicos** e é integralmente válida por si. Nenhum
`object.__setattr__`, `monkeypatch`, `dataclasses.replace` sobre
invariante ou bypass de validação: a lição da E4.5.2 é que uma
adulteração que os construtores recusariam prova apenas que eles
funcionam, e não o que o teste queria medir.

O módulo vive em `tests/` e **nada** aqui é exportado por `backend/app`.
"""

import uuid
from datetime import UTC, datetime, timedelta

from app.memory.models.approval_enums import (
    AssuranceLevel,
    DestructiveOperation,
    ImpactVolumeKind,
    InputChannel,
    VoiceReviewState,
)
from app.memory.models.erasure_enums import ErasureTargetClass
from app.memory.models.governance_enums import GovernanceOutcome
from app.memory.models.target_resolution_enums import (
    LegacyProtectionState,
    ReferenceOrigin,
)
from app.memory.schemas.destructive_approval import (
    OPERACAO_DE_GOVERNANCA,
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
    ErasureTargetDescriptor,
    ErasureTargetReference,
    ReferenceProvenance,
    VerifiedDeletionCapability,
)
from app.memory.schemas.governance import GovernanceResolution

TENANT = uuid.UUID("00000000-0000-0000-0000-0000000ddd01")
WORKSPACE = uuid.UUID("00000000-0000-0000-0000-0000000ddd02")
DOMINIO = uuid.UUID("00000000-0000-0000-0000-0000000ddd03")
POLICY_ID = uuid.UUID("00000000-0000-0000-0000-0000000ddd04")
PRINCIPAL = "principal:humano-d"
FINALIDADE = "purpose:remocao-titular"
REGRA = "rule-1"
"""Identificador de regra **textual opaco** — o valor real do projeto.

```text
OPAQUE_RULE_REFERENCE != UUID
```
"""

SUJEITO_A = uuid.UUID("00000000-0000-0000-0000-0000000aaa01")
SUJEITO_B = uuid.UUID("00000000-0000-0000-0000-0000000aaa02")


def escopo(principal: str = PRINCIPAL) -> ControlScope:
    return ControlScope(WORKSPACE, TENANT, principal)


def custodia(namespace: str = "workspace/w1/a") -> CustodyNamespace:
    return CustodyNamespace("pia-storage", namespace)


def procedencia(posicao: int = 0) -> ReferenceProvenance:
    return ReferenceProvenance(ReferenceOrigin.OUTPUT_REFS, posicao)


def instante(deslocamento_horas: int = -1) -> datetime:
    return datetime.now(UTC).replace(microsecond=0) + timedelta(hours=deslocamento_horas)


def snapshot(
    *,
    subject_coid: uuid.UUID = SUJEITO_A,
    target_class: ErasureTargetClass = ErasureTargetClass.PIA_MANAGED_ARTIFACT,
    control_scope: ControlScope | None = None,
    custody_namespace: CustodyNamespace | None = None,
    origin: ReferenceProvenance | None = None,
    legacy_protection_state: LegacyProtectionState = LegacyProtectionState.NOT_PROTECTED,
    version_etag: str | None = 'W/"v1"',
) -> SafeTargetSnapshot:
    return SafeTargetSnapshot(
        target_class,
        subject_coid,
        control_scope or escopo(),
        custody_namespace or custodia(),
        origin if origin is not None else procedencia(),
        legacy_protection_state,
        version_etag,
    )


def descritor(
    *,
    subject_coid: uuid.UUID = SUJEITO_A,
    target_class: ErasureTargetClass = ErasureTargetClass.PIA_MANAGED_ARTIFACT,
    control_scope: ControlScope | None = None,
    custody_namespace: CustodyNamespace | None = None,
    origin: ReferenceProvenance | None = None,
    legacy_protection_state: LegacyProtectionState = LegacyProtectionState.NOT_PROTECTED,
    version_etag: str | None = 'W/"v1"',
    transient_locator: str = "s3://pia-storage/workspace/w1/a/objeto-1",
    capability_operation: str = "delete_object",
) -> ErasureTargetDescriptor:
    """Descritor **fresco**, sempre com capacidade verificada."""
    return ErasureTargetDescriptor(
        target_class=target_class,
        subject_coid=subject_coid,
        control_scope=control_scope or escopo(),
        custody_namespace=custody_namespace or custodia(),
        capability=VerifiedDeletionCapability(
            operation=capability_operation,
            scope="workspace/w1/*",
            verified=True,
        ),
        resolved_at=instante(0),
        origin=origin if origin is not None else procedencia(),
        legacy_protection_state=legacy_protection_state,
        transient_locator=transient_locator,
        version_etag=version_etag,
    )


def referencia(
    *,
    subject_coid: uuid.UUID = SUJEITO_A,
    control_scope: ControlScope | None = None,
    origin: ReferenceProvenance | None = None,
    expected_namespace: CustodyNamespace | None = None,
    opaque_reference: str = "ref:legada:objeto-1",
) -> ErasureTargetReference:
    return ErasureTargetReference(
        subject_coid=subject_coid,
        opaque_reference=opaque_reference,
        origin=origin if origin is not None else procedencia(),
        control_scope=control_scope or escopo(),
        expected_namespace=expected_namespace,
    )


def resolucao(
    operacao: DestructiveOperation = DestructiveOperation.MOVE_TO_TRASH,
    *,
    principal: str = PRINCIPAL,
    policy_id: uuid.UUID | None = POLICY_ID,
    policy_key: str | None = "gov.erasure",
    policy_version: int | None = 3,
    matched_rule_id: str | None = REGRA,
) -> GovernanceResolution:
    """Resolução `ADMISSIBLE` com proveniência local.

    Os quatro campos de proveniência são parametrizáveis porque a E4.3 os
    declara opcionais — e a composição precisa provar que recusa quando
    falta qualquer um, em vez de completar com default.
    """
    return GovernanceResolution(
        outcome=GovernanceOutcome.ADMISSIBLE,
        operation=OPERACAO_DE_GOVERNANCA[operacao],
        context_domain_ids=(DOMINIO,),
        context_actor_ref=principal,
        context_purpose=FINALIDADE,
        safety_boundary_version=1,
        safety_rationale="titular pediu remoção",
        policy_key=policy_key,
        policy_version=policy_version,
        policy_id=policy_id,
        matched_rule_id=matched_rule_id,
        declared_losses=("conteúdo do artefato",),
    )


def envelope(
    *,
    operacao: DestructiveOperation = DestructiveOperation.MOVE_TO_TRASH,
    alvos: tuple[SafeTargetSnapshot, ...] | None = None,
    approval_id: uuid.UUID | None = None,
    nonce: uuid.UUID | None = None,
    janela: timedelta = timedelta(hours=8),
    governanca: GovernanceResolution | None = None,
    assurance: AssuranceLevel | None = None,
    canal: InputChannel = InputChannel.TEXT,
    revisao: VoiceReviewState = VoiceReviewState.NOT_APPLICABLE,
    principal: str = PRINCIPAL,
    confirmado_ha_horas: int = 1,
) -> DestructiveApprovalEnvelope:
    """Envelope aprovado, integralmente válido pelos construtores públicos.

    `confirmado_ha_horas` desloca toda a linha do tempo para trás. Com
    `janela` menor que o deslocamento, o envelope nasce **já vencido** —
    e continua integralmente válido: `EXPIRES_AT_PRESENT != EXPIRY_
    ENFORCED`, e quem impõe o vencimento é o `clock_timestamp()` do banco.
    Alterar `expires_at` por SQL seria impossível de qualquer forma: a
    trigger da E4.9.9.a torna todo campo de binding imutável.
    """
    agora = instante(-confirmado_ha_horas)
    alvos = alvos or (snapshot(),)
    contexto = ApprovalContext(TENANT, WORKSPACE, DOMINIO, FINALIDADE)
    proveniencia = SafeVoiceProvenance(canal, revisao)
    if assurance is None:
        assurance = (
            AssuranceLevel.STEP_UP_VERIFIED
            if operacao is DestructiveOperation.PERMANENT_ERASURE
            else AssuranceLevel.AUTHENTICATED
        )
    proposta = DestructiveApprovalProposal(
        operation=operacao,
        targets=alvos,
        impact=PresentedImpact(len(alvos), ImpactVolumeKind.KNOWN, 4096),
        governance_resolution=governanca or resolucao(operacao, principal=principal),
        context=contexto,
        provenance=proveniencia,
        blockers=(),
        materialized_at=agora,
    )
    return DestructiveApprovalEnvelope(
        proposal=proposta,
        approval_id=approval_id or uuid.uuid4(),
        nonce=nonce or uuid.uuid4(),
        identity=IdentityEvidence(principal, assurance, agora),
        context=contexto,
        provenance=proveniencia,
        issued_at=agora,
        confirmed_at=agora,
        expires_at=agora + janela,
    )
