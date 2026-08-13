"""
Catálogo de códigos de erro do domínio cognitivo — faixa `PIA-8xxx`.

Decisão registrada em `docs/entregas/entrega-3/E3_DEPENDENCY_MAP.md`
("Error Code Integration Status"): `ERROR_CODE_INTEGRATION_STATUS =
RESOLVED` via Opção B — este catálogo usa os tipos públicos de
`app.core.error_codes` (`ErrorCode`, `ErrorCategory`, `ErrorSeverity`)
sem editar `app/core/error_codes.py` nem `ALL_ERROR_CODES`. Um código
`PIA-8xxx` aqui **não aparece** no mapa reverso `ERROR_CODE_BY_CODE`
de E1/E2 — consequência aceita da decisão.

Apenas os códigos realmente necessários a `LIB-01` são criados aqui —
nenhuma reserva preventiva (§16 do módulo E3.1).
"""

from app.core.error_codes import ErrorCategory, ErrorCode, ErrorSeverity

PIA_8001_IDENTITY_IMMUTABLE = ErrorCode(
    code="PIA-8001",
    default_message="cognitive_object_identity_immutable",
    category=ErrorCategory.VALIDATION,
    http_status=409,
    severity=ErrorSeverity.ERROR,
)
"""Tentativa de reatribuir o COID (`id`) de um `CognitiveObject` já
persistido. Ver `E3_DOMAIN_MODEL_DRAFT.md`: "coid é atribuído uma
única vez, na criação, e nunca é reatribuído"."""

PIA_8002_CLID_ALREADY_SET = ErrorCode(
    code="PIA-8002",
    default_message="cognitive_object_clid_already_set",
    category=ErrorCategory.VALIDATION,
    http_status=409,
    severity=ErrorSeverity.ERROR,
)
"""Tentativa de sobrescrever um `clid` já atribuído fora do mecanismo
de `LIB-03 CLID Manager`/`TransformationRecord`/`LineageEdge` (que
ainda não existem em E3.1). Ver `E3_DOMAIN_MODEL_DRAFT.md`: "clid ...
nunca substituído por outro valor não-None sem passar por
TransformationRecord/LineageEdge explícito"."""

ALL_COGNITIVE_ERROR_CODES: tuple[ErrorCode, ...] = (
    PIA_8001_IDENTITY_IMMUTABLE,
    PIA_8002_CLID_ALREADY_SET,
)

COGNITIVE_ERROR_CODE_BY_CODE: dict[str, ErrorCode] = {
    ec.code: ec for ec in ALL_COGNITIVE_ERROR_CODES
}
