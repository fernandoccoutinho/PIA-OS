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


PIA_8032_CONSOLIDATION_VERIFICATION_FAILED = ErrorCode(
    code="PIA-8032",
    default_message="consolidation_verification_failed",
    category=ErrorCategory.SYSTEM,
    http_status=500,
    severity=ErrorSeverity.ERROR,
)
"""Falha de pós-condição de uma consolidação (`E4.5`).

Cobre divergência em **qualquer** das duas fronteiras verificadas
(corretivo E4.5.2):

```text
request ↔ receipt                 — a porta devolveu fontes ou
                                     predecessores diferentes dos pedidos
receipt ↔ persistence assessment  — o patrimônio observado não
                                     corresponde ao que o recibo afirma
```

    REQUEST FIDELITY != PERSISTENCE COHERENCE
    BOTH ARE REQUIRED

No segundo caso, o recibo devolvido pela porta E3 e o
`PersistenceAssessment` da E4.4 descrevem coisas diferentes sobre o
mesmo alvo.

A E4.5 não conclui uma consolidação com base apenas no recibo de quem
escreveu. O assessment da E4.4 é a prova **independente**, lida do
patrimônio dentro da mesma transação, de que

    S1 ← {M1, ..., Mn}

ficou de fato materializado. Divergência entre os dois significa que a
consolidação não é o que o recibo afirma, e a única resposta correta é
interromper:

    AUTO_DESTRUCTIVE_REPAIR = FORBIDDEN
    MISMATCH != AUTHORIZATION TO FABRICATE OR REPAIR HISTORY

Nada é reparado, nada é apagado, nada é absorvido — a exceção sobe e o
rollback da `UnitOfWork` do chamador desfaz a operação inteira.

Categoria `SYSTEM`, e não `VALIDATION`: chegar aqui não significa que o
chamador pediu algo inválido — isso já foi recusado no preflight — e
sim que a escrita e a leitura do patrimônio discordam entre si.
(`ErrorCategory` é vocabulário fechado em `app/core/error_codes.py` e
não tem `INTERNAL`; `SYSTEM` é a categoria existente que descreve uma
inconsistência interna, e ampliá-lo por conveniência da E4.5 seria
mexer num contrato de E1/E2 fora do escopo deste módulo.)

`PIA-8032` é o próximo código **global** livre — a faixa `PIA-8xxx` é
única no projeto, e a E3.4.2 ocupou `PIA-8029`..`PIA-8031`."""


PIA_8033_RETRIEVAL_DUPLICATE_COID = ErrorCode(
    code="PIA-8033",
    default_message="retrieval_duplicate_coid",
    category=ErrorCategory.SYSTEM,
    http_status=500,
    severity=ErrorSeverity.ERROR,
)
"""A Search devolveu o mesmo COID mais de uma vez para a mesma vista
(`E4.6`).

A E4.6 **não desduplica** patrimônio: objetos com o mesmo CLID, uma
consolidação e suas fontes, revisões `CURRENT` e `SUPERSEDED` — todos
permanecem distintos, porque são cognitivamente distintos.

    DIVERGENCE != INVALIDITY
    CONSOLIDATION != SOURCE REPLACEMENT

O mesmo **COID** repetido é outra coisa: é a mesma identidade aparecendo
duas vezes, o que só pode ser defeito de composição — da porta, do
recorte de domínio ou da paginação em lotes. Escolher uma das ocorrências
em silêncio seria decidir qual versão do patrimônio o chamador vê, sem
que ninguém tenha pedido isso.

Categoria `SYSTEM`, e não `VALIDATION`: o chamador não pediu nada
inválido; a composição interna é que produziu resultado incoerente."""


PIA_8034_RETRIEVAL_CONTRACT_VIOLATION = ErrorCode(
    code="PIA-8034",
    default_message="retrieval_contract_violation",
    category=ErrorCategory.SYSTEM,
    http_status=500,
    severity=ErrorSeverity.ERROR,
)
"""Uma pós-condição do Retrieval foi violada (`E4.6.1`).

Cobre as fronteiras que a E4.6 original deixava sem verificação:

```text
REQUEST ↔ VALIDATED CONTEXT      o validador confirmou, mas substituiu
REQUEST ↔ GOVERNANCE RESOLUTION  autorizou outra operação ou outra policy
SEARCH PORT ↔ COGNITIVE VIEW     hit malformado, ou retorno não iterável
```

O ponto comum das três: verificar apenas
`resolution.execution_authorized` não diz **qual operação** nem **qual
policy** produziram aquela autorização, e filtrar um hit antes de
validar sua forma transforma dado malformado em ausência legítima.

    AUTHORIZATION TO TRANSFORM != AUTHORIZATION TO READ
    REQUESTED POLICY           != RESOLVED POLICY
    CONTEXT VALIDATION         != CONTEXT SUBSTITUTION
    PORT CONTRACT VIOLATION    != EMPTY VIEW
    MALFORMED EVIDENCE         != NO MATCH

Categoria `SYSTEM`, não `VALIDATION`: o chamador não pediu nada
inválido — quem devolveu resposta incoerente foi um colaborador
interno.

Distinto de `PIA-8033`, que continua significando **exclusivamente**
COID duplicado."""


PIA_8035_ACCESSIBILITY_POLICY_VERSION_EXISTS = ErrorCode(
    code="PIA-8035",
    default_message="accessibility_policy_version_exists",
    category=ErrorCategory.VALIDATION,
    http_status=409,
    severity=ErrorSeverity.ERROR,
)
"""Já existe uma versão publicada com este `(policy_key, version)`
(`E4.7`).

Versões publicadas são imutáveis: mudar semântica exige publicar uma
versão nova, nunca reescrever a anterior. A autoridade final é
`UNIQUE(policy_key, version)` no banco — o repositório traduz a violação
para este diagnóstico, inclusive quando duas sessões concorrentes tentam
publicar a mesma versão ao mesmo tempo.

Categoria `VALIDATION`: o pedido é que está errado, e o chamador pode
corrigi-lo publicando outra versão. Espelha `PIA-8027`, o equivalente da
E4.3."""


PIA_8036_ACCESSIBILITY_POLICY_IMMUTABLE = ErrorCode(
    code="PIA-8036",
    default_message="accessibility_policy_immutable",
    category=ErrorCategory.VALIDATION,
    http_status=409,
    severity=ErrorSeverity.ERROR,
)
"""Tentativa de `UPDATE` ou `DELETE` numa versão publicada (`E4.7`).

Levantado tanto pelo override do repositório quanto pelo evento de
mapper — a segunda camada existe porque a E4.3.1 reproduziu o defeito
**contornando** o repositório, mutando o objeto carregado e chamando
`commit()`.

    POLICY IMMUTABILITY INCLUDES PRESERVING ITS AUTHORITY ENVELOPE

Espelha `PIA-8028`, o equivalente da E4.3."""


PIA_8037_ACCESSIBILITY_TRANSITION_CONTRACT_VIOLATION = ErrorCode(
    code="PIA-8037",
    default_message="accessibility_transition_contract_violation",
    category=ErrorCategory.SYSTEM,
    http_status=500,
    severity=ErrorSeverity.ERROR,
)
"""Uma pós-condição da transição de acessibilidade foi violada (`E4.7`).

Cobre as fronteiras que o caminho canônico verifica:

```text
REQUEST ↔ VALIDATED CONTEXT        o validador confirmou, mas substituiu
REQUEST ↔ GOVERNANCE RESOLUTION    autorizou outra operação ou outra policy
SUBJECT ↔ CAUSAL EVIDENCE          evento inexistente ou de outro COID
PORT ↔ OBSERVED POSTCONDITION      o estado escrito não é o autorizado
```

Mesma disciplina de `PIA-8032` (E4.5) e `PIA-8034` (E4.6): carrega
**todos** os motivos detectados, nada é reparado, e a exceção sobe para
que o rollback da `UnitOfWork` do chamador desfaça a operação.

    AUTO_DESTRUCTIVE_REPAIR = FORBIDDEN
    MISSING EVIDENCE != AUTHORIZATION TO FABRICATE HISTORY

Categoria `SYSTEM`, não `VALIDATION`: chegar aqui não significa pedido
inválido — isso já foi recusado no preflight — e sim que colaboradores
internos discordam entre si."""


PIA_8038_ACCESSIBILITY_SUBJECT_NOT_FOUND = ErrorCode(
    code="PIA-8038",
    default_message="accessibility_subject_not_found",
    category=ErrorCategory.VALIDATION,
    http_status=404,
    severity=ErrorSeverity.ERROR,
)
"""Não existe `CognitiveObject` com o COID informado (`E4.7`).

Diagnóstico **próprio**, distinto de qualquer desfecho de policy: um
objeto ausente não é uma transição negada, é um pedido sobre algo que
não existe.

A busca usa `include_deleted=True`. Um objeto com exclusão lógica
**existe** e é sujeito legítimo — a E4.7 não o reativa e nunca toca
`deleted_at`:

    SOFT_DELETED != NEVER EXISTED
    SOFT_DELETED != SUBJECT_NOT_FOUND"""


PIA_8039_ISOLATION_SCOPE_REQUIRED = ErrorCode(
    code="PIA-8039",
    default_message="isolation_scope_required",
    category=ErrorCategory.VALIDATION,
    http_status=400,
    severity=ErrorSeverity.ERROR,
)
"""Pedido de recuperação isolada sem domínio explícito (`E4.8`).

```text
EMPTY MEMORY CONTEXT IS VALID
ZERO-DOMAIN OBJECT IS VALID
EMPTY DOMAIN SCOPE IS NOT AN ISOLATION BOUNDARY
```

Contexto vazio continua válido na E4.2 e a E4.6 continua funcionando com
ele. O que a E4.8 recusa é tratar "sem domínio" como "todos os domínios
isolados" — silenciosamente, seria a expansão de escopo que este módulo
existe para impedir.

**Não** significa inexistência de patrimônio. Categoria `VALIDATION`: o
pedido é que está incompleto, e o chamador o corrige declarando o
escopo."""


PIA_8040_ISOLATION_CONTRACT_VIOLATION = ErrorCode(
    code="PIA-8040",
    default_message="isolation_contract_violation",
    category=ErrorCategory.SYSTEM,
    http_status=500,
    severity=ErrorSeverity.ERROR,
)
"""Desacordo entre pedido, contexto, resoluções, snapshot e vista (`E4.8`).

Cobre as fronteiras que o caminho isolado verifica:

```text
REQUEST  ↔ VALIDATED CONTEXT      o validador confirmou, mas substituiu
REQUEST  ↔ SINGLETON RESOLUTION   autorizou outro domínio, ator ou propósito
REQUEST  ↔ RETRIEVAL RESULT       a vista cita outro contexto ou paginação
SNAPSHOT ↔ RETURNED COIDS         vazamento fora do escopo autorizado
```

Mesma disciplina de `PIA-8032`, `PIA-8034` e `PIA-8037`: acumula **todos**
os motivos detectáveis sem reflexão, nada é reparado, e a exceção sobe.

```text
LEAK DETECTED != AUTHORIZATION TO SILENTLY FILTER
AUTO_DESTRUCTIVE_REPAIR = FORBIDDEN
```

Categoria `SYSTEM`, não `VALIDATION`: chegar aqui não significa pedido
inválido — isso já foi recusado antes — e sim que colaboradores internos
discordam entre si. Uma decisão `INADMISSIBLE`, `NOT_APPLICABLE` ou
`PROHIBITED` é resultado válido de autoridade, **nunca** esta exceção."""


PIA_8041_ERASURE_RECORD_IMMUTABLE = ErrorCode(
    code="PIA-8041",
    default_message="erasure_record_immutable",
    category=ErrorCategory.VALIDATION,
    http_status=409,
    severity=ErrorSeverity.ERROR,
)
"""Tentativa de alterar ou remover um recibo de apagamento (`E4.9.5`).

Um `ErasureRecord` é append-only nas três camadas — eventos de mapper,
repositório e trigger no PostgreSQL. Este código nomeia a recusa das
duas primeiras.

Não há "corrigir o recibo": ele registra o que foi **observado** numa
tentativa material. Se a observação estava errada, o fato novo é uma
observação nova, não a reescrita da anterior — mesma disciplina de
`PIA-8028` e `PIA-8036` para versões publicadas, com um motivo
adicional:

```text
ERASING THE RECEIPT OF AN ERASURE = MAKING DESTRUCTION UNAUDITABLE
```
"""


PIA_8042_RETENTION_POLICY_VERSION_EXISTS = ErrorCode(
    code="PIA-8042",
    default_message="retention_policy_version_exists",
    category=ErrorCategory.VALIDATION,
    http_status=409,
    severity=ErrorSeverity.ERROR,
)
"""A versão de `RetentionPolicy` já existe (`E4.9.6`).

Recusa determinística, nunca absorção silenciosa como idempotência —
mesmo padrão de `PIA-8027` e `PIA-8035`. Sobrescrever a versão
apagaria a regra sob a qual itens se tornaram elegíveis a avaliação, e
a pergunta "sob qual regra isto foi avaliado?" deixaria de ter
resposta.
"""

PIA_8043_RETENTION_POLICY_IMMUTABLE = ErrorCode(
    code="PIA-8043",
    default_message="retention_policy_immutable",
    category=ErrorCategory.VALIDATION,
    http_status=409,
    severity=ErrorSeverity.ERROR,
)
"""Tentativa de alterar ou remover uma versão publicada (`E4.9.6`).

Correção semântica cria versão nova. Vale aqui a mesma disciplina de
`PIA-8028`, `PIA-8036` e `PIA-8041`.
"""

PIA_8044_APPROVAL_RECORD_NOT_USABLE = ErrorCode(
    code="PIA-8044",
    default_message="approval_record_not_usable",
    category=ErrorCategory.VALIDATION,
    http_status=409,
    severity=ErrorSeverity.ERROR,
)
"""A aprovação não pôde ser consumida ou revogada (`E4.9.9.a`).

Carrega um `ApprovalUsageRefusalReason` fechado: não encontrada, já
consumida, revogada, expirada, binding divergente, linha inválida ou
corrida concorrente perdida.

```text
BOOLEAN_OUTCOME = FORBIDDEN
```

`False` não distinguiria "expirada" de "binding divergente", e a segunda
hipótese é sinal que ninguém deveria perder.
"""

PIA_8045_APPROVAL_RECORD_IMMUTABLE = ErrorCode(
    code="PIA-8045",
    default_message="approval_record_immutable",
    category=ErrorCategory.VALIDATION,
    http_status=409,
    severity=ErrorSeverity.ERROR,
)
"""Tentativa de reescrever binding ou remover a trilha de aprovação
(`E4.9.9.a`).

Mesma disciplina de `PIA-8041` e `PIA-8043`: o registro admite **uma**
transição de ciclo de vida e nada mais.
"""

PIA_8046_APPROVAL_RECORD_PERSISTED_ROW_INVALID = ErrorCode(
    code="PIA-8046",
    default_message="approval_record_persisted_row_invalid",
    category=ErrorCategory.VALIDATION,
    http_status=500,
    severity=ErrorSeverity.ERROR,
)
"""Uma linha persistida não reconstrói contrato válido (`E4.9.9.a`).

Falha **controlada e tipada**. A alternativa — devolver um objeto
tolerante — transformaria linha corrompida em aprovação utilizável, que é
exatamente o que a revalidação existe para impedir.
"""
