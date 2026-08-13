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

PIA_8003_COID_INVALID = ErrorCode(
    code="PIA-8003",
    default_message="coid_invalid",
    category=ErrorCategory.VALIDATION,
    http_status=422,
    severity=ErrorSeverity.WARNING,
)
"""Valor apresentado como COID não é um UUID válido (nem instância
`uuid.UUID` nem string parseável como UUID) — usado por
`CoidManager.validate()`/`validate_imported_coid()` (E3.2/LIB-02)."""

PIA_8004_COID_COLLISION = ErrorCode(
    code="PIA-8004",
    default_message="coid_collision",
    category=ErrorCategory.VALIDATION,
    http_status=409,
    severity=ErrorSeverity.ERROR,
)
"""Um COID já existe (ativo ou soft-deleted — identidade nunca é
reciclada) e não pode ser reutilizado para outro `CognitiveObject` —
usado tanto na criação local (`CoidManager.assert_unique`,
`ObjectRepository.add`) quanto na validação de COID importado
(E3.2/LIB-02)."""

PIA_8005_CLID_INVALID = ErrorCode(
    code="PIA-8005",
    default_message="clid_invalid",
    category=ErrorCategory.VALIDATION,
    http_status=422,
    severity=ErrorSeverity.WARNING,
)
"""Valor apresentado como CLID não é um UUID válido — usado por
`ClidManager.validate()`/`validate_imported_clid()` (E3.3/LIB-03).
Código próprio, distinto de `PIA-8003` (COID inválido) — mesma
categoria/status, mas entidades conceitualmente diferentes."""

PIA_8006_LINEAGE_SELF_LINK = ErrorCode(
    code="PIA-8006",
    default_message="lineage_self_link",
    category=ErrorCategory.VALIDATION,
    http_status=422,
    severity=ErrorSeverity.ERROR,
)
"""Tentativa de criar uma `LineageEdge` com `parent_coid == child_coid`
— um objeto não pode ser seu próprio descendente direto (E3.3/LIB-03,
§16)."""

PIA_8007_LINEAGE_DUPLICATE_EDGE = ErrorCode(
    code="PIA-8007",
    default_message="lineage_duplicate_edge",
    category=ErrorCategory.VALIDATION,
    http_status=409,
    severity=ErrorSeverity.ERROR,
)
"""Tentativa de registrar novamente a mesma tripla
`(parent_coid, child_coid, relation_type)` já existente (E3.3/LIB-03,
§17) — nenhuma duplicação silenciosa."""

PIA_8008_LINEAGE_ENDPOINT_NOT_FOUND = ErrorCode(
    code="PIA-8008",
    default_message="lineage_endpoint_not_found",
    category=ErrorCategory.VALIDATION,
    http_status=404,
    severity=ErrorSeverity.ERROR,
)
"""`parent_coid` ou `child_coid` de uma `LineageEdge` não corresponde a
nenhum `CognitiveObject` existente (ativo ou soft-deleted — soft
delete não invalida um endpoint de lineage, §33) — violação da FK
traduzida para erro de domínio (E3.3/LIB-03, §32)."""

ALL_COGNITIVE_ERROR_CODES: tuple[ErrorCode, ...] = (
    PIA_8001_IDENTITY_IMMUTABLE,
    PIA_8002_CLID_ALREADY_SET,
    PIA_8003_COID_INVALID,
    PIA_8004_COID_COLLISION,
    PIA_8005_CLID_INVALID,
    PIA_8006_LINEAGE_SELF_LINK,
    PIA_8007_LINEAGE_DUPLICATE_EDGE,
    PIA_8008_LINEAGE_ENDPOINT_NOT_FOUND,
)

COGNITIVE_ERROR_CODE_BY_CODE: dict[str, ErrorCode] = {
    ec.code: ec for ec in ALL_COGNITIVE_ERROR_CODES
}
