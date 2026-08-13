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

PIA_8009_LINEAGE_EDGE_IMMUTABLE = ErrorCode(
    code="PIA-8009",
    default_message="lineage_edge_immutable",
    category=ErrorCategory.VALIDATION,
    http_status=409,
    severity=ErrorSeverity.ERROR,
)
"""Tentativa de atualizar ou remover uma `LineageEdge` já persistida —
`LineageEdge` é append-only por decisão de domínio (E3.3/LIB-03,
correção E3.3.1, débito C2): nenhuma edge registrada pode ser mutada
ou apagada via `LineageRepository`."""

PIA_8010_TRANSFORMATION_RECORD_IMMUTABLE = ErrorCode(
    code="PIA-8010",
    default_message="transformation_record_immutable",
    category=ErrorCategory.VALIDATION,
    http_status=409,
    severity=ErrorSeverity.ERROR,
)
"""Tentativa de atualizar ou remover um `TransformationRecord` já
persistido — histórico append-only, mesma disciplina de
`LineageEdge`/`PIA-8009` (E3.4/LIB-04, §9)."""

PIA_8011_REVISION_STATUS_INVALID_TRANSITION = ErrorCode(
    code="PIA-8011",
    default_message="revision_status_invalid_transition",
    category=ErrorCategory.VALIDATION,
    http_status=409,
    severity=ErrorSeverity.ERROR,
)
"""Transição inválida de `revision_status` em `CognitiveObject`
(correção E3.4.0) — permitido apenas `None → CURRENT`,
`None → SUPERSEDED`, `CURRENT → SUPERSEDED` e valor → mesmo valor
(idempotente). `SUPERSEDED` nunca volta a `CURRENT`/`None`; `CURRENT`
nunca volta a `None`. Usado tanto pelo guard do modelo quanto por
`VersionManager.revise()` quando `source` já está `SUPERSEDED`."""

PIA_8012_REVISION_CURRENT_UNIQUENESS_VIOLATION = ErrorCode(
    code="PIA-8012",
    default_message="revision_current_uniqueness_violation",
    category=ErrorCategory.VALIDATION,
    http_status=409,
    severity=ErrorSeverity.ERROR,
)
"""Tentativa de tornar `CURRENT` um `CognitiveObject` quando outro
objeto com o **mesmo CLID** já é `CURRENT` (correção E3.4.1) — viola
o invariante `COUNT(CURRENT) <= 1` por CLID. Levantado tanto pela
pré-checagem em `VersionManager.revise()` (defesa em profundidade,
sujeita a TOCTOU) quanto pela tradução de violação do índice único
parcial `uq_cognitive_objects_one_current_per_clid` (autoridade
final, cobre concorrência real)."""

PIA_8013_RELATIONSHIP_SELF_LINK = ErrorCode(
    code="PIA-8013",
    default_message="relationship_self_link",
    category=ErrorCategory.VALIDATION,
    http_status=422,
    severity=ErrorSeverity.ERROR,
)
"""Tentativa de criar uma `Relationship` com `source_coid == target_coid`
— proibido globalmente nesta fase para todos os tipos (E3.5/LIB-05,
§11: nenhum dos 5 tipos tem caso de uso legítimo identificado para
auto-relação)."""

PIA_8014_RELATIONSHIP_DUPLICATE = ErrorCode(
    code="PIA-8014",
    default_message="relationship_duplicate",
    category=ErrorCategory.VALIDATION,
    http_status=409,
    severity=ErrorSeverity.ERROR,
)
"""Tentativa de registrar novamente a mesma relação — para tipos
`DIRECTED`, a tripla `(source_coid, target_coid, relationship_type)`;
para tipos `SYMMETRIC`, o par não ordenado `{a, b}` com o mesmo tipo
(E3.5/LIB-05, §10)."""

PIA_8015_RELATIONSHIP_ENDPOINT_NOT_FOUND = ErrorCode(
    code="PIA-8015",
    default_message="relationship_endpoint_not_found",
    category=ErrorCategory.VALIDATION,
    http_status=404,
    severity=ErrorSeverity.ERROR,
)
"""`source_coid` ou `target_coid` de uma `Relationship` não corresponde
a nenhum `CognitiveObject` existente — violação de FK traduzida para
erro de domínio (E3.5/LIB-05, §18, mesmo princípio de
`LineageEndpointNotFoundError`/`PIA-8008`)."""

PIA_8016_RELATIONSHIP_IMMUTABLE = ErrorCode(
    code="PIA-8016",
    default_message="relationship_immutable",
    category=ErrorCategory.VALIDATION,
    http_status=409,
    severity=ErrorSeverity.ERROR,
)
"""Tentativa de `update`/`delete` físico de uma `Relationship` já
persistida — histórico append-only (E3.5/LIB-05, §12: "alterar/remover
uma relação não deve apagar um fato histórico"). "Remoção" lógica é
`retire()` (marca `retired_at`), não delete físico."""

PIA_8017_PROVENANCE_RECORD_IMMUTABLE = ErrorCode(
    code="PIA-8017",
    default_message="provenance_record_immutable",
    category=ErrorCategory.VALIDATION,
    http_status=409,
    severity=ErrorSeverity.ERROR,
)
"""Tentativa de `update`/`delete` físico de um `ProvenanceRecord` já
persistido — histórico append-only (E3.6/LIB-06, §6: "provenance
representa fato histórico... não permitir UPDATE destrutivo/DELETE
físico"). Mesmo princípio de `LineageEdgeImmutableError`/
`TransformationRecordImmutableError`/`RelationshipImmutableError`."""

PIA_8018_ACCESSIBILITY_INVALID_TRANSITION = ErrorCode(
    code="PIA-8018",
    default_message="accessibility_invalid_transition",
    category=ErrorCategory.VALIDATION,
    http_status=422,
    severity=ErrorSeverity.ERROR,
)
"""Tentativa de transicionar `AccessibilityState` para
`CAUSALLY_EXTINCT` sem um `reason` explícito e não-vazio (E3.6/LIB-06)
— proxy interino para a exigência do Domain Model Draft de que essa
transição nunca seja o valor default nem efeito colateral de query
(§4 do Draft) — o mecanismo formal (`CausalHistoryEvent`) é `E3.9`,
ainda não implementado."""

PIA_8019_SEARCH_CRITERIA_INVALID = ErrorCode(
    code="PIA-8019",
    default_message="search_criteria_invalid",
    category=ErrorCategory.VALIDATION,
    http_status=422,
    severity=ErrorSeverity.ERROR,
)
"""Critérios de busca malformados (E3.8/LIB-08) — nenhuma dimensão
informada, janela temporal invertida, ou `limit`/`offset` negativos.

Deliberadamente **não** cobre "zero resultados": conjunto vazio é
resposta válida de uma consulta bem-formada, nunca erro (§25 do
módulo E3.8). Este é o único código novo de E3.8 — busca é read-only e
não introduz nenhuma outra condição de domínio."""


ALL_COGNITIVE_ERROR_CODES: tuple[ErrorCode, ...] = (
    PIA_8001_IDENTITY_IMMUTABLE,
    PIA_8002_CLID_ALREADY_SET,
    PIA_8003_COID_INVALID,
    PIA_8004_COID_COLLISION,
    PIA_8005_CLID_INVALID,
    PIA_8006_LINEAGE_SELF_LINK,
    PIA_8007_LINEAGE_DUPLICATE_EDGE,
    PIA_8008_LINEAGE_ENDPOINT_NOT_FOUND,
    PIA_8009_LINEAGE_EDGE_IMMUTABLE,
    PIA_8010_TRANSFORMATION_RECORD_IMMUTABLE,
    PIA_8011_REVISION_STATUS_INVALID_TRANSITION,
    PIA_8012_REVISION_CURRENT_UNIQUENESS_VIOLATION,
    PIA_8013_RELATIONSHIP_SELF_LINK,
    PIA_8014_RELATIONSHIP_DUPLICATE,
    PIA_8015_RELATIONSHIP_ENDPOINT_NOT_FOUND,
    PIA_8016_RELATIONSHIP_IMMUTABLE,
    PIA_8017_PROVENANCE_RECORD_IMMUTABLE,
    PIA_8018_ACCESSIBILITY_INVALID_TRANSITION,
    PIA_8019_SEARCH_CRITERIA_INVALID,
)

COGNITIVE_ERROR_CODE_BY_CODE: dict[str, ErrorCode] = {
    ec.code: ec for ec in ALL_COGNITIVE_ERROR_CODES
}
