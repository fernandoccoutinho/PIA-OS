# EDR E4.9.8.3 — Legacy Protection Binding Completion

**Natureza:** corretivo de **lacuna antecedente**, encontrado no preflight da
E4.9.9.a e confirmado pela autoridade.
**Baseline:** cadeia 87 (`36db755f`), `E4_9_STABILIZATION_AUDIT_1 = PASS_FINAL`.

```text
DOCUMENTED_BINDING != RUNTIME_BINDING
APPROVAL_WITHOUT_LEGACY_STATE = INCOMPLETE_APPROVAL
ABSENCE_OF_INFORMATION != NOT_PROTECTED
```

```text
LEGACY_PROTECTION_STATE_SOURCE = ONE
LEGACY_PROTECTION_STATE_REQUIRED_ON_DESCRIPTOR = TRUE
LEGACY_PROTECTION_STATE_REQUIRED_ON_SNAPSHOT = TRUE
LEGACY_PROTECTION_DEFAULT = NONE
UNKNOWN_AS_NOT_PROTECTED = FORBIDDEN
CHANGE_IN_EITHER_DIRECTION_INVALIDATES_APPROVAL = REPRESENTABLE
PROTECTED_IS_AUTOMATIC_PERMISSION = FALSE
PROTECTED_IS_AUTOMATIC_DENIAL = FALSE
E3_DELTA = 0   ALEMBIC_DELTA = 0   PERSISTENCE_DELTA = 0
DESTRUCTIVE_EFFECT_DELTA = 0
E4_9_9_A = STILL_BLOCKED_PENDING_AUDIT
```

---

## 1. A lacuna e as linhas canônicas que a provam

A autorização da E4.9.4 §5 exige nova aprovação quando muda "versão, estado ou
proteção de legado". O EDR da mesma fatia, §7, põe a proteção na lista de
invalidação.

O runtime da cadeia 87 não sustentava a decisão:

```text
SafeTargetSnapshot.legacy_protection_state       ABSENT
ErasureTargetDescriptor.legacy_protection_state  ABSENT
ApprovalBlockerKind.LEGACY_*                     ABSENT
TargetResolutionRefusalReason.LEGACY_*           ABSENT
```

Consequência prática: a E4.9.9.a persistiria um `ApprovalRecord`
estruturalmente incompleto, e a E4.9.9.d não teria contra o que comparar a
re-resolução fresca. Congelar uma aprovação sem esse dado seria pior que não
persistir.

Esta é uma lacuna **antecedente**: nasceu documental, não em código escrito
agora.

---

## 2. Inventário medido — `MEASURED`

Correção que a autoridade exigiu ao plano, e que registro nominalmente porque
eu havia apresentado definições como se fossem consumidores:

```text
construções de PRODUÇÃO de SafeTargetSnapshot          0
conversões descritor -> snapshot em produção           0
schemas/erasure_target.py                    DEFINE ErasureTargetDescriptor
schemas/destructive_approval.py              DEFINE SafeTargetSnapshot
tests/unit/memory/test_destructive_approval.py::snapshot()   fábrica DE TESTE
```

```text
DEFINITION_SITE != CONSTRUCTION_SITE
```

Sem consumidor de produção, a quebra pública não atinge caminho vivo algum.

Estado anterior das duas classes: 9 e 6 campos, um único default em cada
(`version_etag`), **todos** os campos com `compare=True` — a igualdade
estrutural já era total, o que é a razão de o campo novo bastar para tornar a
mudança detectável.

Nenhum estado de proteção pré-existente em E3 ou E4. A única ocorrência de
"legado" em `schemas/retention.py` é prosa que **nega** inferência por pasta,
uso ou legado.

Três instrumentos externos constroem `SafeTargetSnapshot`: `4981_original`,
`4981_v2` e `4982`.

---

## 3. Alternativas consideradas e rejeitadas

| Alternativa | Por que foi rejeitada |
|---|---|
| **default `NOT_PROTECTED`** | autoridade fabricada: toda omissão pareceria "não protegido", que é a forma exata do `verified = True` acidental fechado pelo A6 da E4.9.7.4. Mantém testes antigos verdes ao preço de mentir sobre o que foi apresentado |
| **apenas `ApprovalBlockerKind`** | bloqueio diz que **não pode aprovar**; não registra **o que foi apresentado**. Sem o estado no snapshot, a E4.9.9.d não teria contra o que revalidar, e a mudança de `PROTECTED` para `NOT_PROTECTED` ficaria invisível |
| **wrapper / `SafeTargetSnapshotV2`** | criaria duas famílias de aprovação convivendo, e cada consumidor futuro escolheria uma. Duas verdades sobre o mesmo fato é o defeito que a fonte única existe para impedir |
| **inferir de idade, pasta, validação ou causalidade** | proteção é escolha **do titular**; derivá-la de metadado seria o PIA decidindo por ele |
| **campo obrigatório nas duas classes** | **adotada** |

---

## 4. Semântica dos dois estados

```text
LEGACY_PROTECTION_STATE = PRESENTED_AND_BOUND_FACT
LEGACY_PROTECTION_STATE != LEGAL_OWNERSHIP_PROOF
LEGACY_PROTECTION_STATE != USER_IDENTITY_PROOF
LEGACY_PROTECTION_STATE != DELETION_AUTHORITY
LEGACY_PROTECTION_STATE != AUTOMATIC_DENIAL
LEGACY_PROTECTION_STATE != AUTOMATIC_PERMISSION
```

Esta fatia **não** decide que item protegido é impossível de excluir. Decide que
o estado apresentado entra no binding e que qualquer mudança exige nova
aprovação — **nas duas direções**:

```text
PROTECTED_AT_APPROVAL     + NOT_PROTECTED_AT_EXECUTION = APPROVAL_INVALID
NOT_PROTECTED_AT_APPROVAL + PROTECTED_AT_EXECUTION     = APPROVAL_INVALID
SAME_STATE_REQUIRED = TRUE
```

`u118` e `u127` provam a distinção nas duas classes; a igualdade estrutural
cobre as duas direções por construção, e não por uma guarda que só detecte
perda de proteção.

### 4.1 Quatro fatos distintos

```text
LEGACY_PROTECTION != LEGAL_HOLD          imposição externa vs. escolha do titular
LEGACY_PROTECTION != CANONICAL_VERSION   qual conteúdo é o corrente
LEGACY_PROTECTION != CAUSAL_DEPENDENCY   outro registro depende deste
```

`u121` prova a disjunção com `ApprovalBlockerKind`; `s36` prova que nenhum
membro de `ApprovalBlockerKind` nem de `RefusalDimension` contém `LEGACY`.

### 4.2 Indeterminação é recusa, não estado

```text
PROTECTION_STATE_UNKNOWN = TARGET_RESOLUTION_REFUSAL
```

`TargetResolutionRefusalReason.LEGACY_PROTECTION_STATE_UNRESOLVED`. Um terceiro
membro no enum faria a indeterminação virar aprovação silenciosa.

**`RefusalDimension` não foi ampliada** — recuo aceito da minha proposta
inicial. `observed_dimension` descreve divergência **contextual** entre
governança, identidade e alvo; estado não resolvido é ausência de fato
observável, não divergência de contexto. O motivo fechado já identifica a
recusa; ampliar seria delta público redundante. `u112` e `s36` fixam os 8
membros originais.

---

## 5. Materializador canônico

```text
SafeTargetSnapshot.from_descriptor(descriptor) -> SafeTargetSnapshot
```

Autorizado pela autoridade após o inventário mostrar **zero** conversões de
produção. Sem um ponto canônico, a cópia dos sete campos ficaria espalhada por
cada chamador futuro, e a exclusão do localizador dependeria de cada um lembrar
de não copiá-lo.

**Copiados — os sete:**

```text
target_class · subject_coid · control_scope · custody_namespace
origin · version_etag · legacy_protection_state
```

**Excluídos — os três, cada um por razão distinta:**

| Campo | Por que não atravessa |
|---|---|
| `transient_locator` | endereça o objeto material; a E4.9.7 gastou dois corretivos estabelecendo que ele não sobrevive ao efeito, e um snapshot que circula e é apresentado o levaria junto |
| `capability` | é o que a **conta** pode; o snapshot descreve o que foi **apresentado** ao usuário, não a autoridade |
| `resolved_at` | instante da resolução, transitório; o instante que importa à aprovação é o da materialização da proposta |

### 5.1 Cópia explícita, nunca reflexão

```text
EXPLICIT_COPY != AUTOMATIC_PROPAGATION
```

A tentação era `asdict` ou `**` — menos linhas, e aparentemente "menos sujeito a
esquecimento". Seria pior: com reflexão, um campo novo no descritor entraria no
snapshot **sozinho**, sem ninguém decidir. É exatamente assim que
`transient_locator` atravessaria a fronteira.

`s17_1` fixa na AST os sete copiados, exige que cada `kwarg` copie o atributo
de mesmo nome do `descriptor`, e recusa `asdict(`, `**descriptor`, `getattr(`,
`vars(` e `fields(`.

`from_descriptor` recusa tipo incorreto com `TypeError` explícito (`u131`).

---

## 6. Mudança pública deliberada

```text
OMITTED_LEGACY_PROTECTION_STATE = TypeError
DEFAULT_LEGACY_PROTECTION_STATE = FORBIDDEN
PUBLIC_SIGNATURE_DELTA = EXPECTED_AND_DOCUMENTED
```

Delta público, medido e comparado 87 → 88:

```text
+ LegacyProtectionState (PROTECTED, NOT_PROTECTED)
+ TargetResolutionRefusalReason.LEGACY_PROTECTION_STATE_UNRESOLVED
+ legacy_protection_state obrigatório em ErasureTargetDescriptor
+ legacy_protection_state obrigatório em SafeTargetSnapshot
+ SafeTargetSnapshot.from_descriptor
+ export de LegacyProtectionState em app.memory.models

RefusalDimension            8 membros, INALTERADO
ApprovalBlockerKind         6 membros, INALTERADO
defaults de todas as dataclasses   INALTERADOS
nenhum outro classmethod, parâmetro, ordem ou tipo
```

Nenhuma fixture de teste esconde a escolha: as fábricas declaram
`NOT_PROTECTED` com nota escrita de que é decisão consciente, e os testes
nominais `u113`, `u123`, `u128`, `u133`, `u138` exercitam `PROTECTED`
explicitamente nos dois lados e nos dois canais.

---

## 7. Três guardas envelheceram — corrigidas pela propriedade real

| Guarda | Antes | Depois |
|---|---|---|
| `s17` | proibia o **nome** `ErasureTargetDescriptor` no código executável | prova que o snapshot **não tem** os três campos e que `from_descriptor` **não os copia**; `s17_1` fixa os sete |
| `u53` | inspecionava todas as dataclasses do namespace | filtro por **módulo de origem** — o import trouxe um contrato de outro módulo, cujo `transient_locator` é legítimo e já provado no lugar certo |
| `s15` | retrato dos sete contratos da E4.9.7 | atualizado com o campo obrigatório novo, com nota |

```text
NAME_MENTIONED != FIELD_REUSED
```

`u53` é o caso a registrar: a fraqueza era **pré-existente** — a guarda já
media o módulo errado se qualquer import trouxesse uma dataclass — e só ficou
visível agora. Guarda que mede o módulo errado não protege este módulo.

---

## 8. Instrumentos — três categorias, não "seis congelados"

### 8.1 A descoberta

Os dois instrumentos afetados devolvem, na cadeia 88:

```text
reproduce_e4981_binding_defects_v2   0/11  EXIT=1  stderr=0
reproduce_e4982_contract_defects      0/3  EXIT=1  stderr=0
```

Numericamente idênticos ao esperado. **Probatoriamente inválidos.** Eles
constroem `SafeTargetSnapshot` sem o campo obrigatório, a construção levanta
`TypeError`, e o `except TypeError: return False` interno converte a falha em
`NOT_REPRODUCED`.

```text
ZERO_BY_PROOF != ZERO_BY_CONSTRUCTION_FAILURE
ORIGINAL_RESULT_ON_CHAIN_88 = MEASURED_BUT_NOT_VALID_PROOF
```

É a mesma família de defeito que esta linha vem fechando desde a E4.9.7 —
resultado certo pelo motivo errado —, agora nos instrumentos.

### 8.2 `INSTRUMENT_VALIDITY_GATE`

Exigido pela autoridade antes do commit. Os três instrumentos desta fatia
verificam, **antes de qualquer sonda**, que a fixture constrói:

```text
FIXTURE_CONSTRUCTION_OK = TRUE
PROBES_REACHED_BEHAVIOR_UNDER_TEST = TRUE
```

Se não construir:

```text
INSTRUMENT_INVALID = FIXTURE_CONSTRUCTION_FAILED
EXIT = 2
```

Nunca `NOT_REPRODUCED`. Provado por mutante: uma cópia da `4981_v3` sem o campo
na fixture devolve `EXIT=2` e `FIXTURE_CONSTRUCTION_OK = FALSE (TypeError)` na
cadeia 88, e permanece válida na 87, onde o campo não existe.

```text
ZERO_BY_CONSTRUCTION_FAILURE = FORBIDDEN
```

### 8.3 Classificação

```text
HISTORICAL_ORIGINAL   7 preservados byte a byte, SHA-256 publicados
  4971 · 4972 · 4973 · 4974        executados na 88 — 0/8 · 0/5 · 0/9 · 0/3
  4981_original · 4981_v2 · 4982   preservados; NÃO executados como prova
                                   SEMANTICALLY_INCOMPATIBLE_AFTER_SIGNATURE_BREAK

COMPATIBILITY_COPY = CANONICAL_BILATERAL_PROOF
  4981_v3   0/11 nos dois lados, com o gate de validade
  4982_v2    0/3 nos dois lados, com o gate de validade

NEW_CHARACTERIZATION
  4983      8/8 na cadeia 87 · 0/8 na cadeia 88 · stderr=0
```

As cópias detectam o campo **por assinatura** e só o fornecem no lado que o
exige. Sem default de produção, sem monkeypatch, sem `try/except Exception`,
sem `Any`, `cast` ou `type: ignore`.

---

## 9. Garantias por camada

| Garantia | Camada |
|---|---|
| vocabulário fechado, dois membros, sem genérico | `TYPE_LEVEL` |
| campo obrigatório sem default nas duas classes | `TYPE_LEVEL` |
| recusa de não-membro em runtime | `APPLICATION_LEVEL` |
| distinguibilidade estrutural nas duas direções | `APPLICATION_LEVEL` |
| `from_descriptor` copia sete e exclui três | `APPLICATION_LEVEL` + `AUDIT_LEVEL` (`s17_1`) |
| fonte única do enum | `AUDIT_LEVEL` (`s31`) |
| indeterminação como recusa tipada | `TYPE_LEVEL` |
| **invalidação efetiva da aprovação** | `DEFERRED_TO_E4_9_9_D` |
| proteção persistente, UI, executor, efeito | `NOT_MODELED` |
| `PROTECTED` como bloqueio de produto | `NOT_MODELED` — exige autorização própria |

```text
STRUCTURAL_DISTINGUISHABILITY = IMPLEMENTED_HERE
EFFECTIVE_INVALIDATION = DEFERRED_TO_E4_9_9_D
```

Registro honesto do alcance: eu havia escrito no plano que "a proposta compara
lotes inteiros". Ela **armazena e valida**. Comparar contra re-resolução fresca
é da E4.9.9.d, e `u137` prova por reflexão que nenhum método de comparação
existe aqui.

---

## 10. Master Integrado v2.3

### 10.1 `PIA_OS_SOPHIA_MASTER_COMPATIBILITY` — 20 linhas

```text
 1 USER_AUTHORITY_PRESERVED ............... REFORÇADO. A proteção é do usuário
     e passa a integrar o que ele confirmou; mudá-la exige nova aprovação.
 2 SOPHIA_BRAND_PIA_OS_CODEBASE_PRESERVED . SIM.
 3 MODULE_SCOPE_AND_DEFERRED_CAPABILITIES . Implementado: enum, campo nas duas
     classes, materializador, recusa tipada. Diferidos: proteção persistente,
     UI, bloqueio de produto, comparação com re-resolução.
 4 SCHEDULE_MODE_DECLARED ................. NOT_APPLICABLE.
 5 AI_ROLE_AND_STEP_INSTRUCTION ........... NOT_APPLICABLE.
 6 PROVIDER_CONNECTION_METHOD ............. NOT_APPLICABLE.
 7 AUTOMATION_SCOPE_DECLARED .............. NENHUMA. Item protegido não entra
     em sugestão automática — e nenhuma sugestão automática existe.
 8 APPROVAL_GATES_DECLARED ................ O estado entra no binding; não vira
     permissão nem negação automática.
 9 PERSISTENCE_BEHAVIOR_DECLARED .......... NENHUMA. PERSISTENCE_DELTA = 0.
10 MULTI_AI_RESULT_ATTRIBUTION ............ NOT_APPLICABLE.
11 DIVERGENCE_PRESERVATION_DECLARED ....... SIM. Token fechado, sem
     normalização; repr nunca converte em texto livre.
12 CONCURRENT_WORK_ISOLATION_DECLARED ..... Inalterado.
13 BACKGROUND_EXECUTION_AUTHORIZATION ..... NOT_APPLICABLE.
14 RESOURCE_LIMITS_QUEUE_AND_COST ......... NOT_APPLICABLE.
15 REMOTE_RESOURCE_SCOPE_DECLARED ......... NENHUM acesso remoto.
16 OBSERVATION_PREPARATION_EXECUTION ...... Segue preparação; nada executa.
17 CREDENTIAL_AND_SECRET_BOUNDARY ......... Nenhum campo textual novo; o valor
     é enum fechado.
18 FAILURE_ROLLBACK_AND_CONCURRENCY ....... Sem escrita, nada a reverter.
19 CURRENT_CAPABILITY_NOT_OVERSTATED ...... §9: distinguibilidade aqui,
     invalidação deferida. PROTECTED não é bloqueio.
20 FROZEN_MODULES_UNCHANGED ............... cognitive be407b46 byte a byte;
     alembic sem alteração.
```

### 10.2 `SOPHIA_UX_COMPATIBILITY` — 17 linhas

```text
 1 USER_AUTHORITY_PRESERVED ............... SIM.
 2 SCHEDULE_MODE_DECLARED ................. NOT_APPLICABLE.
 3 AUTOMATION_SCOPE_DECLARED .............. NENHUMA.
 4 PERSISTENCE_BEHAVIOR_DECLARED .......... NENHUMA.
 5 PROVIDER_NEUTRALITY_PRESERVED .......... SIM.
 6 PERSONALIZATION_REVERSIBLE ............. NOT_APPLICABLE. Retirar proteção é
     decisão do usuário e NÃO é efeito colateral de proposta destrutiva.
 7 CONCURRENT_WORK_ISOLATION_DECLARED ..... Inalterado.
 8 BACKGROUND_EXECUTION_AUTHORIZATION ..... NOT_APPLICABLE.
 9 RESOURCE_LIMITS_AND_QUEUE_DECLARED ..... NOT_APPLICABLE.
10 AI_ROLE_CONTROL_DECLARED ............... NOT_APPLICABLE.
11 ROLE_AND_STEP_INSTRUCTION .............. NOT_APPLICABLE.
12 PIA_SEQUENCE_SUGGESTION_BEHAVIOR ....... REFORÇADO: legado fora de sugestão
     automática de limpeza.
13 MULTI_AI_RESULT_ATTRIBUTION ............ NOT_APPLICABLE.
14 PIA_INTEGRATION_DIVERGENCE_PRESERVATION  NOT_APPLICABLE.
15 POST_RESULT_USER_COMMAND_DECLARED ...... A confirmação passa a incluir o
     estado apresentado.
16 RESULT_APPROVAL_AND_PERSISTENCE ........ Distinguidos; nada persiste.
17 FROZEN_MODULES_UNCHANGED ............... SIM.
```

### 10.3 Multicanal v1.3 — 10 marcadores

```text
 1 INPUT_CHANNELS_DECLARED ................ TEXT | VOICE, inalterado.
 2 COMMAND_ENVELOPE_DECLARED .............. O lote do envelope passa a carregar
     o estado; envelope preserva a proposta exata (u135).
 3 CHANNEL_NORMALIZATION_DECLARED ......... NOT_APPLICABLE.
 4 IDENTITY_CONTEXT_AND_SCOPE_DECLARED .... Inalterado. Proteção NÃO é prova de
     identidade nem de titularidade legal.
 5 VOICE_CONFIDENCE_AND_CORRECTION ........ Inalterado.
 6 CONFIRMATION_POLICY_DECLARED ........... REFORÇADO: mudança em qualquer
     direção invalida.
 7 DESTRUCTIVE_INTENT_BINDING_DECLARED .... REFORÇADO; é o objeto da fatia.
 8 GOVERNANCE_PARITY_ACROSS_CHANNELS ...... SIM — u138 parametriza canal × estado.
 9 AUDIT_AND_RECEIPT_DECLARED ............. NOT_APPLICABLE.
10 CURRENT_CAPABILITY_NOT_OVERSTATED ...... SIM — §9.
```

### 10.4 Parte II §12

**Oito obrigações:** diretriz citada; implementado nos §4–§5; diferidos no §9;
estágios separados, e esta fatia é só preparação; autoridade competente é o
usuário, e a proteção é escolha dele; sem escrita não há rollback; compatibilidade
E3/E4 por regressão delta zero, com a exceção declarada das duas contagens
afetadas pela assinatura; Stop Condition assumida — e de fato **exercida** no
preflight da E4.9.9.a, que originou esta fatia.

**Onze Stop Conditions mínimas:** nenhuma disparou. Sem entidade persistente
ou migração; sem ownership; sem credenciais; sem execução externa; **sem
ampliação de autoridade** — o campo apenas restringe; sem assinatura de
provedor; sem sincronização; proveniência preservada; sem Schedule; sem
rollback declarado; congelados intocados.

**Onze provas mínimas:** `PROVADAS` — nenhuma chamada externa, nenhum acesso
fora do escopo, nenhuma escrita, preservação de origem e ordem do lote (`u133`),
isolamento entre workspaces. `NOT_APPLICABLE` — aprovação prévia, rollback,
concorrência, recibo, cancelamento. `DEFERRED` — estado obsoleto, que é
precisamente o que a E4.9.9.d fechará usando este campo.

### 10.5 Parte III §13

```text
1 cria distinção?         SIM — protegido vs. não protegido passa a ser
                          distinguível e vinculável. É o objetivo.
2 transforma distinção?   NÃO
3 compara distinções?     NÃO — compara contexto declarado, não patrimônio
4 muda acessibilidade?    NÃO
5 afeta persistência?     NÃO — PERSISTENCE_DELTA = 0
6 altera proveniência?    NÃO — canal, origem e ordem preservados
7 altera história causal? NÃO — CausalHistory intocada
```

### 10.6 E5 / COUT-P

`E4_INTEGRATION_OF_COUT_P = FORBIDDEN` respeitado. Nenhum score, escalarização
ou dependência.

---

## 11. Gates medidos

```text
COLLECTED        3487                                  (cadeia 87: 3420)
FULL_SUITE       3486 passed / 1 skipped / 0 failed    (cadeia 87: 3419/1/0)
RAW_SUITE        3019 passed / 468 skipped / 0 failed  (cadeia 87: 2952/468/0)
GLOBAL_COVERAGE  99,30%   — subiu (cadeia 87: 99,29%)
  target_resolution_enums.py    36/36   100%
  erasure_target.py           202/202   100%
  destructive_approval.py     249/249   100%
RUFF PASS   BLACK PASS (391)
MYPY app    7 históricos, NEW = 0
supressões / cast / Any novos: 0
ALEMBIC heads = current = c8a3f5017e94   ·   backend/alembic sem alteração
COGNITIVE_TREE be407b46f679a009e0f7f7e9f01fb784f08dea54  byte a byte
git diff --check CLEAN
```

**Regressões — onze seletores em delta zero:**

```text
E3 = 732 · E4.1 = 40 · E4.2 = 42 · E4.3 = 255 · E4.4 = 74 · E4.5 = 187
E4.6 = 275 · E4.7 = 240 · E4.8 = 146 · E4.9.5 = 113 · E4.9.6 = 309
```

**Dois seletores afetados pela assinatura, declarados:**

```text
E4.9.7   285 -> 320   (+35: u110–u122 e s31–s38, s99_9–s99_11)
E4.9.8   266 -> 298   (+32: u123–u138 e s17_1)
```

Suítes da fatia executadas **três vezes** com resultado idêntico: 618 testes.

---

## 12. Riscos e limites

**(a) O campo é obrigatório, mas ninguém o preenche ainda.** Não há resolvedor
concreto; quem construir o descritor declara o estado. Enquanto não existir
fronteira que o observe, o valor depende inteiramente de quem chama — e é por
isso que `LEGACY_PROTECTION_STATE_UNRESOLVED` existe.

**(b) Nada impede um chamador de declarar `NOT_PROTECTED` incorretamente.** O
contrato exige que ele **declare**; não verifica o mundo. Mesma estrutura de
`VerifiedDeletionCapability.verified`, e a mesma razão de a E4.9.1 exigir
adaptador autorizado.

**(c) A invalidação efetiva não existe.** Distinguibilidade não é recusa de
execução. `DEFERRED_TO_E4_9_9_D`, declarado no código e aqui.

**(d) `PROTECTED` não bloqueia.** Se a regra de produto exigir desbloqueio
separado ou confirmação reforçada, é autorização própria com integração de UX
que este corretivo não possui.

**(e) Dois instrumentos históricos ficaram semanticamente incompatíveis.**
Preservados byte a byte e **não** usados como prova na cadeia 88. Qualquer
relatório futuro que diga "seis congelados nos dois lados" estará errado.

---

## 13. Estado

```text
PATCH_CHAIN = 88
MIGRATION_HEAD = c8a3f5017e94 (INALTERADO)
E4_9_8_3_IMPLEMENTATION = COMPLETE_CANDIDATE
LEGACY_PROTECTION_BINDING = IMPLEMENTED_CANDIDATE
E4_9_9_A = STILL_BLOCKED_PENDING_PASS_FINAL
E4_9_9_B = NOT_STARTED   E4_9_9_C = NOT_STARTED   E4_9_9_D = NOT_STARTED
E4_10 = NOT_STARTED
APPROVAL_PERSISTENCE = NONE     ERASURE_EFFECT = NONE
AUTHENTICATOR = NONE            PRODUCT_DESTRUCTIVE_EXECUTION = NOT_AVAILABLE
```

Esta fatia **não** implementa proteção persistente, UI, executor ou efeito.
`PASS_FINAL` pertence à auditoria independente.
