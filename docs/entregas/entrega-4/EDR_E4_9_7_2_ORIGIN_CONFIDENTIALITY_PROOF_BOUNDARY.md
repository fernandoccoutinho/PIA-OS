# EDR E4.9.7.2 — Origem tipada, confidencialidade e fronteira de prova do alvo exato

**Natureza:** corretivo confinado dos cinco achados da auditoria independente da
E4.9.7.1. Não é fatia funcional nova.
**Baseline:** cadeia 81 (`2bd33e31`), `E4_9_7_1_AUDIT = FAIL_CORRECTIVE_REQUIRED`.

```text
ORIGIN = CLOSED_TYPED_PROVENANCE
OPAQUE_REFERENCE = REQUIRED_SENSITIVE_INPUT
REQUIRED_SENSITIVE_INPUT = REDACTED_FROM_REPR_AND_STR
REDACTION != SECRET_FREE_OBJECT
RAW_PATTERN_SYNTAX_REJECTION != MATERIAL_TARGET_CARDINALITY_PROOF
```

```text
A3C_TYPED_ORIGIN = FIXED
A3D_OPAQUE_REFERENCE_REDACTION = FIXED
A1_PROOF_BOUNDARY = ALIGNED
A2_REMAINING_CLAIMS = CORRECTED
MIGRATION_DELTA = 0   DATABASE_SCHEMA_DELTA = 0   E3_DELTA = 0
EFFECT_DELTA = 0      ERASURE_RECORD_WRITER_DELTA = 0   API_DELTA = 0
```

---

## 1. Causa raiz

### 1.1 O padrão, dito antes das causas individuais

A E4.9.7.1 fechou `diagnostic: str | None` e eu escrevi que a confidencialidade
estava imposta. **Havia um segundo campo de texto livre no mesmo objeto**, e eu
não o inventariei antes de fazer a afirmação.

É a quinta vez seguida que uma alegação minha é mais forte que a prova —
E4.9.6.1, .2, .3, E4.9.7 e E4.9.7.1. E é a segunda vez que o defeito é
exatamente o mesmo tipo de campo, num objeto que eu tinha acabado de auditar.

A diferença agora não é ter aplicado a §15.2 do Master — eu apliquei na cadeia
81, e ainda assim errei. O que faltou foi o passo anterior: **enumerar todos os
campos da classe antes de classificar a garantia**. Uma tabela por camada
preenchida sobre um inventário incompleto herda a incompletude.

Por isso este corretivo entrega o inventário do §3, e a guarda `s24` o congela:
qualquer campo `str` novo em qualquer contrato da fatia derruba o teste e
obriga a decidir explicitamente se é canal de confidencialidade.

### 1.2 A3c — `origin` era o novo canal livre

```text
INTENDED_FIELD_NAME != ENFORCED_FIELD_NAME
REQUEST_DATA != SAFE_DATA
FREE_TEXT_ORIGIN = CONFIDENTIALITY_CHANNEL
```

O nome do campo dizia "origem"; o tipo aceitava qualquer texto. Medido na
cadeia 81: o localizador entrava numa recusa e o `repr` o revelava; uma URL
assinada entrava na referência e no descritor.

Pior: `s19` **isentava `origin` explicitamente**, com a justificativa de que era
"dado do pedido, não contexto que o resolvedor compõe". A intenção era
defensável; a garantia não existia. Intenção de nome não vale como garantia de
tipo.

### 1.3 A3d — `opaque_reference` era tratada como segura para representação

Este campo é **entrada necessária** à resolução e pode conter material sensível
legado — uma URL assinada gravada há anos em `source_ref` é referência legítima
da E3. O erro não foi aceitá-la; foi expô-la na representação padrão.

### 1.4 A1 — a alegação era mais forte que a camada

`validar_localizador_exato` recusava sintaxe literal de expansão e o EDR a
apresentava como prova de que um descritor representa um alvo material exato.
Não é. `s3://bucket/%2A`, `s3://bucket/%5Ba-z%5D` e `regex://bucket/.+` são
aceitos, e se são expansão depende do adaptador que os interpretar — adaptador
que não existe.

---

## 2. Baseline e caracterizações

```text
HEAD 2bd33e314750b72071f197273b6d1d515216cf1a
PARENT 075f2651…  TREE 434dd8a3…  PATCH_ID 59f456a8…  PATCH_CHAIN 81
MIGRATION_HEAD c8a3f5017e94   árvore limpa   82 commits
app/cognitive  be407b46f679a009e0f7f7e9f01fb784f08dea54
backend/alembic cc68c3e274f388bda2a8674d6432d515bb8cbc4a
```

Os **dois** scripts externos, byte a byte inalterados:

```text
cadeia 81:  4971 → 0/8  EXIT=1        4972 → 5/5  EXIT=0
cadeia 82:  4971 → 0/8  EXIT=1        4972 → 0/5  EXIT=1
stderr = 0 bytes nos quatro casos — nenhum traceback
```

---

## 3. Inventário obrigatório de todos os campos textuais

Exigido pelo §3.3, e a razão pela qual o A3c passou despercebido na cadeia 81.

| Campo | Papel semântico | Pode conter valor sensível | Armazenamento | `repr`/`str` | Camada da garantia |
|---|---|---|---|---|---|
| `ControlScope.control_principal_ref` | referência opaca ao principal de controle | improvável, mas não impedido | nenhum | visível | `APPLICATION_LEVEL` (texto opaco validado) |
| `CustodyNamespace.provider` | onde o conteúdo vive | não | nenhum | visível | `APPLICATION_LEVEL` |
| `CustodyNamespace.namespace` | idem | não | nenhum | visível | `APPLICATION_LEVEL` |
| `VerifiedDeletionCapability.operation` | o que a conta pode | não | nenhum | visível | `APPLICATION_LEVEL` |
| `VerifiedDeletionCapability.scope` | escopo autorizado, legitimamente um **conjunto** | não | nenhum | visível | `APPLICATION_LEVEL` |
| `ErasureTargetReference.opaque_reference` | **entrada necessária** à resolução | **sim** — referência legada da E3 | nenhum | **redigido** | `APPLICATION_LEVEL` (redação), conteúdo `DEFERRED` |
| `origin` **antes** (cadeia 81) | proveniência | **sim** — era texto livre | nenhum | visível | **nenhuma** — era o defeito |
| `origin` **depois** | proveniência | **não** — vocabulário fechado | nenhum | visível | `APPLICATION_LEVEL` (tipo) |
| `ErasureTargetDescriptor.transient_locator` | endereça o objeto | **sim** | nenhum | **redigido** | `APPLICATION_LEVEL` (redação + recusa estrutural) |
| `ErasureTargetDescriptor.version_etag` | detecta resolução obsoleta | não | nenhum | visível | `APPLICATION_LEVEL` |

**Resultado do inventário:** exatamente **dois** campos podem transportar
material sensível — `opaque_reference` e `transient_locator`. Ambos têm
`repr=False` na dataclass **e** `__repr__`/`__str__` próprios, e `s25` fixa as
duas camadas.

Nenhum outro canal equivalente e diretamente explorável foi encontrado. Se
tivesse sido, o §3.3 manda parar em Stop Condition antes de expandir escopo, e
eu o teria feito.

---

## 4. A3c — origem tipada

### 4.1 O vocabulário veio do repositório, não da documentação

O §3.1.3 exige confirmar os nomes reais antes de congelar. Medido em
`app/cognitive/models/`:

```text
causal_history.py:153        payload_ref     Mapped[str | None]  String(512)
provenance_record.py:105     source_ref      Mapped[str | None]  String(512)
provenance_record.py:156     evidence_refs   Mapped[list[str]]   JSON
transformation_record.py:82  input_refs      Mapped[list[str]]   JSON
transformation_record.py:85  output_refs     Mapped[list[str]]   JSON
```

Os cinco existem e são exatamente os autorizados pela E4.9.1. `s26` reabre os
três arquivos da E3 e falha se algum nome sumir — **sem tocar** na E3.

### 4.2 O desenho

`ReferenceProvenance`, dataclass congelada:

```text
origin: ReferenceOrigin           enum fechado, cinco membros, sem genérico
position: int | None = None       inteiro tipado e SEPARADO
```

`position` existe porque três das cinco origens são listas JSON. É inteiro, não
string: `evidence_refs[3]` codificado em texto reabriria o canal livre pela
porta dos fundos, e o §3.1.5 proíbe exatamente isso.

`ORIGENS_PLURAIS` fixa quais admitem posição. `payload_ref` e `source_ref` são
colunas escalares na E3 — uma posição ali não significaria nada, e aceitá-la
faria o contrato dizer algo que a E3 não sustenta.

### 4.3 Alternativas rejeitadas

| # | Alternativa | Por que |
|---|---|---|
| 1 | redigir `origin` no `repr` | repetiria o defeito da cadeia 80: o valor continuaria dentro do objeto e poderia ser propagado de referência para recusa |
| 2 | validar `origin` contra os cinco nomes como string | o tipo continuaria `str`, e `s19`/`s23` não teriam o que provar; `dataclasses.fields` continuaria dizendo `str` |
| 3 | só o enum, sem `position` | perderia rastreabilidade em `evidence_refs`, `input_refs` e `output_refs`, que são listas |
| 4 | `origin: str` com regex | é a "lista finita apresentada como prova" que a auditoria recusou |
| **5** | **enum fechado + value object com posição tipada** | **adotada** |

### 4.4 Compatibilidade pública

```text
BREAKING_CHANGE = origin: str → origin: ReferenceProvenance
AFFECTED_VALUE_OBJECTS = ErasureTargetReference, ErasureTargetDescriptor,
                         TargetResolutionRefusal
CONSUMERS_IMPACTED = 0
```

Verificado: nenhum consumidor runtime da porta existe (`s10`). O §5 do prompt é
explícito — não manter API insegura por compatibilidade com zero consumidores.

---

## 5. A3d — referência opaca

`opaque_reference` **não** podia virar enum: sem ela não há o que resolver.
Recebeu `field(repr=False)` mais `__repr__`/`__str__` próprios em
`ErasureTargetReference`.

```text
valor acessível a quem resolve        u85
ausente de repr/str/f-string          u84
não copiado para recusa               u86 — a recusa não tem o campo
objeto declarado como portador        u87 — a docstring diz REDACTION !=
de entrada sensível, não livre             SECRET_FREE_OBJECT
```

A assimetria com `origin` é deliberada e é o ponto: ocultar a representação é
correto para um valor **necessário**; seria errado para um campo que não
precisa transportar conteúdo arbitrário.

---

## 6. A1 — alinhar prova e alegação

Adotada a **opção preferida** do §3.4: defesa lexical, exatidão material
deferida.

A função foi renomeada de `validar_localizador_exato` para
`validar_localizador_sem_expansao_literal`. **A renomeação é a correção**, não
cosmética: o nome antigo prometia o que nenhuma camada sem adaptador pode
provar.

```text
RAW_PATTERN_SYNTAX_REJECTION = IMPLEMENTED       APPLICATION_LEVEL
MATERIAL_EXACT_TARGET_PROOF = DEFERRED           adaptador + prova de efeito
```

### 6.1 Consequência declarada na caracterização

O script `reproduce_e4972_defects.py` busca o nome antigo por `getattr` e, não
o encontrando, imprime:

```text
A1_PERCENT_ENCODED_WILDCARD=VALIDATOR_NOT_PRESENT
A1_PERCENT_ENCODED_CLASS=VALIDATOR_NOT_PRESENT
A1_REGEX_LIKE_LOCATOR=VALIDATOR_NOT_PRESENT
```

Publico o resultado literal **e** a medição equivalente pelo nome novo, para
que a renomeação não esconda a observação:

```text
validar_localizador_sem_expansao_literal("transient_locator", "s3://bucket/%2A")
  → ACCEPTED
validar_localizador_sem_expansao_literal("transient_locator", "s3://bucket/%5Ba-z%5D")
  → ACCEPTED
validar_localizador_sem_expansao_literal("transient_locator", "regex://bucket/.+")
  → ACCEPTED
```

Os três continuam **aceitos**, e é deliberado.

### 6.2 Limites declarados

- **Percent-encoding não é decodificado.** `unquote` não é aplicado.
  Decodificar seria interpretar a string em nome de um adaptador que não existe,
  e a interpretação varia por provedor. Aplicar `unquote` trocaria um limite
  declarado por normalização silenciosa, vedada pelo §3.4.1.
- **Scheme desconhecido não é rejeitado.** `regex://`, `glob://` e outros passam
  se a forma literal for limpa. Rejeitar por lista de schemes quebraria a
  neutralidade de provedor e criaria a lista finita que a auditoria recusou.
- **Custo registrado:** um objeto legítimo cujo nome contenha `[`, `{` ou `?` é
  recusado. Recusa conservadora — aceitar por engano designa alvo errado.
- `capability.scope` continua podendo representar conjunto autorizado
  (`u91`), e permanece distinto do localizador de um objeto.

`u90` prova na AST que nenhuma decodificação silenciosa entrou.

---

## 7. A2 — alegações remanescentes corrigidas

```text
CONTRACT_AND_FAKE_ISOLATION_PROOF = IMPLEMENTED
EXTERNAL_RUNTIME_CROSS_TENANT_CLOSURE = DEFERRED
CREDENTIAL_CONFUSION_RUNTIME_CLOSURE = DEFERRED
TARGET_RESOLVER_ADAPTER = NONE
```

| Onde | Antes | Depois |
|---|---|---|
| `CONTROL_SCOPE_MISMATCH` | "Fecha o *cross-tenant*" | "Endereça… fechamento em runtime externo pertence ao adaptador" |
| `CustodyNamespace` | "fecham a *credential confusion*" | "endereçam… nada valida a credencial, porque não há conector" |
| `u35` | "Fecha o cross-tenant no comportamento" | "Prova CONTRATUAL de isolamento, não fechamento em runtime externo" |
| `s22` | "o escopo continua fechado" | "nenhuma capacidade nova entrou" |

Os cinco testes comportamentais do dublê foram preservados. `s27` faz busca
semântica pelas formulações antigas — e ler o texto bruto é correto ali, porque
o alvo **é** o texto das docstrings, não o código executável.

O relato histórico do EDR da cadeia 81 não foi apagado: este documento acrescenta
a resolução.

---

## 8. Evidência antes/depois

| Evidência | Cadeia 81 | Cadeia 82 | Regressão |
|---|---|---|---|
| `A3_REFUSAL_ORIGIN_LOCATOR_ACCEPTED` | aceito | `TypeError` | `u72` |
| `A3_REFUSAL_ORIGIN_REPR_LEAK` | vazava | inconstruível | `u83` |
| `A3_REFERENCE_ORIGIN_SECRET_ACCEPTED` | aceito | `TypeError` | `u70` |
| `A3_DESCRIPTOR_ORIGIN_SECRET_ACCEPTED` | aceito | `TypeError` | `u71` |
| `A3_OPAQUE_REFERENCE_REPR_LEAK` | vazava | redigido | `u84` |

---

## 9. Conformidade documental — quatro camadas (Master v2.3)

### 9.1 `PIA_OS_SOPHIA_MASTER_COMPATIBILITY` — 20 linhas

```text
├── USER_AUTHORITY_PRESERVED ................ SIM. Corretivo só restringe.
├── SOPHIA_BRAND_PIA_OS_CODEBASE_PRESERVED .. SIM.
├── MODULE_SCOPE_AND_DEFERRED_CAPABILITIES ... Escopo: origem tipada, redação
│     da referência, alinhamento de A1/A2. Diferidos: adaptador, efeito, E4.9.8.
├── SCHEDULE_MODE_DECLARED ................... NOT_APPLICABLE — corrective only.
├── AI_ROLE_AND_STEP_INSTRUCTION_DISTINGUISHED NOT_APPLICABLE.
├── PROVIDER_CONNECTION_METHOD_DECLARED ...... NOT_APPLICABLE — nenhum conector.
├── AUTOMATION_SCOPE_DECLARED ................ NENHUMA (`s15`, `s22`).
├── APPROVAL_GATES_DECLARED .................. NOT_APPLICABLE.
├── PERSISTENCE_BEHAVIOR_DECLARED ............ NENHUMA.
├── MULTI_AI_RESULT_ATTRIBUTION_DECLARED ..... NOT_APPLICABLE.
├── DIVERGENCE_PRESERVATION_DECLARED ......... SIM — sem normalização; `unquote`
│     ausente e provado por AST (`u90`).
├── CONCURRENT_WORK_ISOLATION_DECLARED ....... Contratual, com fechamento
│     externo DEFERIDO — §7.
├── BACKGROUND_EXECUTION_AUTHORIZATION ....... NOT_APPLICABLE.
├── RESOURCE_LIMITS_QUEUE_AND_COST_DECLARED .. NOT_APPLICABLE.
├── REMOTE_RESOURCE_SCOPE_DECLARED ........... NENHUM acesso remoto.
├── OBSERVATION_PREPARATION_EXECUTION ........ Continua só OBSERVAÇÃO.
├── CREDENTIAL_AND_SECRET_BOUNDARY_DECLARED .. REFORÇADO — §3 e §5.
├── FAILURE_ROLLBACK_AND_CONCURRENCY ......... Sem escrita, nada a reverter.
├── CURRENT_CAPABILITY_NOT_OVERSTATED ........ §3 inventaria, §6 rebaixa a
│     alegação A1, §7 rebaixa as de A2.
└── FROZEN_MODULES_UNCHANGED ................. cognitive e alembic idênticos.
```

### 9.2 `SOPHIA_UX_COMPATIBILITY` — 17 linhas

```text
├── USER_AUTHORITY_PRESERVED ................. SIM.
├── SCHEDULE_MODE_DECLARED ................... NOT_APPLICABLE.
├── AUTOMATION_SCOPE_DECLARED ................ NENHUMA.
├── PERSISTENCE_BEHAVIOR_DECLARED ............ NENHUMA.
├── PROVIDER_NEUTRALITY_PRESERVED ............ REFORÇADO — scheme desconhecido
│     não é rejeitado por lista; §6.2.
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

### 9.3 `MULTICHANNEL_COMMAND_COMPATIBILITY_v1_3` — 10 marcadores

```text
├── INPUT_CHANNELS_DECLARED ................. TEXT | VOICE, ambos futuros.
├── COMMAND_ENVELOPE_DECLARED ............... Contratos utilizáveis pelo
│     envelope futuro; o envelope é da E4.9.8 e NÃO foi criado.
├── CHANNEL_NORMALIZATION_DECLARED .......... NOT_APPLICABLE — e vale notar
│     que nenhuma normalização existe nem aqui nem no localizador.
├── IDENTITY_CONTEXT_AND_SCOPE_DECLARED ..... PARCIAL, declarado: os campos de
│     `ControlScope` são declarados pela fronteira, não autenticados.
├── VOICE_CONFIDENCE_AND_CORRECTION ......... NOT_APPLICABLE.
├── CONFIRMATION_POLICY_DECLARED ............ NOT_APPLICABLE.
├── DESTRUCTIVE_INTENT_BINDING_DECLARED ..... PARCIAL e rebaixado: a recusa
│     literal de expansão é APPLICATION_LEVEL; cardinalidade material é
│     DEFERRED ao adaptador — §6.
├── GOVERNANCE_PARITY_ACROSS_CHANNELS ....... SIM — origem continua sem virar
│     autoridade (`u82`), agora com tipo fechado.
├── AUDIT_AND_RECEIPT_DECLARED .............. NOT_APPLICABLE — sem recibo. E o
│     localizador segue proibido no `ErasureRecord` futuro.
└── CURRENT_CAPABILITY_NOT_OVERSTATED ....... SIM — §3, §6 e §7.
```

### 9.4 Parte II §12 — 8 obrigações, 11 Stop Conditions, 11 provas

**Oito obrigações:** cumpridas — diretriz citada; implementado nos §4–§7;
diferido no §11; observação/preparação/aprovação/execução separadas, só a
primeira existe; autoridade é o usuário; sem escrita não há rollback e VOs
imutáveis não têm concorrência; compatibilidade com E3/E4 por regressão delta
zero; nenhuma Stop Condition disparou.

**Onze Stop Conditions mínimas:** nenhuma disparou. Em particular, `ORIGIN`
descreve fonte existente e **não** altera ownership, e a E3 não foi tocada —
`s26` a lê para verificar, sem modificar.

**Onze provas mínimas:** PROVADAS — nenhuma chamada externa (`s04`, `u69`),
nenhum acesso fora do escopo (`u62`–`u66`), nenhuma escrita durante observação
(`u69`), preservação de origem e versão (`u74`, `u82`), isolamento entre
Workspaces (`u62`). `NOT_APPLICABLE` — aprovação prévia, rollback,
concorrência determinística, recibo fiel, cancelamento. `DEFERRED` — estado
obsoleto.

### 9.5 Checklist de impacto sobre distinções (Parte III §13)

```text
1. cria distinção?          NÃO — restringe VOs existentes
2. transforma distinção?    NÃO
3. compara distinções?      NÃO
4. muda acessibilidade?     NÃO
5. afeta persistência?      NÃO — zero ORM, zero migração
6. altera proveniência?     NÃO — TIPA a proveniência já existente; os cinco
                            campos da E3 continuam intocados
7. altera história causal?  NÃO
```

---

## 10. Gates medidos

Clone limpo, PostgreSQL recriado e **pré-migrado**:

```text
COLLECTED        3115                                   (cadeia 81: 3048)
FULL_SUITE       3114 passed / 1 skipped / 0 failed     (cadeia 81: 3047/1/0)
RAW_SUITE        2647 passed / 468 skipped / 0 failed   (cadeia 81: 2580/468/0)
GLOBAL_COVERAGE  99,26%   — não caiu
  target_resolution_enums.py   100%
  schemas/erasure_target.py    100%
  ports/erasure_target.py      100%
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

E4.9.7: **179 → 246** (218 unitários + 28 estáticos), três execuções idênticas.

### 10.1 Uma fronteira descoberta pela exigência de 100%

`ReferenceProvenance.__post_init__` recusava `origin` de tipo errado, e nenhum
teste tocava essa linha — todos passavam pelos três value objects que a
embrulham. Fechada com `u92`. Não era linha morta: sem ela, o vocabulário
fechado dependeria de quem constrói o value object externo.

---

## 11. Arquivos alterados

```text
app/memory/models/target_resolution_enums.py   + ReferenceOrigin, ORIGENS_PLURAIS
                                               docstring de CONTROL_SCOPE_MISMATCH
app/memory/schemas/erasure_target.py           + ReferenceProvenance, REFERENCIA_OCULTA
                                               origin: str → ReferenceProvenance ×3
                                               opaque_reference redigida + __repr__
                                               validador renomeado
                                               docstring de CustodyNamespace
tests/unit/memory/test_erasure_target.py       +27 funções, 1 atualizada (u35)
tests/static/test_erasure_target_isolation.py  +6, 3 atualizadas (s13, s19, s22)
docs/.../EDR_E4_9_7_2_...md                    novo
```

`ports/erasure_target.py` não precisou mudar.

### 11.1 Três guardas minhas envelheceram

- **`s13`** fixava 6 classes; `ReferenceProvenance` fez sete.
- **`s19`** isentava `origin` por ser "dado do pedido" — a isenção era o
  defeito. Agora exige que a recusa não tenha **nenhum** campo `str`.
- **`s22`** dizia "o escopo continua fechado", formulação que se confundia com
  o fechamento de cross-tenant.

Nenhuma por regressão: as três diziam algo que deixou de ser verdade, ou que
nunca deveria ter sido afirmado.

---

## 12. Riscos que declaro

**(a) A quinta alegação excessiva foi sobre um campo que eu tinha acabado de
auditar.** O inventário do §3 e a guarda `s24` são a contramedida estrutural. Se
voltar a acontecer **com o inventário no lugar**, o problema não é disciplina de
escrita — é que a classificação por camada está sendo preenchida como
formalidade.

**(b) `control_principal_ref` é o campo textual mais próximo do limite.** É
referência opaca ao principal, e nada impede um chamador de pôr algo sensível
ali. Não o tipei porque o §3.3 proíbe ampliar automaticamente o corretivo, e
porque ele não é diretamente explorável como os dois anteriores — não é
localizador nem entra em recusa. Fica registrado como o próximo candidato caso
a auditoria discorde.

**(c) A recusa conservadora do localizador tem custo.** Declarado no §6.2.

**(d) `%2A` continua aceito.** Deliberado e declarado. Se um adaptador futuro
decodificar percent-encoding, a exatidão material passa a depender dele — que é
exatamente o que `MATERIAL_EXACT_TARGET_PROOF = DEFERRED` diz.

**(e) A prova de isolamento continua contratual.** Um adaptador real que ignore
`ControlScope` satisfaz o `Protocol`.

---

## 13. Estado

```text
PATCH_CHAIN = 82
MIGRATION_HEAD = c8a3f5017e94 (INALTERADO)
E4_9_7_2_IMPLEMENTATION = COMPLETE_CANDIDATE
E4_9_7 = AWAITING_INDEPENDENT_REAUDIT
A3C = FIXED   A3D = FIXED   A1 = ALIGNED   A2 = CORRECTED
TARGET_RESOLVER_ADAPTER = NONE
ERASURE_EFFECT = NONE
ERASURE_RECORD_WRITER = NOT_COMPOSED
E4_9_READY = FALSE
E4_9_8 = NOT_STARTED
```

Não existe adaptador, não existe efeito, e a E4.9.8 não foi iniciada.
`PASS_FINAL` pertence à auditoria independente.
