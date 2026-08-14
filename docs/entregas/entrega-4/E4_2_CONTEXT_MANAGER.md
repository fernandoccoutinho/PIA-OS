# E4_2_CONTEXT_MANAGER

**Módulo:** E4.2 — Context Manager
**Baseline:** E3 FROZEN · E4.0 / E4.0.1 / E4.1 PASS FINAL · patch chain 38
**Patch:** `e4-2-context-manager.patch` (39º)

---

## 1. Missão

Representar a **perspectiva operacional** sob a qual o patrimônio
cognitivo será, mais tarde, governado (E4.3), tornado acessível
(E4.7) e recuperado (E4.6).

```
CONTEXT CHANGES VIEW
CONTEXT DOES NOT REWRITE PATRIMONY
```

Contexto **não é** patrimônio cognitivo, **não cria** memória e
**não modifica** `CognitiveObject`.

---

## 2. Pre-implementation findings

### 2.1 `ContextDefinition` **não** foi congelado — logo, deferido

O §21 do prompt canônico manda inspecionar se a E4.0 realmente
congelou `ContextDefinition` como estado local, e deferir caso
contrário. A inspeção é conclusiva. `E4_PRIMITIVE_OWNERSHIP.md` §6
diz, literalmente:

> "A E4.0 **não congela**. Registra a análise. […] **Posição da E4.0:**
> provavelmente **ambos** […]"

"Provavelmente" não é contrato. `E4_DOMAIN_MODEL_DRAFT.md` também o
marca como "provável" na tabela de entidades candidatas, e o próprio
documento declara seus campos "ilustrativos".

```
CONTEXT_DEFINITION = DEFERRED
```

Implementá-lo agora seria criar primitiva persistente por antecipação
— exatamente o que a regra de admissão de `E4_PRIMITIVE_OWNERSHIP.md`
§1 proíbe. E há um argumento mais forte que a formalidade: uma
`ContextDefinition` sem nenhum consumidor (Governance não existe,
Retrieval não existe) seria uma configuração que ninguém lê. O
momento de decidi-la é quando houver quem a use.

### 2.2 `MemoryContext = TRANSIENT` **está** congelado

`E4_SYNC_BOUNDARY.md` §3.2, matriz F, classifica `MemoryContext` como
**TRANSIENT** — "instância de operação; não persiste". Isso é
contrato, não conjectura.

```
MIGRATION_REQUIRED = NO
TABLE_REQUIRED     = NO
MEMORY_CONTEXT_SYNC = NONE
```

Há evidência executável a favor: o teste arquitetural forte da E4.0
construiu contexto como objeto **puramente em memória** e provou
`Accessible(P,C1) != Accessible(P,C2)` sem nenhuma tabela nova.

### 2.3 A fronteira de import da E4.1 continua valendo

O gate `G17` da E3.12 proíbe `app.cognitive` em qualquer módulo sob
`backend/app/` fora do próprio pacote. `MemoryContext` referencia
domínios por `uuid.UUID` e nada mais — a restrição não custa nada
aqui, e o teste `MD6` (E4.1) já cobre o pacote inteiro, incluindo os
arquivos novos.

---

## 3. As 24 perguntas obrigatórias (§4)

**1. Context deve ser persistente ou transiente?**
**Transiente.** Congelado na matriz F da E4.0.

**2. O freeze distingue `MemoryContext` de `ContextDefinition`?**
Distingue **conceitualmente**, mas só congela o primeiro. O segundo
está marcado como "provável"/"não congela".

**3. Existe necessidade demonstrada de entidade persistida?**
**Não.** Nenhum consumidor existe ainda. Ver §2.1.

**4. Context precisa de UUID?**
**Não** como identidade persistente (§20). A igualdade estrutural do
`frozen dataclass` já resolve comparação e determinismo — inventar
UUID daria identidade a algo que é, por contrato, uma circunstância.

**5. Precisa sobreviver entre sessões?**
**Não.** Se um contexto precisa ser reutilizado, isso é
`ContextDefinition`, que está deferido.

**6. `session_id` pode participar sem definir identidade?**
**Sim** — atributo descritivo opcional. `session_id != context
identity`.

**7. `MemoryDomain` é obrigatório no contexto?**
**Não.**

**8. Context pode operar sem domain?**
**Sim.** Contexto vazio é válido (§28) — ausência de contextualização
não implica ausência de patrimônio.

**9. Context pode conter múltiplos domains?**
**Sim**, e apenas **declara** o conjunto. Nenhuma união ou interseção
de patrimônio é executada aqui (§29).

**10. Actor pertence ao contrato agora?**
**Sim, como entrada descritiva.** `ACTOR PRESENCE != AUTHORIZATION`.
Governança é E4.3, e este módulo não expõe nenhuma API de decisão.

**11. `purpose` precisa ser string livre?**
**Sim**, e é o mínimo defensável: qualquer vocabulário fechado agora
seria inventado sem evidência de uso.

**12. `task` pertence ao contexto?**
**Deferido.** Aparece na lista ilustrativa do §7 da E4.0, mas nenhum
teste ou consumidor o exige. Sem necessidade demonstrada, fora.

**13. `scope` precisa de enum?**
**Deferido**, pelo mesmo motivo — e o §13 é explícito: não inventar
modelo de escopo nem enum universal sem necessidade.

**14. Context deve conter `AccessibilityState`?**
**Não.** Seria confundir perspectiva com estado do objeto, e
antecipar E4.7.

**15. Context pode modificar `AccessibilityState`?**
**Não.** Testado (CT16, COUT3).

**16. Context pode criar membership?**
**Não.** `domain in context != object added to domain`. Testado
(CT15).

**17. Context pode alterar persistence?**
**Não.** E4.4.

**18. Context pode alterar relevance?**
**Não**, e nenhum score é criado. E4.6+.

**19. Context deve ser sincronizado?**
**Não.** `MEMORY_CONTEXT_SYNC = NONE`.

**20. `ContextDefinition`, se persistente, é local ou portable?**
**LOCAL** pela matriz F — mas está deferido, então a questão não se
materializa nesta entrega.

**21. Context precisa de provenance?**
**Não.** Perspectiva não tem origem cognitiva; criar
`ProvenanceRecord` para uma vista falsificaria a proveniência do
patrimônio com um fato que não ocorreu.

**22. Context precisa de `CausalHistory`?**
**Não.** Olhar para algo não é um evento causal sobre esse algo.

**23. Algum campo exigiria metadata arbitrário?**
**Não.** `ARBITRARY_METADATA_DICT = NOT_AUTHORIZED` desde E3.6.2.

**24. Alguma decisão exigiria antecipar Governance?**
**Não.** `actor_ref` e `purpose` são descritivos; nenhuma API de
`allow`/`deny` existe. Testado por ausência estrutural (CT18).

---

## 4. Contrato congelado

### 4.1 `MemoryContext` — value object imutável

```
MemoryContext                      frozen dataclass, NÃO persistido
    domain_ids   tuple[UUID, ...]  canonicalizado (ordenado, sem repetição)
    session_id   str | None        descritivo, opcional
    actor_ref    str | None        descritivo, opcional — NÃO autoriza
    purpose      str | None        descritivo, opcional — NÃO ranqueia
```

**Campos deliberadamente ausentes:** `task_ref` e `scope` (deferidos —
sem necessidade demonstrada), `context_id` persistente (§20),
`accessibility`, qualquer `*_score`, `metadata`/`arbitrary_json`,
qualquer campo específico de provider (`openai_context`,
`anthropic_session`, `model_context_window`).

### 4.2 Imutabilidade e determinismo

`frozen=True` dá igualdade e hash estruturais de graça — que é
exatamente a comparação estrutural pedida pelo §26, sem inventar
identidade.

Determinismo (§27): `domain_ids` é **canonicalizado na construção** —
ordenado e desduplicado. Portanto:

```
context(domains=[D2, D1]) == context(domains=[D1, D2])
context(domains=[D1, D1]) == context(domains=[D1])
```

A ordem em que alguém digita domínios não é informação semântica, e
tratá-la como se fosse tornaria dois contextos idênticos
artificialmente distintos.

### 4.3 Variantes explícitas

`derive()` devolve **um novo** `MemoryContext`; o original nunca é
mutado. Se a perspectiva muda, ela é outra perspectiva —
`C1 → C2`, nunca "mutar C1 em silêncio". Isso é o que torna
reprodutível qualquer decisão futura tomada sob um contexto.

---

## 5. Camadas

```
app/memory/schemas/memory_context.py    ← value object puro, sem I/O
app/memory/services/context_manager.py  ← construção + validação de refs
```

`MemoryContext` é construtível **sem banco**: é um objeto de valor.
O `ContextManager` acrescenta a única coisa que exige leitura — a
validação de que os domínios referenciados existem — e **não escreve
nada**.

```
CONTEXT DESCRIBES
GOVERNANCE DECIDES ADMISSIBILITY
```

O `ContextManager` **não** expõe: `allow`, `deny`, `can`, `authorize`,
`permit`, `filter`, `search`, `retrieve`, `rank`. A ausência é
verificada por teste (CT18, CT20), não apenas afirmada.

---

## 6. Error model

| Código | Nome | Quando |
|---|---|---|
| `PIA-8026` | `CONTEXT_UNKNOWN_DOMAIN_REFERENCE` | contexto referencia domínio(s) inexistente(s) |

Um código novo, e a justificativa importa: já existe
`PIA-8023 MEMORY_DOMAIN_NOT_FOUND` (E4.1), e a tentação seria
reutilizá-lo. A informação diagnóstica é **de outra forma** — um
contexto pode referenciar vários domínios, e reportar um por vez
forçaria N tentativas para descobrir N referências ruins. A exceção
de E4.2 carrega o **conjunto** de ids desconhecidos.

Distinção preservada (§35):

```
DOMAIN NOT FOUND != COGNITIVE OBJECT NOT FOUND
```

Campos ausentes (`session_id`, `actor_ref`, `purpose` em `None`) são
situações **válidas** e não geram erro. Strings presentes porém em
branco são erro de precondição do chamador → `ValueError`, mesma
convenção de `CoidManager.generate_unique` (E3.2) e do `trace_id` em
branco do `IndexManager` (E3.7).

---

## 7. Zero escritas

```
MIGRATION_REQUIRED   = NO
DATABASE_WRITES      = 0
NEW_CONCURRENCY_INVARIANT = NONE
```

A construção de contexto é pura; a validação de domínios é leitura.
Provado por censo completo mais listener em `before_cursor_execute`
contando `INSERT/UPDATE/DELETE/TRUNCATE` — a mesma técnica de `SX3`
(E3.8) e `IA2` (E3.10).

Nenhum teste de concorrência foi escrito: sem estado novo e sem
escrita, não há invariante concorrente a proteger, e inventar um não
provaria nada (mesma decisão registrada em E3.7).

---

## 8. Testes

| Grupo | Onde | Quantidade |
|---|---|---|
| CT1–CT7, CT10–CT12, CT18–CT24 | `tests/unit/memory/test_context_manager.py` | 19 |
| CT8, CT9, CT13–CT17, COUT1–COUT5, DB1 | `tests/integration/memory/test_context_manager_integration.py` | 11 |

### 8.1 O gate central — `COUT1`

Dois contextos distintos construídos e validados sobre o **mesmo**
patrimônio fixo, com censo linha a linha das sete tabelas cognitivas
**e** das duas de memória:

```
c1 != c2                       ← ΔContext != 0
censo_depois == censo_antes    ← ΔPatrimony = 0
```

### 8.2 `DB1` — read-only provado, não afirmado

Listener em `before_cursor_execute` contando
`INSERT/UPDATE/DELETE/TRUNCATE` durante `build`, `build_validated`,
`validate`, `derive` e `equivalent`:

```
CONTEXT_DOMAIN_WRITE_COUNT = 0
```

Mais censo idêntico das nove tabelas. A prova é o SQL efetivamente
emitido, não a intenção do código — mesma técnica de `SX3` (E3.8) e
`IA2` (E3.10).

### 8.3 Fronteiras verificadas por ausência estrutural

`CT18`, `CT19`, `CT20` e `CT23` não testam comportamento: testam que
certas capacidades **não existem**. `ContextManager` e `MemoryContext`
são inspecionados por `inspect.getmembers` e o código-fonte é lido
para garantir que não há `allow`/`deny`/`authorize`, nenhum `*_score`
ou `rank`, nenhum `SearchEngine`/`SearchCriteria`, e nenhuma
referência a `MemoryDomainMembership`.

Testar ausência é o único modo honesto de provar uma fronteira: um
teste de comportamento passaria igual se a capacidade proibida
existisse mas não fosse chamada naquele caminho.

### 8.4 Demais gates

- **`CT9`** — referência desconhecida reporta o **conjunto** de ids, e
  a distinção `missing domain != cognitive patrimony missing` é
  verificada contando os objetos, que continuam lá.
- **`CT16`** — contextos construídos sobre domínios que contêm objetos
  `ACTIVE`, `INACCESSIBLE` e `CAUSALLY_EXTINCT`: nenhum estado se
  move.
- **`CT17`** — nenhum `ProvenanceRecord` e nenhum `CausalHistoryEvent`
  é criado. Olhar para algo não é um fato sobre esse algo.
- **`COUT3`** — Broken Glass: `CAUSALLY_EXTINCT` continua extinto sob
  qualquer perspectiva, inclusive a que declara o domínio do objeto.
- **`COUT5`** — nenhuma tabela `memory_contexts` ou
  `context_definitions` existe, e o envelope da E3 segue com sete
  seções.
- **`CT24`** — validar sem repositório levanta erro em vez de "passar"
  silenciosamente. O pior desfecho possível seria devolver *válido*
  por não ter como checar.

---

## 9. Resultados

```
TESTS
    unit memory            = 48   (29 de E4.1 + 19 de E4.2)
    integration memory     = 22   (11 de E4.1 + 11 de E4.2)
    unit cognitive         = 493  (inalterado)
    integration cognitive  = 105  (inalterado)
    TOTAL COLLECTED        = 1124

FULL_SUITE              = 1123 passed / 1 skipped / 0 failed
E3_REGRESSION_DELTA     = 0    (598/598 cognitivos verdes)
E4_1_REGRESSION_DELTA   = 0    (40/40 verdes)

GLOBAL_COVERAGE         = 98,55%
APP_MEMORY_COVERAGE     = 100%
APP_COGNITIVE_COVERAGE  = 100%

RUFF = PASS   BLACK = PASS
MYPY_TOTAL_ERRORS = 7   MYPY_NEW_ERRORS = 0   (nenhum em app/memory/)

MIGRATION_REQUIRED = NO      DATABASE_WRITES = 0
TABLE_REQUIRED     = NO      NEW_CONCURRENCY_INVARIANT = NONE

E3_FILES_MODIFIED   = NONE
E4_1_FILES_MODIFIED = codes.py e exceptions.py (adição pura: PIA-8026)
```

---

## 10. Deferido por este módulo

```
CONTEXT_DEFINITION   = DEFERRED   ← não congelado pela E4.0; sem consumidor
CONTEXT_TASK_FIELD   = DEFERRED   ← sem necessidade demonstrada
CONTEXT_SCOPE_FIELD  = DEFERRED   ← §13 proíbe inventar modelo de escopo
MEMORY_CONTEXT_SYNC  = NONE       ← TRANSIENT por contrato
CONTEXT_PERSISTENCE  = NONE
CONTEXT_CACHE        = NOT_AUTHORIZED
```

Próximo error code livre: **`PIA-8027`**.
