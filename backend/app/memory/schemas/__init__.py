"""Schemas e value objects da camada de memória (E4)."""

from app.memory.schemas.destructive_approval import (
    ApprovalContext,
    DestructiveApprovalEnvelope,
    DestructiveApprovalProposal,
    IdentityEvidence,
    PresentedImpact,
    SafeTargetSnapshot,
    SafeVoiceProvenance,
)

__all__ = [
    "ApprovalContext",
    "DestructiveApprovalEnvelope",
    "DestructiveApprovalProposal",
    "IdentityEvidence",
    "PresentedImpact",
    "SafeTargetSnapshot",
    "SafeVoiceProvenance",
]

from app.memory.schemas.erasure_effect import (
    ConsumedApprovalEvidence,
    ErasureEffectRequest,
    ErasureEffectResult,
    MaterialAttemptNotStarted,
    ObservedAttemptResult,
)

__all__ += [
    "ConsumedApprovalEvidence",
    "ErasureEffectRequest",
    "ErasureEffectResult",
    "MaterialAttemptNotStarted",
    "ObservedAttemptResult",
]
