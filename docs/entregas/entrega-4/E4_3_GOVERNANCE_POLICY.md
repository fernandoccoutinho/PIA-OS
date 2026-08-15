# E4_3_GOVERNANCE_POLICY

**Módulo:** E4.3 — Governance Policy
**Baseline:** E3 FROZEN · E4.0/E4.0.1/E4.1/E4.2/E4.2.1 · patch chain 40
**HEAD verificado:** `fa5f4c1e…` · **TREE:** `4b8d4c3b…`
**Patch:** `e4-3-governance-policy.patch` (41º)

---

## 1. Missão

```
MemoryContext + operação cognitiva + GovernancePolicy
                        ↓
                GovernanceDecision
```

```
GOVERNANCE MAY RESTRICT ACCESS
GOVERNANCE MUST NOT REWRITE EXISTENCE
```

---

## 2. PRE-IMPLEMENTATION PLAN

### 2.1 O que a E4.3 **não** é

| Pergunta | Quem responde |
|---|---|
| "Quem é este usuário?" | autenticação — **fora da E4** |
| "Pode chamar este endpoint?" | autorização de aplicação — **fora da E4** |
| "Esta operação cognitiva é admissível sob esta policy e contexto?" | **E4.3** |
| "Como aplicar transições de acessibilidade?" | E4.7 |
| "Quais objetos compõem a vista admissível?" | E4.6 |

Nada de login, JWT, OAuth2, RBAC, ACL, permissões SQL, RLS ou
autorização de Kernel/Runtime/Scheduler.

```
ACTOR PRESENCE != AUTHORIZATION
ACTOR_REF      != AUTHENTICATED IDENTITY
```

Uma policy pode **avaliar** o descritor `actor_ref`; a decisão jamais
afirma que a identidade foi autenticada. Isso está codificado no
próprio value object — ver §4.4.

### 2.2 A decisão mais delicada: a forma de `rules`

O freeze deixou a forma **deliberadamente aberta**, e a Stop Condition
12 da E4.0 nomeia o risco: *"escolher policy engine por conveniência
tecnológica"*. OPA/Rego, Cedar, DSL própria e JSON arbitrário estão
todos fora — não porque sejam ruins, mas porque escolher a ferramenta
antes de saber quais decisões precisam ser expressas é deixar a
ferramenta definir a semântica.

**Não foi preciso parar em Stop Condition**, e a razão é que as
decisões exigidas pelos testes mínimos são enumeráveis: dado um
contexto e uma operação, uma regra precisa dizer *a que ela se
aplica* e *o que resulta*. Isso é expressável com uma estrutura
tipada e fechada:

```
GovernanceRule (frozen dataclass)
    operations   frozenset[CognitiveOperation]   vazio = qualquer operação
    domain_ids   frozenset[UUID]                 vazio = qualquer domínio
    actor_refs   frozenset[str]                  vazio = qualquer ator
    purposes     frozenset[str]                  vazio = qualquer propósito
    effect       Effect.ADMIT | Effect.DENY
    rule_id      str    identificador estável, citado na decisão
```

Uma regra é **conjunção** das dimensões informadas; dimensão vazia
significa "não restringe por esta dimensão". Não há negação, nem
operadores aninhados, nem expressões — porque nada nos requisitos
pede isso, e cada construto acrescentado seria um motor sendo
inventado por antecipação.

Quando E4.6/E4.7/E4.9 mostrarem que falta expressividade, ela é
acrescentada com o caso de uso na mão. O caminho inverso — motor
genérico primeiro — não tem volta.

### 2.3 Vocabulário de operações

`CognitiveOperation` é **fechado**, como todo enum de domínio do
projeto (`AccessibilityState`, `CausalEventType`), e ampliá-lo exige
EDR:

```
READ           ler patrimônio
REFERENCE      referenciar sem transformar
DERIVE         derivar novo objeto
TRANSFORM      transformar
EXPOSE         expor para fora
SYNCHRONIZE    transmitir entre instâncias
CONSOLIDATE    consolidar múltiplas fontes
```

São exatamente as sete listadas no `E4_GOVERNANCE_BOUNDARIES.md` §9
como o que governança "pode futuramente controlar". Nenhuma é
inventada aqui, e nenhuma é **executada** aqui:

```
PERMISSION != OPERATION IMPLEMENTATION
```

Permitir `CONSOLIDATE` não cria consolidação — E4.5 ainda não existe.
A policy nomeia; não realiza.

### 2.4 Três resultados, não dois

```
ADMISSIBLE
INADMISSIBLE
NOT_APPLICABLE
```

O terceiro não é ornamento. Sem ele, "nenhuma regra se aplicou"
colapsaria em `False` e ficaria indistinguível de "uma regra negou
explicitamente" — exatamente o colapso diagnóstico que a E3.12
provou não cometer no `negative strong gate`.

E há uma consequência de segurança: `NOT_APPLICABLE` **não concede**.
Quem consome deve tratá-lo como não-admissão, mas sabendo que a causa
é ausência de regra, não proibição. `actor_ref` presente sem regra
aplicável dá `NOT_APPLICABLE`, nunca `ADMISSIBLE` — o teste 6 do §
"testes mínimos" existe exatamente para travar isso.

### 2.5 Precedência

```
DENY_OVERRIDES
```

Havendo qualquer regra aplicável com `DENY`, o resultado é
`INADMISSIBLE`, independentemente de quantas admitam. É a única
precedência defensável para um sistema cujo princípio operacional é
"governança pode restringir": uma restrição que some porque outra
regra permite não é restrição.

Determinismo: as regras são avaliadas em ordem canônica estável, e a
decisão cita **a** regra fundante — a primeira `DENY` aplicável, ou a
primeira `ADMIT` se nenhuma nega.

### 2.6 Identidade e versionamento

```
GovernancePolicy
    id           UUID       identidade de registro
    policy_key   str        identidade lógica estável entre versões
    version      int        >= 1, monotônico dentro do policy_key
    rules        tipadas    serializadas em JSON estruturado
    effective_from / effective_until   vigência, ambos opcionais

    UNIQUE(policy_key, version)
```

Uma versão publicada é **imutável**: mudança semântica cria versão
nova. Isso é o que permite responder "qual versão fundamentou aquela
decisão?" meses depois — e é o mesmo princípio de append-only que a
E3 aplica a `ProvenanceRecord` e `CausalHistoryEvent`, pela mesma
razão.

`UNIQUE(policy_key, version)` no banco é a autoridade final contra
sobrescrita e contra corrida entre duas sessões criando a mesma
versão.

### 2.7 O que **não** entra

- **`owner`/`policy_ref` dentro de `MemoryDomain`** — a policy
  referencia `domain_id`; o domínio não incorpora governança.
  `E4_1_SEMANTICS_UNCHANGED = TRUE`.
- **`GovernanceDecision` persistida** — é value object transitório,
  como `IntegrityFinding` (E3.10) e `SyncReport` (E3.11). Persistir
  decisões criaria a tentação de tratá-las como fato estabelecido em
  vez de resultado datado contra uma versão de policy.
- **Score de qualquer espécie.**
- **Metadados arbitrários.**

### 2.8 Fronteiras de sincronização

```
GOVERNANCE_POLICY_PORTABLE = FALSE
GOVERNANCE_POLICY_SYNC     = NONE
```

Congelado desde a E4.0: autoridade não é transferível, e uma policy
importada produziria objetos invisíveis no destino sem que ninguém
ali tenha decidido isso. O envelope da E3 continua com sete seções.

---

## 3. Implementação

```
app/memory/models/governance_enums.py       CognitiveOperation, GovernanceEffect,
                                            GovernanceOutcome  (StrEnum fechados)
app/memory/models/governance_policy.py      persistência + serialização canônica
app/memory/schemas/governance.py            GovernanceRule, GovernanceDecision
app/memory/repositories/governance_policy_repository.py
app/memory/services/governance_manager.py   publicação + avaliação read-only
alembic/versions/4ca61776b982_...           governance_policies
```

Nenhum arquivo da E3 tocado. Nenhum arquivo de modelo, repositório ou
migração da E4.1 tocado — `MemoryDomain` **não** ganhou `owner` nem
`policy_ref`, e isso é verificado por teste (`gi17`), não apenas
declarado.

### 3.1 Decisões de desenho registradas

**Domínios casam por interseção, não por igualdade.** Um contexto que
declara `{D1, D2}` casa com uma regra sobre `{D1}`. Exigir igualdade
tornaria as regras inúteis para qualquer contexto multi-domínio, e a
E4.2 congelou que contexto apenas *declara* o conjunto.

**Dimensão ausente no contexto não casa com regra que a restringe.**
Uma regra sobre `actor_refs={"ana"}` não se aplica a um contexto sem
`actor_ref`. O contrário faria ausência de informação valer como
informação — e ausência de ator é justamente o caso em que não se deve
concluir nada.

**`session_id` não participa da aplicabilidade.** Sessão não é
identidade nem autoridade (`CONTEXT != SESSION`, congelado na E4.2).
Dois contextos que diferem só na sessão decidem igual — testado.

**Vigência é `[from, until)`, com limite final exclusivo.** Com limite
inclusivo, duas versões contíguas se sobrepõem no instante da virada e
"qual valia?" passa a ter duas respostas.

**A policy referencia `domain_id` por valor, sem FK.** Governança não
é dona do domínio, e travar a evolução dele por causa de uma regra
seria incorporar governança onde ela não pertence. Uma regra pode
inclusive citar um domínio inexistente — governança informa; não
valida patrimônio alheio nem o fabrica.

### 3.2 Código morto removido

A exigência de 100% de cobertura revelou três coisas que eu havia
introduzido **por antecipação**, e as três foram removidas:

- `GovernancePolicyNotFoundError` e o código `PIA-8028` — nada os
  levantava, porque `get_version` devolve `None` e ausência não é
  exceção;
- `GovernancePolicyRepository.exists_policy` — nenhum chamador;
- três ramos `if x is None` inalcançáveis nos validadores.

É o mesmo mecanismo que já havia revelado código morto em E3.11.1,
E4.1 e E4.2.1. Próximo error code livre: **`PIA-8028`**.

## 4. Testes

| Grupo | Onde | Quantidade |
|---|---|---|
| vocabulário, regras, precedência, decisão | `tests/unit/memory/test_governance.py` | 33 |
| versionamento, vigência, concorrência, read-only | `tests/integration/memory/test_governance_integration.py` | 14 |

Correspondência com os 16 requisitos mínimos:

| # | Requisito | Teste |
|---|---|---|
| 1 | criação e recuperação | `gi1` |
| 2 | nova versão explícita | `gi2` |
| 3 | sem sobrescrita silenciosa | `gi3` (exceção **e** `INSERT` direto) |
| 4 | vigência determinística | `gi4`, `gi4b` |
| 5 | aplicabilidade por dimensões do contexto | `gi5` |
| 6 | ator sem regra não concede | `gi6`, `gv8` |
| 7 | três resultados distinguíveis | `gv7` |
| 8 | decisão com policy, versão e fundamento | `gv10` |
| 9 | mesma entrada, decisão equivalente | `gv11` |
| 10 | contextos diferentes decidem diferente | `gv12`, `gi5` |
| 11 | nada é alterado | `gi11` (censo de 10 tabelas + listener) |
| 12 | negativa não produz inexistência | `gi12`, `gv13` |
| 13 | policy fora do Sync | `gi13` |
| 14 | concorrência real | `gi14` |
| 15 | upgrade/downgrade seguros | `gi15` |
| 16 | regressão E3/E4.1/E4.2 | suíte completa |

Fronteiras verificadas por **ausência estrutural** (`gv16`, `gv17`):
o manager não expõe `authenticate`, `login`, `has_role`,
`check_permission`, `search`, `retrieve`, `rank`, `score`, `repair`,
`learn`, `transition`, `set_accessibility`, `add_membership`, nem
executor de nenhuma `CognitiveOperation`; e o código-fonte não
menciona `SearchEngine`, `SearchCriteria`, `AccessibilityState`,
`MemoryDomainMembership` ou `CognitiveObject`. Testar ausência é o
único modo honesto de provar uma fronteira — um teste de comportamento
passaria igual se a capacidade proibida existisse mas não fosse
chamada.

## 5. Resultados

```
FULL_SUITE = 1182 passed / 1 skipped / 0 failed   (total coletado 1183)

E3_REGRESSION_DELTA   = 0   (598/598)
E4_1_REGRESSION_DELTA = 0   (40/40)
E4_2_REGRESSION_DELTA = 0   (42/42)

GLOBAL_COVERAGE = 98,64%   APP_MEMORY = 100%   APP_COGNITIVE = 100%
RUFF = PASS   BLACK = PASS   MYPY_NEW_ERRORS = 0   git diff --check = limpo

MIGRATION_HEAD = 4ca61776b982   SCHEMA_ORM_DRIFT = 0
DATABASE_WRITES_DURING_EVALUATION = 0
GOVERNANCE_POLICY_PORTABLE = FALSE   GOVERNANCE_POLICY_SYNC = NONE
E3_FILES_MODIFIED = NONE   E4_1_SEMANTICS_UNCHANGED = TRUE

E4_3_IMPLEMENTATION = COMPLETE
E4_3_FINAL_STATUS   = AWAITING_INDEPENDENT_AUDIT
READY_FOR_E4_4      = FALSE
```

---

## Qualificação posterior — corretivo E4.3.3

Onde este documento afirma que `operations = frozenset()` significa "não
restringe por operação", leia-se: **não restringe dentro do escopo
histórico** `EMPTY_OPERATIONS_SCOPE_V1` — as sete operações que existiam
quando a E4.3 foi publicada.

```text
EMPTY OPERATIONS != ALL FUTURE OPERATIONS
FUTURE OPERATION DEFAULT = EXPLICIT OPT-IN REQUIRED
```

O corretivo E4.3.3 acrescentou `ACCESSIBILITY_TRANSITION` ao vocabulário
e fechou o envelope do curinga, para que policies publicadas não
adquirissem autoridade sobre capacidades criadas depois delas. Ver
`E4_3_3_EXPLICIT_ACCESSIBILITY_TRANSITION_AUTHORITY.md` e o EDR
correspondente.

Este registro **qualifica** a afirmação original; não a reescreve nem
finge que a semântica sempre foi outra.
