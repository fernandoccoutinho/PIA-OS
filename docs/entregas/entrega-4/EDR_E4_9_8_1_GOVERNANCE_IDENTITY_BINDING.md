# EDR E4.9.8.1 — Binding entre governança, identidade e alvo

**Natureza:** corretivo dos onze achados de binding da auditoria independente
da E4.9.8.
**Baseline:** cadeia 85 (`74a388eb`), `E4_9_8 = BLOCKED_BY_BINDING_DEFECTS`.

```text
GOVERNANCE_RESOLUTION_PRESENT != GOVERNANCE_AUTHORITY_FOR_THIS_ACTION
HUMAN_CONFIRMATION CANNOT CREATE MISSING AUTHORITY
GOVERNANCE_DENIAL CANNOT BECOME HUMAN APPROVAL
INADMISSIBLE != APPROVABLE      NOT_APPLICABLE DOES NOT GRANT
STRING_EQUALITY != AUTHENTICATION
ANNOTATION != ENFORCED_TYPE
```

```text
A7..A17 = FIXED (11/11)
PRODUCTION_SEMANTICS = TYPE_ERROR_STRICT
AUDIT_SCRIPT_DEFECT = CLOSED
DUPLICATE_TEST_KEY_DEFECT = CLOSED_CANDIDATE
CONFIDENTIALITY_PROBES = FULLY_BOUND
STATIC_GUARD_FALSE_POSITIVE = CLOSED_CANDIDATE
GOVERNANCE_FIXTURES = DOMAIN_COHERENT
EXECUTION_AUTHORIZED_CHECK = INDEPENDENTLY_PROVED
MIGRATION_DELTA = 0   E3_DELTA = 0   E4_3_DELTA = 0   E4_9_7_DELTA = 0
E4_9_9 = NOT_STARTED
```

---

## 1. Por que "objeto exato" não era "resolução exata da pergunta"

O §5 do EDR da cadeia 85 traz uma **matriz de binding** afirmando que ação,
policy, identidade, tenant, domínio e finalidade estavam vinculados. O runtime
verificava:

```python
if not isinstance(self.governance_resolution, GovernanceResolution):
    raise TypeError(...)
```

E nada mais.

Escrevi no mesmo documento "objeto exato, sem reavaliação" — e li a segunda
metade como dispensa de verificar a primeira. **Incorporar o objeto exato não é
ter a resolução exata daquela pergunta.** Não reavaliar significa não recalcular
a decisão de governança; nunca significou não conferir se ela responde à ação,
ao domínio, à finalidade e ao principal em questão.

O agravante: `execution_authorized` **já existia** em `GovernanceResolution`
desde a E4.3. Eu não precisava de nada novo para fechar A7/A8 — simplesmente
não chequei.

Esta é a oitava vez nesta linha de trabalho em que uma alegação minha é mais
forte que a prova. Registro sem atenuação, e registro também que a contramedida
desta rodada é diferente: as guardas `s20` e `s21` verificam na AST que cada
verificação **está no construtor**, com `s99_6` provando que a guarda detecta a
remoção. Uma matriz no EDR não protege nada; uma guarda que cai, sim.

### 1.1 Nota aditiva ao EDR da cadeia 85

O documento histórico **não** é reescrito. Fica registrado aqui que a matriz do
§5 daquele EDR descrevia o binding pretendido, não o implementado. A partir da
cadeia 86 ela passa a ser verdadeira, e as guardas acima são o que a sustenta.

---

## 2. Baseline e as onze reproduções

```text
HEAD 74a388eb53d976ae34ca0557a66d14e8e39715ee
PARENT 187f40d9…  TREE 16088d51…  PATCH_ID e60960fd…  PATCH_CHAIN 85
MIGRATION_HEAD c8a3f5017e94   árvore limpa   86 commits
app/cognitive be407b46…   backend/alembic cc68c3e2…
```

| # | Reprodução na cadeia 85 | Correção | Regressão |
|---|---|---|---|
| A7 | `INADMISSIBLE` forma envelope | `outcome is ADMISSIBLE` | `u64`, `u65`, `u66` |
| A8 | `NOT_APPLICABLE` idem | idem | `u64`, `u65`, `u66` |
| — | **`PROHIBITED`** (nominal, exigido) | idem | `u64`, `u65`, `u66` |
| A9 | `READ` aprova apagamento | `OPERACAO_DE_GOVERNANCA` | `u68`, `u69`, `u70` |
| A10 | domínio divergente | `context_domain_ids == (domain_id,)` | `u71` |
| A11 | finalidade divergente | `context_purpose == purpose_ref` | `u72` |
| A12 | ator ≠ identidade | `context_actor_ref == principal_ref` | `u73` |
| A13 | auth depois da confirmação | `materialized ≤ auth ≤ confirmed` | `u78`, `u79`, `u80` |
| A14 | blocker duplicado | recusa, sem dedup | `u82`, `u83`, `u84` |
| A15 | `satisfies("...")` → `True` | `TypeError` estrito | `u85`, `u87` |
| A16 | `permite_proposta("text")` → `True` | `TypeError` estrito | `u86`, `u87` |
| A17 | principal ≠ controle do alvo | igualdade por alvo | `u75`, `u76` |

---

## 3. Matriz operação destrutiva ↔ `CognitiveOperation`

```text
MOVE_TO_TRASH      -> RETENTION_DISPOSITION
PERMANENT_ERASURE  -> LEGAL_ERASURE
```

Fonte **única** (`OPERACAO_DE_GOVERNANCA`), correspondência **positiva**, sem
fallback. `s19` prova na AST que existe uma só definição e que cada membro de
`CognitiveOperation` aparece uma única vez no módulo — escrever a
correspondência em linha no `__post_init__` criaria duas verdades sobre qual
pergunta a governança precisa ter respondido.

`u68` exige `set(OPERACAO_DE_GOVERNANCA) == set(DestructiveOperation)`: um
membro novo em qualquer dos dois enums sem entrada aqui derruba o contrato
antes de virar autorização implícita.

`u69` e `u70` recusam nominalmente `READ`, `RETENTION_ASSESSMENT`,
`ACCESSIBILITY_TRANSITION` e a **troca cruzada** entre as duas operações
válidas — que é o caso mais perigoso, porque parece plausível.

---

## 4. Matriz de binding

### 4.1 Na proposta — a pergunta feita à governança

| Dimensão | Regra | Recusa |
|---|---|---|
| outcome | `is GovernanceOutcome.ADMISSIBLE` | `INADMISSIBLE`, `NOT_APPLICABLE`, `PROHIBITED` |
| autorização | `execution_authorized is True` | condição **independente** — §6 |
| operação | `OPERACAO_DE_GOVERNANCA[operation]` | qualquer outra |
| domínio | `context_domain_ids == (context.domain_id,)` | vazio, outro, subconjunto, superconjunto, ordem |
| finalidade | `context_purpose == context.purpose_ref` | outra, espaço, caixa, `None` |
| blockers | sem repetição | duplicata, sem dedup e sem reordenar |

Estas vivem na proposta porque são propriedades da **pergunta**: existem antes
de qualquer identidade.

### 4.2 No envelope — quem confirma e quando

| Dimensão | Regra | Recusa |
|---|---|---|
| ator avaliado | `resolution.context_actor_ref == identity.principal_ref` | divergência, `None` |
| controle do alvo | cada `target.control_scope.control_principal_ref == identity.principal_ref` | qualquer alvo do lote, com índice |
| frescor | `materialized_at <= authenticated_at <= confirmed_at` | anterior à proposta, posterior à confirmação |

Estas dependem de `IdentityEvidence`, que só o envelope tem.

### 4.3 Sem normalização

Nenhuma comparação aplica `strip`, `casefold`, normalização Unicode ou
aproximação. `u72` prova que `"purpose:remocao-titular "` com espaço final e
`"Purpose:..."` com maiúscula são finalidades **diferentes**. Divergência
preservada, como em toda a linha E4.9.

---

## 5. Por que igualdade não promove `actor_ref` a autenticação

```text
STRING_EQUALITY != AUTHENTICATION
```

`context_actor_ref` continua sem autenticar ninguém, e `control_principal_ref`
continua sendo referência descritiva. A igualdade **não** afirma que alguém foi
autenticado.

O que ela afirma é estreito e verificável: governança, evidência externa e alvo
descrevem **o mesmo principal**, e não pessoas diferentes. Sem ela, uma
resolução avaliada para A poderia fundamentar uma confirmação declarada por B
sobre um alvo controlado por C — três pessoas distintas num único envelope.

A verificação da evidência externa segue `EXTERNAL_BOUNDARY_LEVEL` e
`DEFERRED`. `u74` prova que nada no envelope alega verificação realizada: não há
`authenticate`, `verify`, `is_authenticated` nem `prove`.

---

## 6. `execution_authorized` como condição independente

Hoje a propriedade da E4.3 é derivada do outcome, então `ADMISSIBLE` com
`execution_authorized = False` é **impossível** pela construção normal.

Verifiquei as duas condições mesmo assim, e `u67` prova a segunda com um
**dublê controlado** — subclasse que sobrescreve a propriedade. Sem o dublê, a
segunda condição estaria coberta por coincidência com a primeira e ninguém
saberia se ela é verificada. Se a E4.3 passar a derivar a propriedade de outra
coisa, a prova continua valendo.

O dublê vive só no teste. Nenhum caminho de produção o constrói.

---

## 7. Frescor mínimo da identidade

```text
AUTHENTICATION_AFTER_CONFIRMATION != PRESENT_AUTHENTICATED_USER
OLD_OR_FUTURE_ASSERTION != FRESH STEP_UP
```

```text
materialized_at <= authenticated_at <= confirmed_at
```

Autenticação **anterior à proposta** é sessão antiga, não step-up vinculado a
esta ação. **Posterior à confirmação** é causalmente impossível como fundamento
dela.

Os dois extremos são inclusive (`u80`), e **nenhuma duração canônica foi
inventada**. A ordem anterior — `materialized ≤ issued ≤ confirmed < expires` —
foi preservada (`u81`). Nenhum `datetime.now()`: `s24` prova.

---

## 8. Limite: delegação não modelada

```text
DELEGATION = NOT_MODELED
```

A regra de principal representa **exclusivamente** o caso direto: quem confirma
é quem controla. Papel, grupo, procuração, ACL, admin override e atuação em
nome de terceiro não existem, e inventá-los seria criar autoridade
organizacional sem contrato.

`u77` prova por reflexão que nenhum contrato tem campo desse tipo; `s22` prova
por **identificador na AST** que nenhum aparece no módulo.

Consequência prática, declarada: enquanto isto valer, um lote com alvos de
controladores diferentes **não forma envelope**, ainda que o usuário tenha
poder real sobre todos. Quando houver modelo de delegação, isto muda por EDR
próprio — não por relaxamento silencioso.

---

## 9. Helpers públicos estritos

```text
ANNOTATION != ENFORCED_TYPE
STRING_EQUIVALENT != ENUM_MEMBER
```

`AssuranceLevel.satisfies` e `VoiceReviewState.permite_proposta` confiavam só
na anotação. A comparação `is` contra o membro falhava em silêncio e caía no
ramo permissivo: `satisfies("permanent_erasure")` devolvia `True` em
`AUTHENTICATED`.

Não havia exploit pelo caminho interno — os construtores sempre passam membros
reais —, mas o contrato **público** era mais permissivo que o EDR, e um helper
que aceita string equivalente é uma porta que ninguém vigia.

Ambos passaram a levantar `TypeError` controlado. `s23` exige o `isinstance`
explícito na AST; `s99_7` prova que a guarda distingue anotação sozinha de
verificação real. `u87` confirma que a semântica positiva não mudou.

---

## 10. Contradição do prompt e substituição do instrumento

O §4.8 exigia `TypeError`; o §8 exigia o reprodutor sem traceback. O script
original avaliava A15/A16 **fora** de `try/except`, então a implementação
correta quebrava o instrumento.

Parei e relatei em vez de escolher. A alternativa — devolver `False` para
não-membro — teria feito a medição passar e escondido uma entrada de tipo
inválido como resposta normal do predicado.

A autoridade confirmou o defeito no instrumento e autorizou a substituição
exclusiva do reprodutor:

```text
sha256 original = 856ada70edb07deef479613139e66fbe713d703e5db64925736547e05014e487
sha256 v2       = e0b20254e9cf6e07f5d2ac3b741350d241c41bc5cafeebff2444d09c2b9e2fdb
sha256 pacote   = 091acb88f897dd9a372b708d9eb91512361b3e129cfcc686f78679be75096bc9
```

Procedência conferida antes de usar: o `_original.py` do pacote de correção é
byte a byte o script recebido na tarefa. O diff toca **apenas** A15/A16,
acrescentando `accepts_non_member`, que trata `TypeError` como fechamento e
**retorno normal, inclusive `False`, como defeito ainda reproduzido**.

Isso é mais forte que a versão original: o instrumento passou a distinguir
recusa de tipo de resposta negativa, que era exatamente a distinção que o §4.8
protegia.

Os quatro scripts da E4.9.7 permanecem byte a byte.

---

## 11. Dois defeitos de teste fechados nesta cadeia

### 11.1 Chave duplicada no inventário de canais

`_objetos_com_marcador` tinha `"Envelope→identity.principal_ref"` **duas vezes**
no mesmo literal de `dict`. Python sobrescreve em silêncio: um canal deixava de
ser medido sem aviso.

`u50_1` conta as chaves do literal na AST e compara com o dicionário resultante.
Chave repetida derruba o teste.

### 11.2 Falso positivo de substring em `s22`

Escrevi a guarda de delegação procurando `"role"` e `"acl"` no texto. Ela
acusou **cont*role*** e **dat*acl*ass**.

É a **nona** vez que esta forma aparece no projeto — `gv16` (E4.3.1),
`s02`/`s11` (E4.9.6), `s15` (E4.9.6.1), `u76` (E4.9.6.3), `s04` (E4.9.7.2) — e
eu a reproduzi no primeiro impulso, com a lição registrada.

A lição corrigida não é "use AST". É:

```text
SUBSTRING É SEMPRE A FERRAMENTA ERRADA QUANDO O ALVO É UM CONCEITO,
E NÃO UM LITERAL
```

`s22` passou a buscar **identificadores** (`Name`, `Attribute`, `FunctionDef`,
`arg`), que é onde delegação apareceria de fato. `s99_8` prova a distinção:
`controle`/`dataclass` não acusam, `role_id` acusa.

---

## 12. Fixtures de governança coerentes com o domínio

Descoberta durante os testes: a `GovernanceResolution` da E4.3 impõe coerência
interna que a fábrica da cadeia 85 não respeitava.

```text
NOT_APPLICABLE  não cita regra local — se nenhuma se aplicou, não há o que citar
PROHIBITED      exige capacidade bloqueada — recusa que não diz o que bloqueou
                é irrecorrível
ADMISSIBLE      exige proveniência local completa
```

Reutilizar a proveniência de `ADMISSIBLE` para os outros outcomes produziria
**testes de estados impossíveis** — objetos que a E4.3 nunca emitiria. A fábrica
passou a montar cada outcome com seus próprios invariantes, e `u65` exercita
objetos que a E4.3 realmente produziria.

```text
GOVERNANCE_FIXTURES = DOMAIN_COHERENT
```

---

## 13. Sondas de confidencialidade totalmente vinculadas

Depois do binding, é **impossível variar um canal isolado**: pôr o marcador em
`control_principal_ref` obriga identidade e ator avaliado a serem o mesmo
principal, senão a proposta nem se forma.

```text
CONFIDENTIALITY_PROBES = FULLY_BOUND
```

Duas consequências, ambas boas: as sondas constroem objetos integralmente
coerentes, mais fiéis ao uso real; e uma sonda mal montada **falha na
construção** em vez de passar sem medir. Aconteceu quatro vezes até eu acertar —
e é assim que deve ser.

---

## 14. Garantia por camada

| Garantia | Camada |
|---|---|
| outcome admissível + `execution_authorized` | `APPLICATION_LEVEL` |
| operação ↔ `CognitiveOperation` | `APPLICATION_LEVEL` |
| domínio, finalidade | `APPLICATION_LEVEL` |
| ator avaliado ↔ identidade | `APPLICATION_LEVEL` |
| principal ↔ controle do alvo | `APPLICATION_LEVEL`, **caso direto apenas** |
| delegação | `NOT_MODELED` |
| frescor de `authenticated_at` | `APPLICATION_LEVEL`, instantes recebidos |
| blockers sem duplicata | `APPLICATION_LEVEL` |
| tipo estrito nos helpers | `TYPE_LEVEL` + `APPLICATION_LEVEL` |
| step-up efetivamente verificado | `EXTERNAL_BOUNDARY_LEVEL` — representado |
| autenticação, IdP, sessão | `DEFERRED` |
| persistência, consumo, revogação, replay, TOCTOU | `DEFERRED` |
| `GovernanceResolution` livre de segredo na fonte | `DEFERRED` — fora do escopo |

Nenhuma garantia descrita acima da camada que a sustenta.

---

## 15. Assinaturas, defaults e confidencialidade

**Nenhuma assinatura pública mudou.** As correções são invariantes de
`__post_init__` e endurecimento de tipo nos dois helpers — cujas anotações
passaram de `DestructiveOperation`/`InputChannel` para `object`, o que **amplia**
o tipo aceito estaticamente e o restringe em runtime. Nenhum campo novo, nenhum
default novo.

`s15` continua congelando os sete contratos da E4.9.7; `u44` continua
congelando os defaults dos sete da E4.9.8.

Campos textuais livres inalterados — `version_etag`, `principal_ref`,
`purpose_ref` —, todos redigidos direta e composicionalmente, agora exercitados
com marcador em objetos totalmente coerentes (§13). Os onze textos livres de
`GovernanceResolution` seguem redigidos na composição.

---

## 16. Conformidade documental — quatro camadas (Master v2.3)

### 16.1 `PIA_OS_SOPHIA_MASTER_COMPATIBILITY` — 20 linhas

```text
 1 USER_AUTHORITY_PRESERVED ............... REFORÇADO. É o achado: confirmação
     humana não cria autoridade ausente; governança negada não vira aprovação.
 2 SOPHIA_BRAND_PIA_OS_CODEBASE_PRESERVED . SIM. Nenhum identificador de marca.
 3 MODULE_SCOPE_AND_DEFERRED_CAPABILITIES . Implementado: os oito bindings.
     Diferidos: auth, step-up, persistência, consumo, revogação, replay,
     TOCTOU, re-resolução, delegação, executor, efeito, recibo.
 4 SCHEDULE_MODE_DECLARED ................. NOT_APPLICABLE — sem Schedule.
 5 AI_ROLE_AND_STEP_INSTRUCTION_DISTINGUISHED NOT_APPLICABLE — sem multi-IA.
 6 PROVIDER_CONNECTION_METHOD_DECLARED .... NOT_APPLICABLE — nenhum conector;
     AssuranceLevel segue neutro de provedor.
 7 AUTOMATION_SCOPE_DECLARED .............. NENHUMA (s24, s12).
 8 APPROVAL_GATES_DECLARED ................ REFORÇADO — §4.
 9 PERSISTENCE_BEHAVIOR_DECLARED .......... NENHUMA. Recusar mais cedo não
     cria estado.
10 MULTI_AI_RESULT_ATTRIBUTION_DECLARED ... NOT_APPLICABLE.
11 DIVERGENCE_PRESERVATION_DECLARED ....... SIM — igualdade estrita, sem
     normalização (§4.3, u72).
12 CONCURRENT_WORK_ISOLATION_DECLARED ..... REFORÇADO — domínio e principal
     de controle acrescentados a tenant e workspace.
13 BACKGROUND_EXECUTION_AUTHORIZATION ..... NOT_APPLICABLE.
14 RESOURCE_LIMITS_QUEUE_AND_COST_DECLARED  NOT_APPLICABLE.
15 REMOTE_RESOURCE_SCOPE_DECLARED ......... NENHUM acesso remoto.
16 OBSERVATION_PREPARATION_EXECUTION ...... Esta fatia é PREPARAÇÃO; nada
     mudou de estágio.
17 CREDENTIAL_AND_SECRET_BOUNDARY_DECLARED  SIM — nenhum campo novo; as
     comparações usam referências opacas já existentes.
18 FAILURE_ROLLBACK_AND_CONCURRENCY ....... Sem escrita, nada a reverter;
     recusa no construtor não deixa objeto parcial.
19 CURRENT_CAPABILITY_NOT_OVERSTATED ...... §1, §5, §8 e §14.
20 FROZEN_MODULES_UNCHANGED ............... cognitive, alembic, E4.3 e os sete
     contratos da E4.9.7 intocados.
```

### 16.2 `SOPHIA_UX_COMPATIBILITY` — 17 linhas

```text
 1 USER_AUTHORITY_PRESERVED ............... REFORÇADO.
 2 SCHEDULE_MODE_DECLARED ................. NOT_APPLICABLE.
 3 AUTOMATION_SCOPE_DECLARED .............. NENHUMA.
 4 PERSISTENCE_BEHAVIOR_DECLARED .......... NENHUMA.
 5 PROVIDER_NEUTRALITY_PRESERVED .......... SIM — nenhum provedor congelado.
 6 PERSONALIZATION_REVERSIBLE ............. NOT_APPLICABLE.
 7 CONCURRENT_WORK_ISOLATION_DECLARED ..... REFORÇADO.
 8 BACKGROUND_EXECUTION_AUTHORIZATION ..... NOT_APPLICABLE.
 9 RESOURCE_LIMITS_AND_QUEUE_DECLARED ..... NOT_APPLICABLE.
10 AI_ROLE_CONTROL_DECLARED ............... NOT_APPLICABLE — nenhuma IA
     participa da aprovação destrutiva.
11 ROLE_AND_STEP_INSTRUCTION_DISTINGUISHED  NOT_APPLICABLE.
12 PIA_SEQUENCE_SUGGESTION_BEHAVIOR ....... NOT_APPLICABLE — nada sugere.
13 MULTI_AI_RESULT_ATTRIBUTION_DECLARED ... NOT_APPLICABLE.
14 PIA_INTEGRATION_DIVERGENCE_PRESERVATION  NOT_APPLICABLE — sem síntese.
15 POST_RESULT_USER_COMMAND_DECLARED ...... SIM — a confirmação é comando do
     usuário, e agora só é registrada se a governança respondeu àquela ação.
16 RESULT_APPROVAL_AND_PERSISTENCE ........ Distinguidos; APPROVABLE !=
     APPROVED preservado.
17 FROZEN_MODULES_UNCHANGED ............... SIM.
```

### 16.3 `MULTICHANNEL_COMMAND_COMPATIBILITY_v1_3` — 10 marcadores

```text
 1 INPUT_CHANNELS_DECLARED ................ TEXT | VOICE, proveniência.
 2 COMMAND_ENVELOPE_DECLARED .............. Endurecido; sem parser/ASR (s05).
 3 CHANNEL_NORMALIZATION_DECLARED ......... NOT_APPLICABLE — e nenhuma
     normalização de string foi introduzida.
 4 IDENTITY_CONTEXT_AND_SCOPE_DECLARED .... PARCIAL, declarado: governança,
     identidade e alvo têm de descrever o mesmo principal; isso não autentica.
 5 VOICE_CONFIDENCE_AND_CORRECTION ........ Inalterado — NOT_REVIEWED,
     LOW_CONFIDENCE e AMBIGUOUS não formam proposta.
 6 CONFIRMATION_POLICY_DECLARED ........... REFORÇADO — a confirmação passa a
     exigir que a governança tenha respondido àquela ação, domínio,
     finalidade e principal.
 7 DESTRUCTIVE_INTENT_BINDING_DECLARED .... REFORÇADO — §3 e §4.
 8 GOVERNANCE_PARITY_ACROSS_CHANNELS ...... SIM, provado nos dois sentidos:
     u90 (passam) e u91 (falham nos mesmos quatro bindings).
 9 AUDIT_AND_RECEIPT_DECLARED ............. NOT_APPLICABLE — sem recibo.
10 CURRENT_CAPABILITY_NOT_OVERSTATED ...... SIM — §14.
```

### 16.4 Parte II §12 — 8 obrigações

```text
1 citar esta diretriz .................... citada aqui e no plano.
2 declarar o que será implementado ....... os oito bindings do §4 do prompt.
3 declarar o que continua diferido ....... §14, linhas DEFERRED.
4 separar observação/preparação/aprovação/execução — observação é E4.9.7;
    preparação é a proposta; aprovação é o envelope; execução não existe.
5 identificar o usuário ou autoridade competente — usuário presente e
    autenticado; esta fatia não cria a infraestrutura que prova a presença.
6 definir falhas, rollback e concorrência . TypeError/ValueError no construtor,
    sem objeto parcial; sem escrita não há rollback; VOs congelados.
7 verificar compatibilidade com E3/E4 congeladas — delta zero em E3 e
    E4.1–E4.9.7; E4.3 intocada.
8 interromper em Stop Condition .......... EXERCIDA: parei na contradição do
    prompt (§10) em vez de escolher em silêncio.
```

### 16.5 Parte II §12.1 — 11 Stop Conditions mínimas

```text
 1 nova entidade persistente ou migração ... não exigida. MIGRATION_DELTA = 0.
 2 ownership de Workspace/Schedule/domínio/conector — não exigido; as
     comparações LEEM identificadores, não atribuem posse.
 3 armazenamento de credenciais ........... não exigido; nenhum campo novo.
 4 execução externa irreversível .......... não exigida; nada executa.
 5 ampliação silenciosa de autoridade ..... NÃO OCORRE — o corretivo só
     restringe; toda mudança de comportamento é uma recusa nova.
 6 assinatura de provedor não suportada ... não exigida.
 7 sincronização destrutiva de arquivos ... não exigida; sem I/O.
 8 perda de proveniência ou origem ........ não ocorre; canal, origem e ordem
     do lote preservados.
 9 colapso entre múltiplos Schedules ...... NOT_APPLICABLE.
10 execução sem rollback declarado ........ NOT_APPLICABLE.
11 alteração de congelados por conveniência não ocorre.
```

### 16.6 Parte II §12.2 — 11 provas mínimas

```text
 1 nenhuma chamada externa quando recusado . PROVADA (s03; recusas são puras).
 2 nenhum acesso fora do escopo autorizado . PROVADA e REFORÇADA (u71, u75).
 3 nenhuma escrita durante observação/preparação — PROVADA (s01).
 4 aprovação obrigatória antes de ação crítica — REPRESENTADA e reforçada;
     a ação crítica não existe.
 5 rollback sob falha injetada ............ NOT_APPLICABLE — sem escrita.
 6 proteção contra estado obsoleto ........ DEFERRED; version_etag e
     authenticated_at MODELAM, nada impõe. TOCTOU segue aberto.
 7 comportamento concorrente determinístico  NOT_APPLICABLE — VOs congelados.
 8 preservação de origem, versão e histórico PROVADA (u83 ordem, u19 lote).
 9 recibo fiel ao pedido e à execução ..... NOT_APPLICABLE — sem recibo.
10 cancelamento sem estado parcial oculto . NOT_APPLICABLE.
11 isolamento entre Schedules e Workspaces  PROVADA e REFORÇADA.
```

### 16.7 Parte III §13 — impacto sobre distinções

```text
1 cria distinção?          SIM — "resolução presente" e "resolução admissível
                           daquela ação" passam a ser distinguíveis
2 transforma distinção?    NÃO — nenhum valor é reescrito
3 compara distinções?      NÃO — compara contexto declarado, não patrimônio
4 muda acessibilidade?     NÃO
5 afeta persistência?      NÃO
6 altera proveniência?     NÃO — preserva canal, origem e ordem
7 altera história causal?  NÃO — CAUSAL_HISTORY_DEPENDENCY segue sendo apenas
                           motivo de bloqueio
```

### 16.8 E5 / COUT-P

```text
E4_INTEGRATION_OF_COUT_P = FORBIDDEN — respeitado
```

Nenhum score, escalarização ou dependência. `AssuranceLevel.satisfies` devolve
`bool` por comparação de membros, não por métrica.

---

## 17. Gates medidos

Clone limpo, PostgreSQL recriado e pré-migrado:

```text
COLLECTED        3393                                  (cadeia 85: 3311)
FULL_SUITE       3392 passed / 1 skipped / 0 failed    (cadeia 85: 3310/1/0)
RAW_SUITE        2925 passed / 468 skipped / 0 failed  (cadeia 85: 2843/468/0)
GLOBAL_COVERAGE  99,29%   — não caiu
  approval_enums.py            52/52    100%
  destructive_approval.py    237/237    100%
RUFF PASS   BLACK PASS (391)
MYPY app    7 históricos, NEW = 0
supressões / cast / Any novos: 0
ALEMBIC heads = current = c8a3f5017e94
git diff --check CLEAN
```

**Regressões, delta 0:**

```text
E3 = 732 · E4.1 = 40 · E4.2 = 42 · E4.3 = 255 · E4.4 = 74 · E4.5 = 187
E4.6 = 275 · E4.7 = 240 · E4.8 = 146 · E4.9.5 = 113 · E4.9.6 = 309
E4.9.7 = 285
```

**Fatia: E4.9.8 = 157 → 239** (207 unitários + 32 estáticos), três execuções
idênticas.

**Cinco caracterizações**, `stderr = 0`:

```text
cadeia 85:  0/8 · 0/5 · 0/9 · 0/3 · 11/11 EXIT=0
cadeia 86:  0/8 · 0/5 · 0/9 · 0/3 ·  0/11 EXIT=1
```

---

## 18. Arquivos

```text
ALTERADOS
  app/memory/models/approval_enums.py            helpers estritos
  app/memory/schemas/destructive_approval.py     OPERACAO_DE_GOVERNANCA,
                                                 bindings de proposta e envelope,
                                                 duplicata de blockers
  tests/unit/memory/test_destructive_approval.py fixtures coerentes, u50_1,
                                                 u64–u91
  tests/static/test_destructive_approval_isolation.py s19–s24, s99_6–s99_8
NOVO
  docs/entregas/entrega-4/EDR_E4_9_8_1_GOVERNANCE_IDENTITY_BINDING.md
```

Nada em E3, E4.3, contratos da E4.9.7, Alembic, migration, ORM, adapter,
efeito ou recibo.

---

## 19. Riscos restantes

**(a) Delegação não modelada é uma restrição visível ao usuário.** Um lote com
alvos de controladores diferentes não forma envelope, mesmo com poder real
sobre todos. Declarado, não escondido — e a saída é EDR, não relaxamento.

**(b) A igualdade de principal é frágil a qualquer renomeação externa.** Se o
IdP futuro emitir a mesma pessoa com referência diferente da gravada em
`control_principal_ref`, o envelope não se forma. É o comportamento correto sem
modelo de identidade, e é também o primeiro ponto a doer quando ele existir.

**(c) `GovernanceResolution` continua vazando na fonte.** Composição redigida,
fonte não. Fora do escopo por decisão da autoridade; segue como o candidato mais
provável a achado futuro.

**(d) TOCTOU e replay seguem abertos.** O binding é sobre coerência entre
evidências já representadas, não sobre o mundo. Nonce sem consumo continua
decoração até a E4.9.9.

**(e) Nona repetição do falso positivo de substring.** A lição estava
registrada e eu a reproduzi mesmo assim. As guardas por identificador e as
demonstrações `s99` reduzem o custo, mas o padrão é meu e não some por
disciplina escrita.

---

## 20. Estado

```text
PATCH_CHAIN = 86
MIGRATION_HEAD = c8a3f5017e94 (INALTERADO)
E4_9_8_1_IMPLEMENTATION = COMPLETE_CANDIDATE
E4_9_8 = AWAITING_INDEPENDENT_REAUDIT
AUTHENTICATOR = NONE        STEP_UP_RUNTIME = NONE
APPROVAL_PERSISTENCE = NONE ATOMIC_CONSUMPTION = NONE
ERASURE_EFFECT = NONE       ERASURE_RECORD_WRITER = NOT_COMPOSED
DELEGATION = NOT_MODELED
E4_9_READY = FALSE
E4_9_9 = NOT_STARTED
```

`PASS_FINAL` pertence à auditoria independente.
