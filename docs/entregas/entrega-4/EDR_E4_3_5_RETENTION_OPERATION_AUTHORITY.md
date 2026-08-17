# EDR E4.3.5 — Retention Operation Authority

**Natureza:** decisão de ampliação do vocabulário fechado de governança.
**Exigido por:** o próprio contrato da E4.3 — ampliar `CognitiveOperation`
exige EDR. Precedente estrito: `EDR_E4_3_3_...`.
**Complementa, sem reescrever:** `EDR_COUT_PIA_E4.md`,
`E4_3_GOVERNANCE_POLICY.md`,
`EDR_E4_3_3_EXPLICIT_ACCESSIBILITY_TRANSITION_AUTHORITY.md`,
`E4_3_4_GOVERNANCE_RESOLUTION_CONTEXT_BINDING.md`.

---

## 1. A lacuna confirmada

O preflight canônico da E4.9 devolveu sete Stop Conditions. A primária,
e a única que este corretivo fecha:

```text
STOP_CONDITION = RETENTION_OPERATION_AUTHORITY_GAP
```

`CognitiveOperation` tinha oito membros e **nenhum** representa avaliar
retenção, dispor de um sujeito ao expirar, ou apagar por obrigação
legítima. A lacuna foi reproduzida contra a cadeia 63:

| # | Demonstração na baseline | Resultado |
|---|---|---|
| 1 | membros de `CognitiveOperation` | **8** |
| 2 | `CognitiveOperation("retention_assessment")` | `ValueError` |
| 3 | `CognitiveOperation("retention_disposition")` | `ValueError` |
| 4 | `CognitiveOperation("legal_erasure")` | `ValueError` |
| 5 | `GovernanceRule(operations={"retention_assessment"})` | `TypeError: operations aceita apenas CognitiveOperation` |
| 6 | `deserialize_rules` com o token | `ValueError: 'retention_assessment' is not a valid CognitiveOperation` |
| 7 | pedir a resolução da operação | impossível — o parâmetro é tipado `CognitiveOperation` |

```text
AUTHORITY NOT REPRESENTABLE => E4.9 CANNOT RESOLVE THE EXACT OPERATION
```

O §11.4 do prompt da E4.9 exige resolver a **operação exata** antes de
tocar o sujeito. Sem membro que a represente, nem o caminho somente
leitura da E4.9 é construível.

---

## 2. As três operações e seus tokens

```python
CognitiveOperation.RETENTION_ASSESSMENT  = "retention_assessment"
CognitiveOperation.RETENTION_DISPOSITION = "retention_disposition"
CognitiveOperation.LEGAL_ERASURE         = "legal_erasure"
```

Tokens persistidos exatos, minúsculos com sublinhado, como os oito
anteriores. O vocabulário permanece **fechado**: ampliar de novo exige
novo EDR.

---

## 3. Por que três, e não uma

Uma operação genérica — `RETENTION` ou `ERASURE` — foi rejeitada, e a
razão é a mesma que sustenta todo o desenho de autoridade da E4.3:
conceder mais do que se pretende é o defeito, não a economia.

```text
AUTHORITY TO ASSESS  != AUTHORITY TO DISPOSE
AUTHORITY TO DISPOSE != AUTHORITY TO ERASE
AUTHORITY TO ERASE   != EFFECT EXECUTED
```

Os três atos têm consequências materialmente diferentes:

| Operação | Consequência máxima se autorizada | Reversível |
|---|---|---|
| `RETENTION_ASSESSMENT` | alguém descobre que um sujeito expirou | n/a — não muda nada |
| `RETENTION_DISPOSITION` | uma disposição é proposta ou autorizada | sim, enquanto não executada |
| `LEGAL_ERASURE` | um apagamento legítimo é autorizado | **não** |

Fundir avaliação e apagamento num membro só faria toda policy que
quisesse permitir a primeira conceder também o terceiro. Numa operação
irreversível, esse é o pior default possível.

Elas também não são etapas obrigatórias de um mesmo fluxo. Uma
disposição pode expirar sem que nada seja apagado; e uma obrigação
externa de apagamento pode chegar fora de qualquer prazo de retenção.
São autoridades vizinhas, não sequenciais.

---

## 4. Por que nenhuma operação existente serviria

**`READ`.** Uma avaliação de retenção lê `created_at` e memberships —
dados que `READ` já alcança —, e nesse sentido estreito não amplia
acesso a informação nenhuma. Mas o que ela produz não é uma leitura: é
uma afirmação sobre a permanência futura do sujeito. Reusar `READ` faria
toda policy que hoje admite leitura passar a admitir, sem novo ato de
publicação, uma capacidade que ninguém lhe concedeu.

```text
AUTHORITY TO READ != AUTHORITY TO ASSESS RETENTION
AUTHORITY TO READ != AUTHORITY TO FORGET
```

**`TRANSFORM`.** Produz nova versão ou derivação. Apagar não é
transformar, e o `TransformationRecord` correspondente descreveria uma
operação que não ocorreu.

```text
AUTHORITY TO TRANSFORM != AUTHORITY TO ERASE
```

**`ACCESSIBILITY_TRANSITION`.** Foi criada pela E4.3.3 justamente para
não ser reusada assim, e o argumento dela se aplica aqui sem alteração:
`ACCESSIBILITY != EXISTENCE`. Uma transição de acessibilidade não altera
existência; um apagamento altera.

```text
AUTHORITY TO CHANGE ACCESSIBILITY != AUTHORITY TO DELETE
```

---

## 5. `EMPTY_OPERATIONS_SCOPE_V1` não foi tocado

O conjunto continua com as **mesmas sete** operações históricas,
enumeradas literalmente. As três novas ficam de fora, como
`ACCESSIBILITY_TRANSITION` já ficava.

```text
OLD WILDCARD AUTHORITY   != FUTURE RETENTION AUTHORITY
EMPTY OPERATIONS         != ALL FUTURE OPERATIONS
FUTURE OPERATION DEFAULT = EXPLICIT OPT-IN REQUIRED
```

Uma policy publicada com `operations=()` antes deste corretivo resolve
as três como `NOT_APPLICABLE` — nem admite, nem nega: simplesmente não
se aplica. Isso está provado contra PostgreSQL real, com policy
efetivamente gravada, e contra a policy da própria baseline: a mesma
regra que devolve `ADMISSIBLE` para `READ` devolve `NOT_APPLICABLE` para
as três.

O mecanismo é o **positivo** criado pela E4.3.3, e nenhum ramo especial
por operação foi acrescentado a `matches()` — há teste estrutural que
verifica a ausência dos três tokens no código executável do método.

**V2 do curinga não foi criado.** Incluir uma operação futura no
envelope ampliaria retroativamente o alcance de versões imutáveis, e
exigiria EDR próprio para isso — não é o que este corretivo faz.

---

## 6. Nenhuma versão publicada é modificada

Nenhuma linha de `governance_policies` é reescrita, republicada ou
migrada. O payload é montado a partir de `op.value` ordenado, então
acrescentar membros ao enum não altera bytes de regra alguma que não os
cite. Provado no banco: `rules::text` e `updated_at` idênticos antes e
depois de resolver as três operações novas contra a policy.

Policy publicada continua imutável pelo repositório e por mutação ORM
direta — inclusive quando a mutação tentada é justamente ganhar a
autoridade nova (`PIA-8028`).

---

## 7. Nada é executado aqui

```text
AUTHORITY VOCABULARY != OPERATION IMPLEMENTATION
PERMISSION           != EXECUTION
E4_3_5               != E4_9
```

Nomear `LEGAL_ERASURE` não cria mecanismo de apagamento. O preflight da
E4.9 registrou — e este corretivo não muda — que o PIA-OS hoje **não**
alcança conteúdo externo, **não** possui primitiva de auditoria de
apagamento, **não** tem ponto de composição para forgetting no caminho
de leitura, e **não** tem contrato de aprovação com identidade
verificável.

Este corretivo não cria nenhuma dessas coisas, e há teste por AST sobre
todo `app/memory` provando a ausência de `RetentionPolicy`,
`RetentionRule`, `RetentionAssessment`, `RetentionDecision`,
`ErasureRecord`, da tabela `retention_policies` e de métodos
`assess_retention` / `dispose` / `erase` / `forget`.

---

## 8. Stop Conditions da E4.9 que continuam abertas

```text
RETENTION_OPERATION_AUTHORITY_GAP   = CLOSED (candidato, sob auditoria)
ERASURE_TARGET_OWNERSHIP_GAP        = OPEN
LEGAL_ERASURE_CAUSAL_HISTORY_GAP    = OPEN/CONDITIONAL
ERASURE_AUDIT_PRIMITIVE_GAP         = OPEN
ON_EXPIRY_ACTION_UNRESOLVED         = OPEN
RETENTION_RETRIEVAL_COMPOSITION_GAP = OPEN
DESTRUCTIVE_EXECUTION_AUTHORITY_GAP = OPEN
E4_9_IMPLEMENTATION                 = NOT_STARTED
```

Fechar a autoridade **não** libera a E4.9. Este corretivo remove um
bloqueio de sete; os outros seis pedem decisões próprias, e nenhuma
delas é decisão do implementador.

---

## 9. SOPHIA

```text
COMMERCIAL_BRAND = SOPHIA
SYSTEM_CODEBASE_AND_ARCHITECTURE = PIA-OS
```

Nenhum namespace, kernel ou backend SOPHIA foi criado. A consequência
prospectiva que este corretivo habilita é modesta e vale dizer sem
inflar: a partir dele, uma instalação **pode declarar** quem tem
autoridade para avaliar retenção, propor disposição e autorizar
apagamento. Ela ainda não pode fazer nenhuma dessas coisas.

```text
CURRENT_CAPABILITY_NOT_OVERSTATED = TRUE
```

---

## 10. Ampliar de novo exige novo EDR

`CognitiveOperation` passa de oito para onze membros e permanece
fechado. O teste que enumera o vocabulário literalmente foi atualizado —
não afrouxado: ele continua exaustivo e continua falhando diante de
qualquer membro que alguém acrescente sem editá-lo e explicar por quê.
