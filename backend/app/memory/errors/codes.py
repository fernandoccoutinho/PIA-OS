"""
Catálogo de códigos de erro da camada de memória — faixa `PIA-8xxx`.

Arquivo **próprio**: o catálogo de E3 (`app/cognitive/errors/codes.py`)
está congelado e não é tocado por esta entrega. A sequência numérica,
porém, continua de onde parou — `PIA-8022` foi o último de E3, e não
há colisão possível porque os códigos são únicos por valor, não por
arquivo.

Como em E3, estes códigos usam os tipos públicos de
`app.core.error_codes` sem editar `ALL_ERROR_CODES` — consequência já
aceita e registrada em `E3_DEPENDENCY_MAP.md`.

Apenas os códigos realmente necessários a E4.1 existem aqui. Nenhuma
reserva preventiva.
"""

from app.core.error_codes import ErrorCategory, ErrorCode, ErrorSeverity

PIA_8023_MEMORY_DOMAIN_NOT_FOUND = ErrorCode(
    code="PIA-8023",
    default_message="memory_domain_not_found",
    category=ErrorCategory.VALIDATION,
    http_status=404,
    severity=ErrorSeverity.ERROR,
)
"""O `domain_id` informado não corresponde a nenhum `MemoryDomain`.

Detectado por pré-checagem no repositório, antes da escrita — não para
substituir a FK (que continua sendo a autoridade final), mas para
tornar o diagnóstico determinado: `memory_domain_memberships` tem duas
FKs, e uma violação `23503` sozinha não diria qual delas falhou."""

PIA_8024_MEMORY_DOMAIN_MEMBERSHIP_DUPLICATE = ErrorCode(
    code="PIA-8024",
    default_message="memory_domain_membership_duplicate",
    category=ErrorCategory.VALIDATION,
    http_status=409,
    severity=ErrorSeverity.ERROR,
)
"""O par `(domain_id, coid)` já existe.

Rejeição determinística, seguindo o padrão real do projeto
(`LineageDuplicateEdgeError`, `RelationshipDuplicateError`) em vez de
absorver silenciosamente como idempotência: classificar duas vezes não
é um fato novo, e o chamador merece saber que sua premissa estava
errada."""

PIA_8025_MEMORY_DOMAIN_MEMBERSHIP_OBJECT_NOT_FOUND = ErrorCode(
    code="PIA-8025",
    default_message="memory_domain_membership_object_not_found",
    category=ErrorCategory.VALIDATION,
    http_status=404,
    severity=ErrorSeverity.ERROR,
)
"""O `coid` informado não corresponde a nenhum `CognitiveObject`.

Nenhum objeto é fabricado para acomodar a classificação — mesma
disciplina de `MISSING EVIDENCE != AUTHORIZATION TO FABRICATE`."""
