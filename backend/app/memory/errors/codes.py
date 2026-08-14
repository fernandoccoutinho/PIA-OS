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

PIA_8026_CONTEXT_UNKNOWN_DOMAIN_REFERENCE = ErrorCode(
    code="PIA-8026",
    default_message="context_unknown_domain_reference",
    category=ErrorCategory.VALIDATION,
    http_status=404,
    severity=ErrorSeverity.ERROR,
)
"""Um `MemoryContext` referencia `MemoryDomain`(s) que não existem.

Código próprio, e não reúso de `PIA-8023`, porque a informação
diagnóstica tem outra forma: um contexto pode referenciar vários
domínios de uma vez, e reportar um por vez forçaria N tentativas para
descobrir N referências ruins. A exceção correspondente carrega o
**conjunto** de ids desconhecidos.

`DOMAIN NOT FOUND != COGNITIVE OBJECT NOT FOUND` — a distinção
diagnóstica de E4.1 é preservada, não colapsada."""

PIA_8027_GOVERNANCE_POLICY_VERSION_EXISTS = ErrorCode(
    code="PIA-8027",
    default_message="governance_policy_version_exists",
    category=ErrorCategory.VALIDATION,
    http_status=409,
    severity=ErrorSeverity.ERROR,
)
"""Já existe uma versão com este `(policy_key, version)`.

Versões publicadas são imutáveis: mudança semântica cria versão nova.
Aceitar a segunda escrita como atualização apagaria em silêncio a
policy que fundamentou decisões passadas — e nenhuma delas poderia
mais ser explicada."""

PIA_8028_GOVERNANCE_POLICY_IMMUTABLE = ErrorCode(
    code="PIA-8028",
    default_message="governance_policy_immutable",
    category=ErrorCategory.VALIDATION,
    http_status=409,
    severity=ErrorSeverity.ERROR,
)
"""Tentativa de alterar ou remover uma `GovernancePolicy` publicada.

Corretivo `E4.3.1`. A E4.3 **afirmava** imutabilidade e não a impunha:
o repositório herdava `update()`/`delete()` de `BaseRepository`, e uma
mutação ORM seguida de `commit()` adulterava a versão publicada sem
criar versão nova — reproduzido antes da correção.

É a mesma dívida que a E3.3.1 fechou em `LineageEdge`, onde a
docstring dizia "append-only por construção" sem que nada aplicasse a
regra."""
