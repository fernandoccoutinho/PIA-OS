# EDR E4.9.9.c — Avaliador puro de retenção

**Baseline:** cadeia 91 (`a76ec679`). **Saída:** cadeia 92.

```text
ASSESSMENT_ELIGIBILITY != DELETION_DECISION
EVALUATION             != DISPOSITION
NO_POLICY              != ELIGIBLE
CLOCK_INJECTED         = REQUIRED
LEGACY_PROTECTION_OVERRIDES_RETENTION_ELIGIBILITY
```

```text
E4_9_9_C = COMPLETE_CANDIDATE
RETENTION_EVALUATOR = IMPLEMENTED
SCHEDULER = NONE   DISPOSITION = NONE   PERSISTENCE = NONE
E4_9_9_D = NOT_STARTED
E4_9_READY = FALSE
PASS_FINAL = NOT_DECLARED
```

---

## 1. Duas omissões materiais corrigidas antes do código

Meu plano inicial tinha três decisões e **não incluía a proteção de
legado** no candidato. A autoridade apontou, e as duas correções são
graves o bastante para abrir este EDR.

**A proteção de legado é obrigatória no candidato.** A E4.9.8.3 existiu
para tornar esse estado **vinculável**; omiti-lo aqui faria um item que o
titular pediu para preservar aparecer como elegível a avaliação. Campo
obrigatório, sem default — um default faria a omissão parecer
`NOT_PROTECTED`, que é a forma exata da autoridade fabricada fechada pela
E4.9.7.4.

**Cinco decisões, não três.** `POLICY_NOT_EFFECTIVE` e
`PRESERVE_LEGACY_PROTECTED` não são refinamentos: são fatos distintos que
as outras três não conseguiriam expressar sem mentir.

E a janela da policy passou a ser verificada **primeiro**, com
`candidate.created_at <= evaluated_at` preservado.

---

## 2. Precedência, formalizada

```text
1. POLICY_NOT_EFFECTIVE        janela [effective_from, effective_until)
2. OUT_OF_SCOPE                nenhuma regra vigente alcança
3. PRESERVE_LEGACY_PROTECTED   o titular pediu para preservar
4. NOT_YET_DUE                 evaluated_at < effective_due_at
5. ASSESS_AND_INFORM           evaluated_at >= effective_due_at
```

A ordem não é arbitrária. Cada degrau responde a uma pergunta que só faz
sentido depois da anterior:

- perguntar se venceu antes de saber se a policy vigora produziria
  vencimento sob regra que não vale;
- perguntar sobre prazo antes da proteção de legado produziria "elegível"
  para item que o titular pediu para preservar.

`u10` e `u11` provam a ordem pelos casos que a exercitam: item protegido
**fora de escopo** continua `OUT_OF_SCOPE`; item protegido sob policy não
vigente continua `POLICY_NOT_EFFECTIVE`.

`s10` fixa a ordem na AST — medida por **linha**, não por `ast.walk`, o
que é registrado no §5.

### 2.1 Janela inclusiva no início, exclusiva no fim

```text
[effective_from, effective_until)
```

`u04` mede os três pontos: no `effective_from` a policy vigora; no
`effective_until` já não vigora; um microssegundo antes do início, não
vigora.

### 2.2 `OUT_OF_SCOPE` não é `NOT_YET_DUE`

```text
NO_APPLICABLE_RULE != NOT_YET_DUE
NO_POLICY          != ELIGIBLE
```

Colapsá-los faria "nenhuma regra fala deste item" parecer "ainda não
venceu", e a segunda leitura sugere que um dia vencerá — falso, e
induziria quem lê a esperar por uma elegibilidade que não vem. `u07`
prova a distinção pelo `next_due_at`, presente numa e ausente na outra.

---

## 3. O máximo, não o mínimo

```text
effective_due_at = MAX(due_at de todas as regras aplicáveis)
ASSESS_AND_INFORM somente quando evaluated_at >= effective_due_at
```

Melhoria conservadora que a autoridade aceitou e mandou formalizar.

Com o **mínimo**, uma regra de 30 dias neutralizaria outra que exige 365:
o item viraria avaliável enquanto uma política vigente ainda pedia
preservação. O máximo é a única leitura que não perde uma exigência de
preservação por causa de outra mais curta.

O resultado cita **três coisas distintas**:

| Campo | O que diz |
|---|---|
| `applicable_rule_ids` | todas as regras vigentes que alcançam o candidato |
| `due_rule_ids` | quais já venceram **individualmente** |
| `next_due_at` | quando a situação muda, só em `NOT_YET_DUE` |

`u12` é o caso central: com regras de 30 e 365 dias, aos 60 dias a
decisão é `NOT_YET_DUE`, `due_rule_ids == ("curta",)` e
`effective_due_at` é o de 365. A regra curta **consta como vencida** e
mesmo assim não decide.

`u14` prova que a ordem das regras na entrada não altera o resultado.

```text
EVERY_DECISION_CITES_ITS_BASIS
```

`rule_id` existe desde a E4.9.6 "para ser citado como fundamento de uma
avaliação futura". Esta é a avaliação futura, e `u17` prova que toda
decisão que alcança regras as cita.

---

## 4. Função pura

Sem estado, sem `__init__`, sem sessão, sem repositório. Um manager com
`__init__(session)` convidaria a consultar o banco lá dentro, e a leitura
de patrimônio é exatamente o que esta fatia não faz.

```text
CLOCK_INJECTED = REQUIRED
```

O instante é argumento **obrigatório e keyword-only**, sem default — um
default seria `now()` disfarçado. `u18` mede a assinatura; `u20` e `s02`
provam por AST que não existe `now`, `utcnow` nem `today` no módulo;
`u19` prova que a mesma entrada produz a mesma saída; `u21` prova que a
avaliação não muta a entrada.

**Âncora única.** Só `created_at`. `s09` prova que `updated_at` não
aparece: o preflight da E4.9.6 mediu que ele se move por transição de
acessibilidade, e ancorar nele faria um objeto reclassificado
**rejuvenescer**.

---

## 5. Uma guarda minha media outra coisa

`s10` verifica a ordem dos degraus na AST. A primeira versão coletava os
nós com `ast.walk` e chamava aquilo de ordem no código.

`ast.walk` é em **largura**: devolveu `ASSESS_AND_INFORM` primeiro, porque
o `return` final está diretamente no corpo da função enquanto os demais
estão dentro de `if`. A guarda teria passado a medir profundidade e a
chamar de ordem.

```text
WALK_ORDER != SOURCE_ORDER
```

Corrigida para ordenar por `(lineno, col_offset)`, e o mutante `s99_1`
usa a mesma lógica. É a décima primeira ocorrência da família
`GUARD_NAME != GUARD_MEASUREMENT` nesta linha, e desta vez a peguei
antes de publicar.

---

## 6. O vocabulário não pode crescer

```text
RetentionExpiryAction = ['assess_and_inform']   — um único membro
RetentionAnchor       = ['created_at']          — um único membro
```

A unicidade de `RetentionExpiryAction` desde a E4.9.6 é a **prova** de
que vencimento nunca dispôs de nada. Esta fatia não a amplia, e `s08`
fixa isso na AST do módulo da E4.9.6.

Nenhum membro de `RetentionAssessmentDecision` sugere apagar, mover,
agendar ou dispor — `u01` prova por lista fechada.

---

## 7. Guardas envelhecidas — quatro, revisadas uma a uma

| Guarda | Antes | Depois |
|---|---|---|
| `s01`, `s16` (policy) | nenhum serviço importa a policy | avaliador é consumidor **autorizado**; repositório segue com zero consumidores |
| `e435` (governança) | `RetentionAssessment` na lista de ausências | conjunto autorizado próprio, como a E4.9.5 e a E4.9.6 fizeram |
| `s10` (alvo) | — | avaliador lê `LegacyProtectionState`, com nota do porquê |

O que **não** mudou, e é o que importa:

```text
RETENTION_POLICY_REPOSITORY_CONSUMER = NONE
assess_retention · dispose · erase · forget   AUSENTES em todo app/memory
ErasureTargetResolverPort CONSUMERS = 0
```

---

## 8. Master Integrado v2.4

### 8.1 `PIA_OS_SOPHIA_MASTER_COMPATIBILITY` — 20 linhas

```text
 1 USER_AUTHORITY_PRESERVED ....... A avaliação INFORMA; a decisão continua
     do usuário, pelo caminho da E4.9.8. E legado protegido preserva.
 2 SOPHIA_BRAND_PIA_OS_CODEBASE ... SIM.
 3 MODULE_SCOPE_AND_DEFERRED ...... Implementado: vocabulário, candidato,
     resultado, função pura. Diferidos: orquestrador, disposição, UI.
 4 SCHEDULE_MODE_DECLARED ......... NOT_APPLICABLE — e é o marcador que mais
     importa aqui, porque avaliação de retenção é onde um agendador
     pareceria natural. A função só responde quando chamada (s01).
 5 AI_ROLE_AND_STEP_INSTRUCTION ... NOT_APPLICABLE.
 6 PROVIDER_CONNECTION_METHOD ..... NOT_APPLICABLE.
 7 AUTOMATION_SCOPE_DECLARED ...... NENHUMA — sem worker, fila ou disparo.
 8 APPROVAL_GATES_DECLARED ........ Elegibilidade NÃO é aprovação e não forma
     envelope (u32).
 9 PERSISTENCE_BEHAVIOR_DECLARED .. NENHUMA. MIGRATION_DELTA = 0.
10 MULTI_AI_RESULT_ATTRIBUTION .... NOT_APPLICABLE.
11 DIVERGENCE_PRESERVATION ........ SIM — rule_id citados sem normalização,
     em tupla ordenada; nunca set.
12 CONCURRENT_WORK_ISOLATION ...... Domínio do candidato comparado contra
     domain_ids da regra.
13 BACKGROUND_EXECUTION ........... NOT_APPLICABLE.
14 RESOURCE_LIMITS_QUEUE_AND_COST . NOT_APPLICABLE.
15 REMOTE_RESOURCE_SCOPE .......... NENHUM.
16 OBSERVATION_PREPARATION_EXEC ... Pura OBSERVAÇÃO; nem preparação.
17 CREDENTIAL_AND_SECRET_BOUNDARY . Nenhum campo de conteúdo, localizador,
     capacidade ou credencial (u31).
18 FAILURE_ROLLBACK_AND_CONCURRENCY Sem escrita, sem estado.
19 CURRENT_CAPABILITY_NOT_OVERSTATED ASSESS_AND_INFORM significa que uma
     regra venceu, não que algo deva ser apagado.
20 FROZEN_MODULES_UNCHANGED ....... cognitive e alembic byte a byte.
```

### 8.2 `SOPHIA_UX_COMPATIBILITY` — 17 linhas

```text
 1 USER_AUTHORITY_PRESERVED ......... REFORÇADO — proteção do titular vence
     prazo cumprido.
 2 SCHEDULE_MODE_DECLARED ........... NOT_APPLICABLE.
 3 AUTOMATION_SCOPE_DECLARED ........ NENHUMA.
 4 PERSISTENCE_BEHAVIOR_DECLARED .... NENHUMA.
 5 PROVIDER_NEUTRALITY_PRESERVED .... SIM.
 6 PERSONALIZATION_REVERSIBLE ....... NOT_APPLICABLE.
 7 CONCURRENT_WORK_ISOLATION ........ Por domínio.
 8 BACKGROUND_EXECUTION ............. NOT_APPLICABLE.
 9 RESOURCE_LIMITS_AND_QUEUE ........ NOT_APPLICABLE.
10 AI_ROLE_CONTROL_DECLARED ......... NOT_APPLICABLE.
11 ROLE_AND_STEP_INSTRUCTION ........ NOT_APPLICABLE.
12 PIA_SEQUENCE_SUGGESTION .......... O resultado é insumo de sugestão
     INFORMADA; legado protegido NÃO entra em limpeza automática.
13 MULTI_AI_RESULT_ATTRIBUTION ...... NOT_APPLICABLE.
14 PIA_INTEGRATION_DIVERGENCE ....... NOT_APPLICABLE.
15 POST_RESULT_USER_COMMAND ......... Inalterado.
16 RESULT_APPROVAL_AND_PERSISTENCE .. Avaliação não é aprovação e não
     persiste.
17 FROZEN_MODULES_UNCHANGED ......... SIM.
```

### 8.3 Multicanal v1.3 — 10 marcadores

```text
 1 INPUT_CHANNELS_DECLARED ........ Inalterado.
 2 COMMAND_ENVELOPE_DECLARED ...... Inalterado.
 3 CHANNEL_NORMALIZATION .......... NOT_APPLICABLE.
 4 IDENTITY_CONTEXT_AND_SCOPE ..... Domínio do candidato; sem identidade.
 5 VOICE_CONFIDENCE_AND_CORRECTION  NOT_APPLICABLE.
 6 CONFIRMATION_POLICY_DECLARED ... Inalterado — a avaliação não confirma.
 7 DESTRUCTIVE_INTENT_BINDING ..... NOT_APPLICABLE — não há intenção aqui.
 8 GOVERNANCE_PARITY_ACROSS_CHANNELS SIM, por construção: NÃO existe campo
     de canal no avaliador, logo não há como tratar voz diferente.
 9 AUDIT_AND_RECEIPT_DECLARED ..... NOT_APPLICABLE.
10 CURRENT_CAPABILITY_NOT_OVERSTATED SIM.
```

### 8.4 Parte II §12

**Oito obrigações** cumpridas: diretriz citada; implementado nos §2–§4;
diferidos no §10; estágios separados — pura observação; autoridade
competente é o usuário, e a avaliação apenas informa; sem escrita não há
rollback; compatibilidade E3/E4 por regressão delta zero; Stop Condition
assumida.

**Onze Stop Conditions:** nenhuma disparou — sem entidade persistente,
migration ou schema; sem alterar E3 ou os contratos das fatias anteriores;
sem scheduler, worker ou disparo automático; sem disposição; sem
ampliação de `RetentionExpiryAction`; sem consumidor de repositório; sem
credencial; sem acesso externo.

**Onze provas:** `PROVADAS` — nenhuma chamada externa, nenhuma escrita,
nenhum acesso fora do escopo, preservação de proveniência e ordem,
isolamento por domínio. `NOT_APPLICABLE` — rollback, concorrência,
recibo, cancelamento, aprovação. `DEFERRED` — estado obsoleto do alvo.

### 8.5 Parte III §13

```text
1 cria distinção?         SIM — cinco situações de retenção passam a ser
                          distinguíveis, incluindo "protegido" e "fora de
                          escopo", que antes não tinham nome
2 transforma distinção?   NÃO
3 compara distinções?     NÃO — compara idade contra prazo declarado
4 muda acessibilidade?    NÃO
5 afeta persistência?     NÃO — MIGRATION_DELTA = 0
6 altera proveniência?    NÃO
7 altera história causal? NÃO
```

### 8.6 Parte III §19 e E5/COUT-P

```text
MULTI_AI_HANDOFF_COMPATIBILITY = NOT_APPLICABLE
REASON = pure internal evaluation; no AI-to-AI runtime handoff introduced
E4_INTEGRATION_OF_COUT_P = FORBIDDEN
```

---

## 9. Gates medidos

```text
COLLECTED        3730                                  (cadeia 91: 3669)
FULL_SUITE       3729 passed / 1 skipped / 0 failed    (cadeia 91: 3668/1/0)
RAW_SUITE        3227 passed / 503 skipped / 0 failed  (cadeia 91: 3166/503/0)
GLOBAL_COVERAGE  99,30%
  retention_assessment_enums.py    12/12    100%
  retention_evaluator.py         101/101    100%
RUFF PASS   BLACK PASS (407)
MYPY app    7 históricos, NEW = 0
supressões / cast / Any novos: 0
ALEMBIC heads = a1f7c2d40e93 — INALTERADO
git diff --check CLEAN
```

**Seletores em delta zero:**

```text
E3 = 732 · E4.3 = 255 · E4.9.5 = 113 · E4.9.6 = 309 · E4.9.7 = 326
E4.9.8 = 299 · E4.9.9.a = 85 · E4.9.9.b = 90
```

**Fatia nova: E4.9.9.c = 61**, três execuções idênticas.

**Dez caracterizações**, `EXIT=1`, `stderr=0`. A nova é bilateral: **8/8
na cadeia 91**, **0/8 na 92**.

---

## 10. Riscos e limites

**(a) Sétimo contrato sem consumidor.** A E4.9.9.d o consumirá.

**(b) A avaliação responde sobre UM candidato.** Não enumera patrimônio,
e quem chamar em laço é responsável pelo custo. Enumerar exigiria leitura
de patrimônio, que esta fatia não faz.

**(c) `PRESERVE_LEGACY_PROTECTED` não impede exclusão.** Diz que a
retenção não a torna elegível. A E4.9.8.3 já declarou que `PROTECTED` não
é bloqueio automático; se a regra de produto exigir desbloqueio separado,
é autorização própria.

**(d) A âncora é única.** Se uma versão futura acrescentar outra, o
`_due_at` levanta erro em vez de inferir — declarado no código.

**(e) O resultado não é persistido.** Duas avaliações do mesmo item em
instantes diferentes podem divergir legitimamente, e nada as reconcilia.

---

## 11. Estado

```text
PATCH_CHAIN = 92
MIGRATION_HEAD = a1f7c2d40e93 (INALTERADO)
E4_9_9_C = COMPLETE_CANDIDATE
RETENTION_EVALUATOR = IMPLEMENTED
SCHEDULER = NONE   DISPOSITION = NONE   PERSISTENCE = NONE
ERASURE_EFFECT_ADAPTER = NONE
ERASURE_RECORD_WRITER = NOT_COMPOSED
DESTRUCTIVE_EXECUTION_SERVICE = NONE
E4_9_9_D = NOT_STARTED   E4_10 = NOT_STARTED
E4_9_READY = FALSE
PASS_FINAL = NOT_DECLARED
```
