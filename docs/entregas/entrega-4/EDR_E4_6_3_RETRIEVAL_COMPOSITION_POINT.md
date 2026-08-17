# EDR E4.6.3 — Retrieval Composition Point

**Natureza:** decisão arquitetural de composição no caminho de leitura.
**Exigido por:** a Tensão G do preflight da E4.9 —
`STOP_CONDITION = RETENTION_RETRIEVAL_COMPOSITION_GAP`.
**Complementa, sem reescrever:** `E4_6_MEMORY_RETRIEVAL.md`,
`E4_8_MEMORY_ISOLATION.md`, `EDR_COUT_PIA_E4.md`.

```text
COMPOSITION POINT != RETENTION DECISION
GATE REDUCES A RESPONSE
GATE DOES NOT ADD, REORDER, TRANSFORM OR REVEAL
```

---

## 1. O problema

O preflight da E4.9 constatou que a E4.6 filtra **antes** de paginar — o
que está correto — mas que **não existe ponto de injeção**:

- `_admissivel` é `@staticmethod` e tem lista de filtros fechada;
- `_Escopo` é `frozen` e carrega apenas `coids: frozenset | None`;
- os critérios atravessam o módulo **opacos** (`CriteriaT` contravariante,
  vocabulário da E3.8), e expiração de retenção não é nenhuma das
  dimensões de `SearchCriteria`, porque é calculada a partir de policy,
  não lida de coluna.

Restavam três caminhos, todos proibidos: filtrar **depois** da paginação,
**duplicar** o laço de coleta, ou **alterar** a E4.6 sem corretivo
próprio.

O dano da primeira alternativa foi medido, não argumentado: com 5 objetos
e `limit=3`, a página canônica sai com 3 itens e `has_more=True`;
descartar 1 item já paginado deixa 2 itens com `has_more` e `limit`
mentindo.

```text
POST-PAGINATION FILTERING = INCOMPLETE PAGE + LYING CONTRACT
```

---

## 2. Alternativas consideradas

| # | Alternativa | Por que foi rejeitada |
|---|---|---|
| 1 | filtrar depois da paginação | páginas incompletas e `has_more` falso — medido |
| 2 | duplicar o laço de coleta na E4.9 | segunda implementação de paginação, que divergiria da primeira |
| 3 | predicado guardado no construtor do manager | vira estado; duas chamadas passariam a interferir uma na outra |
| 4 | ampliar `SearchCriteria` com uma dimensão de retenção | o vocabulário de critérios pertence à E3.8, e expiração não é coluna |
| 5 | passar a lista de candidatos ao colaborador | ele poderia devolvê-la reordenada, aumentada ou reescrita |
| 6 | tornar a E4.6 *retention-aware* | acoplamento prematuro: a E4.6 é recuperação base |
| **7** | **gate tipado, por chamada, um candidato → um booleano** | **adotada** |

A alternativa 5 merece registro porque é a tentação natural — e é
exatamente onde a garantia se perde. Um colaborador que recebe a coleção
pode devolver outra; um que recebe **um candidato** e devolve **um
booleano** não tem por onde acrescentar, reordenar ou transformar.

```text
THE SHAPE OF THE CONTRACT IS THE GUARANTEE
```

### Correção posterior — E4.6.3.1

O parágrafo acima descreve o raciocínio da cadeia 68 e **estava
parcialmente errado**. A auditoria independente demonstrou que "não tem
por onde transformar" é falso: devolver apenas `bool` impede retornar
uma coleção, mas não impede **mutar o argumento compartilhado** antes da
projeção. Um gate hostil usou `object.__setattr__` no candidato e o COID
fabricado saiu no resultado.

```text
BOOLEAN RETURN   != IMMUTABLE ARGUMENT
SHARED REFERENCE != STRICTLY REDUCTIVE GATE
```

A formulação `THE SHAPE OF THE CONTRACT IS THE GUARANTEE` fica
registrada como **overclaim**: a forma do contrato governa o que o
colaborador pode *devolver*, e o `Protocol` somente-leitura governa o
código tipado — nenhum dos dois torna a instância concreta imutável em
runtime.

Formulação normativa que passa a valer:

```text
CONTRACT SHAPE GOVERNS THE RETURN
VALUE ISOLATION GOVERNS THE ARGUMENT
BOTH ARE REQUIRED
```

Corrigido pelo corretivo **E4.6.3.1** (cadeia 69), que entrega ao gate
um snapshot imutável por valor. Ver
`E4_6_3_1_ISOLATED_CANDIDATE_SNAPSHOT.md`.

---

## 3. A decisão

```python
@runtime_checkable
class RetrievalCandidateGatePort(Protocol):
    def allows(self, candidate: CognitiveObjectView) -> bool: ...
```

Injetado por chamada:

```python
MemoryRetrievalManager.retrieve(..., candidate_gate=None)
```

Keyword-only, opcional, **nunca armazenado**. Com `None`, o
comportamento é o da cadeia 67.

---

## 4. Posição exata no pipeline

```text
READ autorizado pela Governança
→ escopo base resolvido
→ Search retorna hit
→ contrato/formato do hit validado
→ admissibilidade base validada
→ duplicata validada
→ candidate_gate.allows(candidate)      ← aqui
→ offset sobre candidatos aprovados
→ projeção
→ limit + has_more
```

A posição não é arbitrária; cada vizinhança responde a um risco:

**Depois da governança** — o gate nunca é consultado sob recusa. Um gate
chamado antes da autoridade veria a existência de objetos que a
autoridade recusou revelar.

```text
GATE IS CONSULTED AFTER AUTHORITY, NEVER INSTEAD OF IT
```

**Depois do escopo base** — soft-deleted, inacessível e fora de domínio
não chegam ao gate. Ele filtra o que já é admissível, não decide
admissibilidade.

**Depois da validação de forma e da duplicata** — senão um gate poderia
**esconder** uma violação de contrato da Search devolvendo `False` para
o hit malformado ou para a duplicata. A violação continuaria existindo,
sem ninguém para reportá-la.

```text
GATE MUST NOT MASK A PORT CONTRACT VIOLATION
```

**Antes do `offset`** — `offset`, `limit`, preenchimento de página e
`has_more` contam somente aprovados. Contá-los antes descreveria uma
página que não é a devolvida.

**Dentro do laço de lotes** — rejeitar gera **backfill**, não buraco: a
coleta segue até `limit + 1` aprovados ou até a Search esgotar.

---

## 5. Por que injeção por chamada

Guardar o gate no manager o transformaria em estado, e estado
compartilhado entre chamadas é precisamente o que a E4.6 evitou desde o
início — ela não tem cache, sessão própria nem contexto implícito.

```text
GATE IS AN ARGUMENT, NOT STATE
```

Duas chamadas consecutivas ao mesmo manager podem usar gates distintos
sem interferência, e há teste que compara `vars(manager)` antes e depois
para provar que nada foi guardado.

---

## 6. Fail-closed

Duas falhas possíveis do colaborador, nenhuma podendo virar decisão
silenciosa sobre a vista:

```text
INVALID GATE RESULT  != EXCLUSION
INVALID GATE RESULT  != INCLUSION
COLLABORATOR FAILURE != EMPTY VIEW
```

**Tipo exato.** `type(resultado) is bool`, e não `isinstance`, porque
`bool` é subclasse de `int` e `isinstance(1, int)` não separaria `True`
de `1`. Coagir com `bool(...)` seria pior: um gate que devolvesse `None`
por engano excluiria tudo, e a vista vazia pareceria legítima.

**Exceção.** Propagar crua faria uma falha do colaborador atravessar a
fronteira sem código PIA; engoli-la faria o objeto entrar ou sair sem
que ninguém decidisse. A causa é preservada em `__cause__`.

Nos dois casos: `RetrievalContractViolationError` (`PIA-8034`), a
taxonomia **já existente** da E4.6. Nenhum código de erro novo foi
criado — `NEXT_FREE_ERROR_CODE = PIA-8041`, inalterado.

---

## 7. Compatibilidade

```text
DEFAULT = None
BEHAVIOUR WITH None = CHAIN 67, UNCHANGED
CALLER SIGNATURES = UNCHANGED
E4.8 = UNTOUCHED
```

Nenhum chamador atual passa o gate, e nenhum precisa. A E4.8 continua
chamando a E4.6 sem gate, e sua assinatura não o admite — há teste que
verifica essa ausência.

---

## 8. Riscos e limites declarados

**Bypass por chamada direta.** Quem chamar `retrieve()` sem gate obtém a
vista base. Isso é **correto** nesta etapa: a E4.6 é recuperação base, e
tornar o gate obrigatório aqui faria toda chamada existente depender de
um conceito que ainda não existe. Fechar o caminho canônico de
forgetting será obrigação de composição da E4.9, não deve ser resolvido
aqui por acoplamento prematuro.

**Custo por candidato.** O gate é consultado uma vez por candidato
admissível, dentro do laço. Um gate caro multiplica o custo da coleta —
troca conhecida, e responsabilidade de quem o fornece.

**O gate confia no que recebe.** Ele vê o `CognitiveObjectView` já
validado; não pode inspecionar a Search, o contexto ou a resolução. É
deliberado: dar-lhe mais contexto seria dar-lhe autoridade.

---

## 9. Fronteira com a E4.9

```text
THIS CORRECTIVE OFFERS COMPOSITION, NOT RETENTION
E4.6 IS NOT RETENTION-AWARE
THE EXISTENCE OF THIS POINT AUTHORIZES NO RETENTION DECISION
```

O protocolo é **neutro**: nem o nome, nem os membros, nem o código
executável mencionam retenção, expiração, esquecimento ou apagamento —
há teste por AST (sem docstrings) que verifica isso, e outro que verifica
que o manager não importa módulo algum de retenção ou erasure.

A futura E4.9 poderá construir um gate imutável por chamada, **depois**
de validar sua própria autoridade, e deverá torná-lo obrigatório no
caminho canônico de forgetting.

```text
NOT RETURNED IN THIS RESPONSE != FORGOTTEN
NOT RETURNED IN THIS RESPONSE != INACCESSIBLE
NOT RETURNED IN THIS RESPONSE != DELETED
NOT RETURNED IN THIS RESPONSE != NONEXISTENT
```

Um `False` não escreve nada. Na chamada seguinte, sem gate, o mesmo
objeto reaparece — provado contra PostgreSQL real, com espião de escritas
em zero e conferência do estado persistido.

---

## 10. Stop Conditions

```text
RETENTION_RETRIEVAL_COMPOSITION_GAP = CLOSED_CANDIDATE

ERASURE_TARGET_OWNERSHIP_GAP        = OPEN
LEGAL_ERASURE_CAUSAL_HISTORY_GAP    = OPEN_CONDITIONAL
ON_EXPIRY_ACTION_UNRESOLVED         = OPEN
DESTRUCTIVE_EXECUTION_AUTHORITY_GAP = OPEN

E4_9_IMPLEMENTATION = NOT_STARTED
E4_9_READY          = FALSE
```

`CLOSED_FINAL` não é declarado aqui: cabe à auditoria independente.
