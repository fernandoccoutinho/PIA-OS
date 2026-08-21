"""`E5_APPROVAL_VALIDATION_STEP` — função pura sobre o validador PIAP.

Produz `approval_validation_outcome` **exatamente uma vez** por avaliação,
antes da montagem em `E5.j`. Não concede autoridade, não renova, não consulta
serviço nenhum.

```text
E5_VALIDATES_BUT_DOES_NOT_GRANT_APPROVAL = TRUE
APPROVAL_VALIDATION_OUTCOME_IS_NEVER_NONE = TRUE
```
"""

from __future__ import annotations

from datetime import datetime

from app.predictive_accessibility.piap.authority import AuthorityContext, validate_approval
from app.predictive_accessibility.piap.enums import ApprovalValidationOutcome, BoundObjectKind
from app.predictive_accessibility.piap.envelope import PiapEnvelope


def predictive_approval_validation(
    envelope: PiapEnvelope,
    *,
    at: datetime,
    expected_version: int,
    required_scope: tuple[str, ...],
    expected_jurisdiction: str | None,
    expected_binding_kind: BoundObjectKind,
) -> ApprovalValidationOutcome:
    if not isinstance(envelope, PiapEnvelope):
        raise TypeError(f"envelope deve ser PiapEnvelope, recebido {type(envelope).__name__}")
    contexto: AuthorityContext = envelope.authority
    vinculo = contexto.approval.bound_to if contexto.approval is not None else None
    if vinculo is None or vinculo.kind is not expected_binding_kind:
        return (
            ApprovalValidationOutcome.MISSING
            if vinculo is None
            else (ApprovalValidationOutcome.BINDING_MISMATCH)
        )
    return validate_approval(
        contexto,
        at=at,
        expected_version=expected_version,
        required_scope=required_scope,
        expected_jurisdiction=expected_jurisdiction,
        expected_binding=vinculo,
    )
