# EDR E4.9.7.4 — Verificação explícita da capacidade

**Natureza:** corretivo mínimo do achado A6 da auditoria independente da
E4.9.7.3. Uma linha de produção.
**Baseline:** cadeia 83 (`79f70b05`), `E4_9_7_3 = FAIL_CORRECTIVE_REQUIRED`.

```text
OMITTED_VERIFICATION != VERIFIED_TRUE
DEFAULT_TRUE = IMPLICIT_AUTHORITY
VERIFIED_CAPABILITY != ASSUMED_CAPABILITY
CAPABILITY_OBSERVED != CAPABILITY_VERIFIED
```

```text
A6_VERIFIED_DEFAULT_AUTHORITY = FIXED
MIGRATION_DELTA = 0   DATABASE_SCHEMA_DELTA = 0   E3_DELTA = 0
EFFECT_DELTA = 0      ERASURE_RECORD_WRITER_DELTA = 0   API_DELTA = 0
```

---

## 1. Causa — e por que este erro é de espécie diferente dos anteriores

### 1.1 O que aconteceu

Ao acrescentar `field(repr=False)` em `operation` e `scope` na cadeia 83, escrevi
também:

```python
verified: bool = True
```

**O default não era necessário.** `dataclasses.field()` sem `default` nem
`default_factory` deixa o campo obrigatório, então `operation` e `scope`
continuaram sem default e nunca forçaram um valor em `verified`. Foi acréscimo
reflexo — presumi uma restrição de ordenação de dataclass que não existia — e
não há linha no EDR da cadeia 83 que o justifique, porque eu não percebi que o
tinha feito.

### 1.2 Por que é pior que as alegações excessivas anteriores

Os cinco achados anteriores foram **alegações mais fortes que a prova**: o
código fazia menos do que o documento dizia. Este é diferente: o **contrato
público mudou** e o documento nem mencionou.

```text
cadeia 82:  VerifiedDeletionCapability(operation, scope, verified)
            omitir verified → TypeError

cadeia 83:  VerifiedDeletionCapability(operation, scope, verified=True)
            omitir verified → capacidade VERIFICADA
```

E a consequência atravessa a fronteira que esta fatia inteira existe para
proteger:

```text
OMITTED_VERIFICATION → VERIFIED_CAPABILITY → SUCCESS_DESCRIPTOR
```

Um descritor de sucesso é exatamente o contrato que um executor futuro vai
consumir. Tornar a verificação verdadeira por omissão move a falha para a
fronteira de autoridade **antes de o executor existir** — que é o pior momento
para introduzi-la, porque não há nada em runtime que a revele.

Vale nomear o que isto contradiz: a própria E4.9.7 declarou que capacidade
presumida é a forma silenciosa do *confused deputy*, e `u07` prova que
`verified=False` não constrói descritor. Eu mantive a prova do caso negativo e
abri o caso da omissão.

### 1.3 Por que a suíte não pegou

Todas as fábricas e chamadas existentes passam `verified=True` explicitamente.
Os testes mediam:

```text
u07  verified=False não vira descritor de sucesso     ✔ passava
u08  tipo não-bool é recusado                          ✔ passava
u108 verified=True aparece no repr                     ✔ passava
```

Nenhum media que o **argumento é obrigatório**. A suíte inteira passa enquanto a
assinatura pública regride — e essa é a lição estrutural: teste de valor não
substitui teste de assinatura. Um contrato tem duas partes, o que ele aceita e
o que ele exige, e eu só testava a primeira.

`u109` e `u110` fecham por reflexão, `s29` pela AST — porque o defeito entrou
como uma linha de anotação com valor, e é essa linha que a guarda inspeciona.

---

## 2. Baseline e caracterizações

```text
HEAD 79f70b05f68bcd7ea71d015a2b78c5a7396e9a39
PARENT df310bbf…  TREE 87697f91…  PATCH_ID fdcffb9d…  PATCH_CHAIN 83
MIGRATION_HEAD c8a3f5017e94   árvore limpa   84 commits
app/cognitive  be407b46f679a009e0f7f7e9f01fb784f08dea54
backend/alembic cc68c3e274f388bda2a8674d6432d515bb8cbc4a
```

Os **quatro** scripts externos, byte a byte inalterados:

```text
cadeia 83:  0/8 EXIT=1 · 0/5 EXIT=1 · 0/9 EXIT=1 · 3/3 EXIT=0
cadeia 84:  0/8 EXIT=1 · 0/5 EXIT=1 · 0/9 EXIT=1 · 0/3 EXIT=1
stderr = 0 bytes nas oito execuções
```

---

## 3. Assinaturas — anterior, regredida e final

| Cadeia | Assinatura | Omitir `verified` |
|---|---|---|
| 82 | `(operation: str, scope: str, verified: bool)` | `TypeError` |
| 83 | `(operation: str, scope: str, verified: bool = True)` | capacidade verificada |
| **84** | `(operation: str, scope: str, verified: bool)` | **`TypeError`** |

A cadeia 84 restaura exatamente a assinatura da 82. `operation` e `scope`
mantêm `field(repr=False)` — a redação da cadeia 83 fica intacta.

### 3.1 Por que default `False` também estaria errado

Seria a correção intuitiva e é uma armadilha:

```text
Ausência de afirmação != Afirmação de ausência
```

`verified=False` significa **"o resolvedor observou a capacidade e ela não se
confirmou"** — é um estado observado, com valor informativo, que produz a recusa
`DELETION_CAPABILITY_NOT_VERIFIED`. Um default `False` faria toda omissão se
disfarçar de observação negativa, apagando a diferença entre "não verifiquei" e
"verifiquei e falhou". O chamador declara o que observou; se não observou, não
constrói.

Pela mesma razão, nem sentinel, nem `None`, nem factory. `u110` prova `MISSING`
nos dois campos da dataclass.

---

## 4. Impacto público e consumidores

```text
BREAKING_CHANGE = verified volta a ser obrigatório
CONSUMERS_IMPACTED = 0
```

Não existe consumidor runtime da porta (`s10`), e a produção **não constrói**
`VerifiedDeletionCapability` em lugar algum — `s30` prova isso na AST,
justamente para impedir que um construtor auxiliar devolva a autoridade
implícita com outro nome.

Todas as chamadas em teste já passavam `verified` explicitamente, então nenhuma
precisou mudar. A restauração é, em termos de código chamador, invisível — e é
exatamente por isso que a regressão passou.

---

## 5. Guarda contra a repetição

`u117` fixa **quais campos têm default** em todos os sete contratos da fatia:

```text
ControlScope                 —
CustodyNamespace             —
VerifiedDeletionCapability   —
ReferenceProvenance          position
ErasureTargetReference       expected_namespace
ErasureTargetDescriptor      version_etag
TargetResolutionRefusal      classified_as, observed_dimension
```

Um default novo em qualquer campo derruba o teste. É a contramedida direta para
o modo de falha desta rodada: assinatura pública alterada sem intenção, dentro
de um corretivo sobre outro assunto.

`u116` prova que nenhuma fábrica de teste mascara a omissão, e `s30` que
nenhuma de produção existe.

---

## 6. Evidência antes/depois

| Evidência | Cadeia 82 | Cadeia 83 | Cadeia 84 | Regressão |
|---|---|---|---|---|
| `A6_VERIFIED_PARAMETER_DEFAULTS_TRUE` | ausente | REPRODUCED | NOT_REPRODUCED | `u109`, `s29` |
| `A6_OMISSION_CONSTRUCTS_VERIFIED_CAPABILITY` | ausente | REPRODUCED | NOT_REPRODUCED | `u111` |
| `A6_OMISSION_ALLOWS_SUCCESS_DESCRIPTOR` | ausente | REPRODUCED | NOT_REPRODUCED | `u112` |
| `VERIFIED_PARAMETER_DEFAULT` | `_empty` | `True` | `_empty` | `u110` |

---

## 7. O que NÃO mudou

```text
4971 = 0/8   4972 = 0/5   4973 = 0/9        correções anteriores intactas
operation e scope com field(repr=False)     preservados
verified visível no repr                    u118
as 14 representações sem vazamento          u118, s25
inventário por reflexão                     s25_1
ReferenceOrigin fechado                     inalterado
opaque_reference, transient_locator,
  version_etag redigidos                    inalterados
MATERIAL_EXACT_TARGET_PROOF = DEFERRED      inalterado
capability.scope = "workspace/w1/*"         u106
provider-neutrality                         u107
cross-tenant externo e credential
  confusion DEFERIDOS                       inalterados
imutabilidade, igualdade, tz-aware          inalterados
zero escrita, rede, adapter, efeito         u69, s02–s04
```

Nenhuma outra assinatura pública foi tocada, e o corretivo não foi aproveitado
para refatoração.

---

## 8. Conformidade documental — quatro camadas (Master v2.3)

### 8.1 `PIA_OS_SOPHIA_MASTER_COMPATIBILITY` — 20 linhas

```text
├── USER_AUTHORITY_PRESERVED ................ REFORÇADO — é o achado A6: a
│     omissão deixou de conceder verificação.
├── SOPHIA_BRAND_PIA_OS_CODEBASE_PRESERVED .. SIM.
├── MODULE_SCOPE_AND_DEFERRED_CAPABILITIES ... Escopo: uma linha de produção.
│     Diferidos: adaptador, efeito, E4.9.8.
├── SCHEDULE_MODE_DECLARED ................... NOT_APPLICABLE — corrective only.
├── AI_ROLE_AND_STEP_INSTRUCTION_DISTINGUISHED NOT_APPLICABLE.
├── PROVIDER_CONNECTION_METHOD_DECLARED ...... NOT_APPLICABLE.
├── AUTOMATION_SCOPE_DECLARED ................ NENHUMA.
├── APPROVAL_GATES_DECLARED .................. NOT_APPLICABLE — nada executa; e
│     é justamente por isso que o contrato precisa estar certo antes.
├── PERSISTENCE_BEHAVIOR_DECLARED ............ NENHUMA.
├── MULTI_AI_RESULT_ATTRIBUTION_DECLARED ..... NOT_APPLICABLE.
├── DIVERGENCE_PRESERVATION_DECLARED ......... SIM — nenhuma normalização.
├── CONCURRENT_WORK_ISOLATION_DECLARED ....... Contratual; externo DEFERIDO.
├── BACKGROUND_EXECUTION_AUTHORIZATION ....... NOT_APPLICABLE.
├── RESOURCE_LIMITS_QUEUE_AND_COST_DECLARED .. NOT_APPLICABLE.
├── REMOTE_RESOURCE_SCOPE_DECLARED ........... NENHUM acesso remoto.
├── OBSERVATION_PREPARATION_EXECUTION ........ Continua só OBSERVAÇÃO — e
│     `verified` é o campo que registra o que foi OBSERVADO.
├── CREDENTIAL_AND_SECRET_BOUNDARY_DECLARED .. Inalterado desde a cadeia 83.
├── FAILURE_ROLLBACK_AND_CONCURRENCY ......... Sem escrita, nada a reverter.
├── CURRENT_CAPABILITY_NOT_OVERSTATED ........ §1.2 registra que o contrato
│     mudou sem o documento dizer — a omissão documental é o próprio achado.
└── FROZEN_MODULES_UNCHANGED ................. cognitive e alembic idênticos.
```

### 8.2 `SOPHIA_UX_COMPATIBILITY` — 17 linhas

```text
├── USER_AUTHORITY_PRESERVED ................. REFORÇADO — ver §8.1.
├── SCHEDULE_MODE_DECLARED ................... NOT_APPLICABLE.
├── AUTOMATION_SCOPE_DECLARED ................ NENHUMA.
├── PERSISTENCE_BEHAVIOR_DECLARED ............ NENHUMA.
├── PROVIDER_NEUTRALITY_PRESERVED ............ SIM — inalterado (`u107`).
├── PERSONALIZATION_REVERSIBLE ............... NOT_APPLICABLE.
├── CONCURRENT_WORK_ISOLATION_DECLARED ....... Contratual; externo DEFERIDO.
├── BACKGROUND_EXECUTION_AUTHORIZATION ....... NOT_APPLICABLE.
├── RESOURCE_LIMITS_AND_QUEUE_DECLARED ....... NOT_APPLICABLE.
├── AI_ROLE_CONTROL_DECLARED ................. NOT_APPLICABLE.
├── ROLE_AND_STEP_INSTRUCTION_DISTINGUISHED .. NOT_APPLICABLE.
├── PIA_SEQUENCE_SUGGESTION_BEHAVIOR ......... NOT_APPLICABLE.
├── MULTI_AI_RESULT_ATTRIBUTION_DECLARED ..... NOT_APPLICABLE.
├── PIA_INTEGRATION_DIVERGENCE_PRESERVATION .. NOT_APPLICABLE.
├── POST_RESULT_USER_COMMAND_DECLARED ........ NOT_APPLICABLE.
├── RESULT_APPROVAL_AND_PERSISTENCE ......... Distinguidos por ausência.
└── FROZEN_MODULES_UNCHANGED ................. SIM.
```

### 8.3 `MULTICHANNEL_COMMAND_COMPATIBILITY_v1_3` — 10 marcadores

```text
├── INPUT_CHANNELS_DECLARED ................. TEXT | VOICE, ambos futuros.
├── COMMAND_ENVELOPE_DECLARED ............... Envelope é da E4.9.8, NÃO criado.
├── CHANNEL_NORMALIZATION_DECLARED .......... NOT_APPLICABLE.
├── IDENTITY_CONTEXT_AND_SCOPE_DECLARED ..... Inalterado desde a cadeia 83.
├── VOICE_CONFIDENCE_AND_CORRECTION ......... NOT_APPLICABLE.
├── CONFIRMATION_POLICY_DECLARED ............ NOT_APPLICABLE — mas o achado é
│     da mesma família: o adendo v1.3 proíbe que confirmação nasça de omissão,
│     e `verified` por default era omissão virando afirmação.
├── DESTRUCTIVE_INTENT_BINDING_DECLARED ..... Inalterado.
├── GOVERNANCE_PARITY_ACROSS_CHANNELS ....... SIM — nenhum canal concede
│     verificação que não foi declarada.
├── AUDIT_AND_RECEIPT_DECLARED .............. NOT_APPLICABLE — sem recibo.
└── CURRENT_CAPABILITY_NOT_OVERSTATED ....... SIM — §1.2 e §3.
```

### 8.4 Parte II §12 — 8 obrigações, 11 Stop Conditions, 11 provas

**Oito obrigações:** cumpridas — diretriz citada; implementado no §3; diferido
no §9; observação/preparação/aprovação/execução separadas; autoridade é o
usuário e o corretivo **restaura** a exigência de declaração explícita; sem
escrita não há rollback; compatibilidade por regressão delta zero; nenhuma Stop
Condition disparou.

**Onze Stop Conditions mínimas:** nenhuma disparou. Em especial, `verified` não
tem default de espécie alguma e a omissão não constrói capacidade nem descritor.

**Onze provas mínimas:** PROVADAS — nenhuma chamada externa (`s04`, `u69`),
nenhum acesso fora do escopo (`u62`–`u66`), nenhuma escrita durante observação
(`u69`), preservação de origem e versão (`u74`), isolamento entre Workspaces
(`u62`). `NOT_APPLICABLE` — aprovação prévia, rollback, concorrência,
recibo, cancelamento. `DEFERRED` — estado obsoleto.

### 8.5 Checklist de impacto sobre distinções (Parte III §13)

```text
1. cria distinção?          NÃO — restaura uma que a cadeia 83 apagou:
                            "não verificado" voltou a ser distinguível de
                            "verificado"
2. transforma distinção?    NÃO
3. compara distinções?      NÃO
4. muda acessibilidade?     NÃO
5. afeta persistência?      NÃO — zero ORM, zero migração
6. altera proveniência?     NÃO
7. altera história causal?  NÃO
```

---

## 9. Gates medidos

Clone limpo, PostgreSQL recriado e **pré-migrado**:

```text
COLLECTED        3154                                  (cadeia 83: 3136)
FULL_SUITE       3153 passed / 1 skipped / 0 failed    (cadeia 83: 3135/1/0)
RAW_SUITE        2686 passed / 468 skipped / 0 failed  (cadeia 83: 2668/468/0)
GLOBAL_COVERAGE  99,26%   — não caiu
  target_resolution_enums.py    31/31   100%
  schemas/erasure_target.py    198/198  100%
  ports/erasure_target.py        5/5    100%
RUFF PASS   BLACK PASS (387)
MYPY app    7 históricos, NEW = 0
supressões / cast / Any novos: 0
ALEMBIC heads = current = c8a3f5017e94, single head
git diff --check CLEAN
```

**Regressões, delta 0:**

```text
E3 = 732 · E4.1 = 40 · E4.2 = 42 · E4.3 = 255 · E4.4 = 74 · E4.5 = 187
E4.6 = 275 · E4.7 = 240 · E4.8 = 146 · E4.9.5 = 113 · E4.9.6 = 309
```

E4.9.7: **267 → 285** (252 unitários + 33 estáticos), três execuções idênticas.

---

## 10. Arquivos alterados

```text
app/memory/schemas/erasure_target.py           verified: bool = True → bool
                                               (+ docstring registrando a causa)
tests/unit/memory/test_erasure_target.py       +10 funções (u109–u118)
tests/static/test_erasure_target_isolation.py  +2 guardas (s29, s30)
docs/.../EDR_E4_9_7_4_...md                    novo
```

Uma linha de comportamento em produção. `target_resolution_enums.py` e
`ports/erasure_target.py` não precisaram mudar.

---

## 11. Riscos que declaro

**(a) O modo de falha desta rodada não é de raciocínio, é de atenção.** Alterei
uma assinatura pública por reflexo, dentro de um corretivo sobre outro assunto,
e não notei. `u117` é a contramedida específica — fixa o conjunto de campos com
default —, mas ela só cobre esta fatia. A regra geral que registro: **um
corretivo que altera assinatura pública sem que o prompt a mencione é uma Stop
Condition**, e eu deveria tê-la disparado sozinho.

**(b) A suíte media valor, não exigência.** `u109`/`u110`/`s29` fecham o caso,
mas o padrão vale além dele: nenhum outro contrato desta fatia tinha teste de
assinatura antes desta rodada.

**(c) `verified=True` continua sendo afirmação de quem resolveu.** O contrato
exige o campo; não verifica o mundo. Um adaptador que sempre devolvesse `True`
satisfaria o `Protocol` e produziria descritores falsos — inalterado desde a
E4.9.7, e é a razão de a E4.9.1 exigir adaptador **autorizado**.

**(d) Sétimo defeito consecutivo na mesma fatia.** Os seis primeiros foram
alegações mais fortes que a prova; este foi uma mudança de contrato não
declarada. São falhas de espécies distintas, e a contramedida de uma não cobre a
outra — o que sugere que a densidade de fronteiras desta fatia é alta o
suficiente para justificar auditoria de assinatura pública em todo corretivo,
não só de comportamento.

---

## 12. Estado

```text
PATCH_CHAIN = 84
MIGRATION_HEAD = c8a3f5017e94 (INALTERADO)
E4_9_7_4_IMPLEMENTATION = COMPLETE_CANDIDATE
E4_9_7 = AWAITING_INDEPENDENT_REAUDIT
A6 = FIXED
TARGET_RESOLVER_ADAPTER = NONE
ERASURE_EFFECT = NONE
ERASURE_RECORD_WRITER = NOT_COMPOSED
E4_9_READY = FALSE
E4_9_8 = NOT_STARTED
```

Não existe adaptador, não existe efeito, e a E4.9.8 não foi iniciada.
`PASS_FINAL` pertence à auditoria independente.
