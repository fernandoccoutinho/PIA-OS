"""Sub-camada protocolar PIAP (`E5.a`)."""

from app.predictive_accessibility.piap.authority import (
    ApprovalBinding,
    AuthorityContext,
    BoundObjectRef,
    validate_approval,
)
from app.predictive_accessibility.piap.enums import (
    ApprovalValidationOutcome,
    AuthorityStatus,
    BoundObjectKind,
    PiapContractVersion,
    TemporalAvailability,
)
from app.predictive_accessibility.piap.envelope import (
    ClaimSubject,
    Horizon,
    PiapEnvelope,
    ProvenanceKind,
    ProvenanceRecord,
    SourceReference,
    deserialize_piap_envelope,
    serialize_piap_envelope,
)
from app.predictive_accessibility.piap.version import (
    SUPPORTED_VERSIONS,
    require_supported_version,
)

__all__ = [
    "SUPPORTED_VERSIONS",
    "ApprovalBinding",
    "ApprovalValidationOutcome",
    "AuthorityContext",
    "AuthorityStatus",
    "BoundObjectKind",
    "BoundObjectRef",
    "ClaimSubject",
    "Horizon",
    "PiapContractVersion",
    "PiapEnvelope",
    "ProvenanceKind",
    "ProvenanceRecord",
    "SourceReference",
    "TemporalAvailability",
    "deserialize_piap_envelope",
    "require_supported_version",
    "serialize_piap_envelope",
    "validate_approval",
]
