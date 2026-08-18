# EDR E4.9.7.3 — Inventário textual e confidencialidade composta

**Natureza:** corretivo confinado do achado A5 da auditoria independente da
E4.9.7.2. Não é fatia funcional nova.
**Baseline:** cadeia 82 (`df310bbf`), `E4_9_7_2 = FAIL_CORRECTIVE_REQUIRED`.

```text
UNRESTRICTED_PUBLIC_STR = MAY_CONTAIN_SENSITIVE_VALUE
SEMANTIC_FIELD_NAME != ENFORCED_VALUE_DOMAIN
TEXT_VALIDATION     != NON_SENSITIVE_VALUE_PROOF
DIRECT_REDACTION    != COMPOSITE_REDACTION
INVENTORY_OF_NAMES  != CONFIDENTIALITY_PROOF
```

```text
A5_TEXTUAL_CONFIDENTIALITY_INVENTORY = FIXED
MIGRATION_DELTA = 0   DATABASE_SCHEMA_DELTA = 0   E3_DELTA = 0
EFFECT_DELTA = 0      ERASURE_RECORD_WRITER_DELTA = 0   API_DELTA = 0
```

---

## 1. Causa raiz

### 1.1 A frase falsa da cadeia 82

O §3 do EDR anterior declarou:

> **Resultado do inventário:** exatamente **dois** campos podem transportar
> material sensível — `opaque_reference` e `transient_locator`. […] Nenhum
> outro canal equivalente e diretamente explorável foi encontrado.

A auditoria mediu nove vazamentos com o mesmo marcador sensível. A frase era
falsa, e o teste `s25` a congelou como contrato.

O histórico não é apagado: o EDR da cadeia 82 permanece no repositório com a
afirmação original. Este documento acrescenta a resolução.

### 1.2 A agravante — eu identifiquei o risco e argumentei contra ele

O §12(b) do EDR da cadeia 82 diz, sobre `control_principal_ref`:

> Não o tipei […] porque ele não é diretamente explorável como os dois
> anteriores — não é localizador nem entra em recusa.

Isso era **falso em runtime**, e a auditoria o demonstrou em duas linhas: a
dataclass expõe o campo diretamente, e `ErasureTargetReference.__repr__` inclui
`control_scope!r`. Identificar um risco e depois descartá-lo com uma
justificativa que não foi testada é pior do que não o ter mencionado — a menção
dá aparência de diligência a uma conclusão não medida.

### 1.3 A regra que eu apliquei pela metade

A cadeia 82 estabeleceu `INTENDED_FIELD_NAME != ENFORCED_FIELD_NAME` e a
aplicou **somente** a `origin`. "Provider", "namespace", "operation", "scope" e
"principal" são exatamente a mesma coisa: nomes que descrevem intenção sem
restringir o domínio de valores.

`validar_texto_opaco` recusa tipo errado, vazio, invisíveis Unicode e excesso de
tamanho. Nada disso prova que o valor não é sensível — uma URL assinada passa
por todas essas checagens.

```text
TEXT_VALIDATION != NON_SENSITIVE_VALUE_PROOF
```

### 1.4 Por que o inventário da cadeia 82 não pegou

`s24` inventaria **nomes e tipos**. `s25` protegia **dois campos**. Nenhum dos
dois exercitava conteúdo sensível nos demais canais — e por isso passavam.

```text
INVENTORY_OF_NAMES != CONFIDENTIALITY_PROOF
```

Uma guarda que não pode falhar não é guarda. A substituta do §5 exercita o
marcador real em cada canal, que é a única forma de ela poder falhar.

---

## 2. Baseline e caracterizações

```text
HEAD df310bbfc07f7b3156b17ed427422ad9f58a8463
PARENT 2bd33e31…  TREE 9e18d74c…  PATCH_ID 48dae1bf…  PATCH_CHAIN 82
MIGRATION_HEAD c8a3f5017e94   árvore limpa   83 commits
app/cognitive  be407b46f679a009e0f7f7e9f01fb784f08dea54
backend/alembic cc68c3e274f388bda2a8674d6432d515bb8cbc4a
```

Os **três** scripts externos, byte a byte inalterados:

```text
cadeia 82:  4971 → 0/8 EXIT=1   4972 → 0/5 EXIT=1   4973 → 9/9 EXIT=0
cadeia 83:  4971 → 0/8 EXIT=1   4972 → 0/5 EXIT=1   4973 → 0/9 EXIT=1
stderr = 0 bytes nas seis execuções
```

---

## 3. Inventário completo, por domínio executável

A coluna que decide é `ENFORCED_VALUE_DOMAIN` — o que o contrato **realmente**
aceita —, nunca o nome do campo.

| Campo | Domínio executável | Pode conter valor sensível | `repr`/`str` direto | Composto | Camada | Decisão |
|---|---|---|---|---|---|---|
| `ControlScope.control_principal_ref` | texto opaco arbitrário | **SIM** | redigido | redigido em `Reference` e `Descriptor` | `APPLICATION_LEVEL` | `REQUIRED_SENSITIVE_REDACTED` |
| `CustodyNamespace.provider` | texto opaco arbitrário | **SIM** | redigido | redigido nos dois | `APPLICATION_LEVEL` | `REQUIRED_SENSITIVE_REDACTED` |
| `CustodyNamespace.namespace` | texto opaco arbitrário | **SIM** | redigido | redigido nos dois | `APPLICATION_LEVEL` | `REQUIRED_SENSITIVE_REDACTED` |
| `VerifiedDeletionCapability.operation` | texto opaco arbitrário | **SIM** | redigido | redigido em `Descriptor` | `APPLICATION_LEVEL` | `REQUIRED_SENSITIVE_REDACTED` |
| `VerifiedDeletionCapability.scope` | texto opaco arbitrário, **conjunto legítimo** | **SIM** | redigido | redigido em `Descriptor` | `APPLICATION_LEVEL` | `REQUIRED_SENSITIVE_REDACTED` |
| `ErasureTargetReference.opaque_reference` | texto opaco arbitrário | **SIM** | redigido | — | `APPLICATION_LEVEL` | `REQUIRED_SENSITIVE_REDACTED` |
| `ErasureTargetDescriptor.transient_locator` | texto opaco **sem expansão literal, sem userinfo, sem query** | **SIM** (segredo no caminho) | redigido | — | `APPLICATION_LEVEL` + `DEFERRED` | `REQUIRED_SENSITIVE_REDACTED` |
| `ErasureTargetDescriptor.version_etag` | texto opaco arbitrário, opcional | **SIM** | redigido | — | `APPLICATION_LEVEL` | `REQUIRED_SENSITIVE_REDACTED` |
| `ReferenceProvenance.origin` | `ReferenceOrigin`, 5 membros | **NÃO** — tipo fechado | visível | visível | `APPLICATION_LEVEL` | `CLOSED_TYPED` |
| `ReferenceProvenance.position` | `int >= 0`, só origens plurais | **NÃO** — não é texto | visível | visível | `APPLICATION_LEVEL` | `CLOSED_TYPED` |
| `VerifiedDeletionCapability.verified` | `bool` estrito | **NÃO** — não é texto | visível | visível | `APPLICATION_LEVEL` | `CLOSED_TYPED` |

**Todo campo `str` público desta fatia é `REQUIRED_SENSITIVE_REDACTED`.** Não há
exceção, e a lista é derivada por reflexão em `s25_1`, não escrita à mão.

`transient_locator` carrega duas camadas: a recusa estrutural de expansão,
userinfo e query é `APPLICATION_LEVEL`; segredo escondido **no caminho** segue
`DEFERRED`, como já declarado na cadeia 81.

---

## 4. Decisão de desenho

### 4.1 Redação, e por que não tipo fechado

| Alternativa | Por que foi rejeitada |
|---|---|
| enum de provedores | quebra `PROVIDER_NEUTRALITY_PRESERVED`; o §3.3 proíbe congelar provedores reais |
| gramática "identificador, não URL" para `provider`/`namespace` | inventaria regra que nenhum contrato sustenta — há provedores cujo namespace legítimo **é** uma URI; e seria a lista finita de caracteres que a auditoria da cadeia 81 já recusou |
| gramática para `scope` | transformaria capacidade em alvo exato, invertendo o contrato — `workspace/w1/*` tem de continuar legítimo |
| tipar `control_principal_ref` | ele referencia um principal externo cujo formato o PIA-OS não define; fechá-lo exigiria conhecer o IdP, que não existe |
| redigir só as composições | `DIRECT_REDACTION != COMPOSITE_REDACTION` vale nos dois sentidos: as classes internas são públicas e vazavam sozinhas |
| **redação uniforme, direta e composta** | **adotada** |

### 4.2 Duas camadas em cada classe

`field(repr=False)` **mais** `__repr__`/`__str__` próprios. A primeira é fácil de
apagar sem perceber; a segunda torna a redação visível no texto do módulo.
`s25_3` exige as duas.

### 4.3 O descritor extraía as strings internas

Este é o detalhe que teria feito uma correção parcial passar despercebida:

```text
cadeia 82:  f"provider={self.custody_namespace.provider!r}, "
            f"namespace={self.custody_namespace.namespace!r}, "
```

Redigir `CustodyNamespace` **não** teria corrigido o descritor, porque ele não
delegava — puxava os campos. Passou a delegar:
`custody_namespace={self.custody_namespace!r}`.

### 4.4 Redação não pode virar apagamento

`repr` continua mostrando classe, `subject_coid`, timestamp, proveniência e
`verified`. `u108` fixa isso, e o motivo é prático: uma representação inútil é
trocada por comodidade na primeira sessão de depuração difícil, e a proteção
morre por desuso.

---

## 5. Correção de `s25`

A guarda da cadeia 82 contava nomes e protegia dois campos — e passava
**porque não exercitava os demais**. Foi substituída por quatro:

```text
s25    marcador sensível real em 14 canais, diretos e compostos,
       em repr, str, f-string e format
s25_1  a lista de canais é derivada por REFLEXÃO — um campo `str` novo
       em qualquer contrato derruba a guarda até ser classificado
s25_2  os valores continuam acessíveis, iguais e imutáveis
s25_3  duas camadas de redação em cada classe
```

`transient_locator` não entra nas fábricas de `s25` porque o validador de
expansão literal **rejeita** a URL com userinfo e query — rejeição também é
fechamento, e `u53`/`u55` cobrem esse caminho.

---

## 6. Evidência antes/depois

| Evidência | Cadeia 82 | Cadeia 83 | Regressão |
|---|---|---|---|
| `A5_CONTROL_PRINCIPAL_DIRECT_REPR_LEAK` | vazava | redigido | `u93` |
| `A5_REFERENCE_NESTED_CONTROL_PRINCIPAL_REPR_LEAK` | vazava | redigido | `u97` |
| `A5_PROVIDER_DIRECT_REPR_LEAK` | vazava | redigido | `u94` |
| `A5_NAMESPACE_DIRECT_REPR_LEAK` | vazava | redigido | `u94` |
| `A5_REFERENCE_NESTED_NAMESPACE_REPR_LEAK` | vazava | redigido | `u98` |
| `A5_DESCRIPTOR_NESTED_PROVIDER_REPR_LEAK` | vazava | redigido | `u99` |
| `A5_DESCRIPTOR_NESTED_NAMESPACE_REPR_LEAK` | vazava | redigido | `u99` |
| `A5_OPERATION_DIRECT_REPR_LEAK` | vazava | redigido | `u95` |
| `A5_SCOPE_DIRECT_REPR_LEAK` | vazava | redigido | `u95` |
| `A5_VERSION_ETAG_DESCRIPTOR_REPR_LEAK` | já omitido | `repr=False` + redigido | `u96` |

Também coberto: `Descriptor→control_scope` (`u101`) e
`Descriptor→capability.*` (`u100`), que a auditoria não listou nominalmente mas
são a mesma composição.

---

## 7. O que NÃO mudou

```text
4971 = 0/8   4972 = 0/5                       correções anteriores intactas
ReferenceOrigin fechado nas cinco origens     inalterado
position inteira, não negativa, só plurais    inalterado
origin sem `str` livre nos três VOs           inalterado
MATERIAL_EXACT_TARGET_PROOF = DEFERRED        inalterado
percent-encoding e schemes desconhecidos      inalterados (u89)
capability.scope = "workspace/w1/*" legítimo  u106
EXTERNAL_RUNTIME_CROSS_TENANT_CLOSURE         segue DEFERRED
resultado discriminado sucesso | recusa       inalterado
imutabilidade, igualdade, timezone-aware      u104, u105
zero escrita, zero chamada externa            u69
```

Nenhum provedor foi congelado em enum (`u107`).

---

## 8. Conformidade documental — quatro camadas (Master v2.3)

### 8.1 `PIA_OS_SOPHIA_MASTER_COMPATIBILITY` — 20 linhas

```text
├── USER_AUTHORITY_PRESERVED ................ SIM. Corretivo só restringe
│     representação; nenhum poder novo.
├── SOPHIA_BRAND_PIA_OS_CODEBASE_PRESERVED .. SIM.
├── MODULE_SCOPE_AND_DEFERRED_CAPABILITIES ... Escopo: inventário textual e
│     redação direta/composta. Diferidos: adaptador, efeito, E4.9.8.
├── SCHEDULE_MODE_DECLARED ................... NOT_APPLICABLE — corrective only.
├── AI_ROLE_AND_STEP_INSTRUCTION_DISTINGUISHED NOT_APPLICABLE.
├── PROVIDER_CONNECTION_METHOD_DECLARED ...... NOT_APPLICABLE — nenhum conector.
├── AUTOMATION_SCOPE_DECLARED ................ NENHUMA.
├── APPROVAL_GATES_DECLARED .................. NOT_APPLICABLE.
├── PERSISTENCE_BEHAVIOR_DECLARED ............ NENHUMA — e a redação NÃO cria
│     persistência: nada é gravado, só omitido da representação.
├── MULTI_AI_RESULT_ATTRIBUTION_DECLARED ..... NOT_APPLICABLE.
├── DIVERGENCE_PRESERVATION_DECLARED ......... SIM — nenhuma normalização;
│     igualdade preservada byte a byte (`u104`).
├── CONCURRENT_WORK_ISOLATION_DECLARED ....... Contratual; externo DEFERIDO.
├── BACKGROUND_EXECUTION_AUTHORIZATION ....... NOT_APPLICABLE.
├── RESOURCE_LIMITS_QUEUE_AND_COST_DECLARED .. NOT_APPLICABLE.
├── REMOTE_RESOURCE_SCOPE_DECLARED ........... NENHUM acesso remoto.
├── OBSERVATION_PREPARATION_EXECUTION ........ Continua só OBSERVAÇÃO.
├── CREDENTIAL_AND_SECRET_BOUNDARY_DECLARED .. REFORÇADO — é o achado A5.
├── FAILURE_ROLLBACK_AND_CONCURRENCY ......... Sem escrita, nada a reverter.
├── CURRENT_CAPABILITY_NOT_OVERSTATED ........ §3 classifica TODO campo pelo
│     domínio executável; nenhuma alegação de "não sensível" sem prova.
└── FROZEN_MODULES_UNCHANGED ................. cognitive e alembic idênticos.
```

### 8.2 `SOPHIA_UX_COMPATIBILITY` — 17 linhas

```text
├── USER_AUTHORITY_PRESERVED ................. SIM.
├── SCHEDULE_MODE_DECLARED ................... NOT_APPLICABLE.
├── AUTOMATION_SCOPE_DECLARED ................ NENHUMA.
├── PERSISTENCE_BEHAVIOR_DECLARED ............ NENHUMA.
├── PROVIDER_NEUTRALITY_PRESERVED ............ REFORÇADO — a alternativa de
│     enum de provedores foi rejeitada por isto (`u107`).
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
├── CHANNEL_NORMALIZATION_DECLARED .......... NOT_APPLICABLE — e nenhuma
│     normalização foi introduzida em campo algum.
├── IDENTITY_CONTEXT_AND_SCOPE_DECLARED ..... PARCIAL e agora mais honesto:
│     `control_principal_ref` é declarado pela fronteira, não autenticado, E
│     é tratado como potencialmente sensível.
├── VOICE_CONFIDENCE_AND_CORRECTION ......... NOT_APPLICABLE.
├── CONFIRMATION_POLICY_DECLARED ............ NOT_APPLICABLE.
├── DESTRUCTIVE_INTENT_BINDING_DECLARED ..... Inalterado desde a cadeia 82:
│     recusa literal APPLICATION_LEVEL, cardinalidade material DEFERRED.
├── GOVERNANCE_PARITY_ACROSS_CHANNELS ....... SIM — nenhum campo de origem ou
│     de canal vira autoridade.
├── AUDIT_AND_RECEIPT_DECLARED .............. NOT_APPLICABLE — sem recibo. E o
│     §3 amplia a lista do que não pode entrar num recibo futuro.
└── CURRENT_CAPABILITY_NOT_OVERSTATED ....... SIM — §3.
```

### 8.4 Parte II §12 — 8 obrigações, 11 Stop Conditions, 11 provas

**Oito obrigações:** cumpridas — diretriz citada; implementado no §4; diferido
no §9; observação/preparação/aprovação/execução separadas, só a primeira
existe; autoridade é o usuário; sem escrita não há rollback e VOs imutáveis não
têm concorrência; compatibilidade com E3/E4 por regressão delta zero; nenhuma
Stop Condition disparou.

**Onze Stop Conditions mínimas:** nenhuma disparou. Em particular, nenhum campo
`str` livre permanece classificado como não sensível, e o marcador não aparece
em representação direta nem composta.

**Onze provas mínimas:** PROVADAS — nenhuma chamada externa (`s04`, `u69`),
nenhum acesso fora do escopo (`u62`–`u66`), nenhuma escrita durante observação
(`u69`), preservação de origem e versão (`u74`, `u103`), isolamento entre
Workspaces (`u62`). `NOT_APPLICABLE` — aprovação prévia, rollback, concorrência
determinística, recibo fiel, cancelamento. `DEFERRED` — estado obsoleto.

### 8.5 Checklist de impacto sobre distinções (Parte III §13)

```text
1. cria distinção?          NÃO
2. transforma distinção?    NÃO — valores preservados byte a byte
3. compara distinções?      NÃO
4. muda acessibilidade?     NÃO ao contrato; a REPRESENTAÇÃO passa a omitir
                            texto livre, e o valor segue acessível (u103)
5. afeta persistência?      NÃO — zero ORM, zero migração
6. altera proveniência?     NÃO
7. altera história causal?  NÃO
```

---

## 9. Gates medidos

Clone limpo, PostgreSQL recriado e **pré-migrado**:

```text
COLLECTED        3136                                  (cadeia 82: 3115)
FULL_SUITE       3135 passed / 1 skipped / 0 failed    (cadeia 82: 3114/1/0)
RAW_SUITE        2668 passed / 468 skipped / 0 failed  (cadeia 82: 2647/468/0)
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

E4.9.7: **246 → 267** (236 unitários + 31 estáticos), três execuções idênticas.

---

## 10. Arquivos alterados

```text
app/memory/schemas/erasure_target.py           + TEXTO_OCULTO
                                               ControlScope: repr=False + __repr__
                                               CustodyNamespace: idem, dois campos
                                               VerifiedDeletionCapability: idem
                                               version_etag: repr=False
                                               Descriptor.__repr__ passa a DELEGAR
tests/unit/memory/test_erasure_target.py       +16 funções (u93–u108)
tests/static/test_erasure_target_isolation.py  s25 substituída por s25/.1/.2/.3
docs/.../EDR_E4_9_7_3_...md                    novo
```

`target_resolution_enums.py` e `ports/erasure_target.py` não precisaram mudar.

---

## 11. Riscos que declaro

**(a) A representação ficou mais pobre, e isso tem custo real.** Depurar um
`ControlScope` agora exige acessar o campo. `u108` garante que o que **não** é
texto livre continua visível, mas o risco é que alguém "resolva" isso removendo
a redação numa sessão difícil. As duas camadas mais `s25_3` tornam a remoção
visível em teste.

**(b) A redação não impede um consumidor de imprimir o valor.** Ele precisa ser
acessível — é o contrato. A proteção é contra vazamento **acidental e
idiomático**, nunca contra decisão deliberada de expor. Mesma posição da
E4.9.7.1 sobre o localizador.

**(c) Segredo no caminho do localizador continua indetectável.** `DEFERRED`,
como na cadeia 81.

**(d) Sexta alegação minha mais forte que a prova.** E desta vez com o
inventário no lugar — a tabela do §3 da cadeia 82 existia e estava errada,
porque eu classifiquei por nome, não por domínio executável, e não exercitei os
canais. A contramedida desta rodada é diferente em espécie: `s25_1` deriva os
canais por reflexão e `s25` os exercita com valor sensível real. Uma guarda que
só pode passar não vale nada; estas podem falhar.

**(e) `transient_locator` é o único campo com garantia em duas camadas
distintas.** Rejeição estrutural (`APPLICATION_LEVEL`) mais redação. Segredo no
caminho fica fora das duas. Registrado para que ninguém leia "redigido" como
"seguro".

---

## 12. Estado

```text
PATCH_CHAIN = 83
MIGRATION_HEAD = c8a3f5017e94 (INALTERADO)
E4_9_7_3_IMPLEMENTATION = COMPLETE_CANDIDATE
E4_9_7 = AWAITING_INDEPENDENT_REAUDIT
A5 = FIXED
TARGET_RESOLVER_ADAPTER = NONE
ERASURE_EFFECT = NONE
ERASURE_RECORD_WRITER = NOT_COMPOSED
E4_9_READY = FALSE
E4_9_8 = NOT_STARTED
```

Não existe adaptador, não existe efeito, e a E4.9.8 não foi iniciada.
`PASS_FINAL` pertence à auditoria independente.
