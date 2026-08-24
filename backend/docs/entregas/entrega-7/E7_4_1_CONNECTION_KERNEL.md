# E7.4-1 — kernel neutro de conexões

```text
CHAIN            = 118 (candidata)
PARENT           = 67f16686125af37a8a22e2080ac483154fe4d2f5 (Chain117)
MIGRATION        = b47e9c05d3fa, filha única de a91d3f7c26be
MCP_RUNTIME      = ABSENT
NETWORK_AND_CREDENTIALS = ABSENT
```

## Resultado binário

```text
CONNECTION_KERNEL              = OPERATIONAL
MANUAL_PROFILE                 = ONE_PER_PRINCIPAL
MANUAL_PROFILE_CREATION        = IDEMPOTENT_UNDER_CONCURRENCY
MANUAL_PROFILE_STATE           = AVAILABLE
MANUAL_PROFILE_ENDPOINT_REF    = NULL
MANUAL_HANDOFF_RECEIPT         = PRODUCED_FOR_EVERY_ATTEMPT
ORCHESTRATION_QUERY_SERVICE    = PUBLIC_BOUNDARY_ACTIVE
```

## O que a entrega criou

`app/connections/**` — kernel **neutro**: método de conexão é dado, não
subclasse. Nove modelos (quatro de catálogo, `ConnectionProfile`,
`CapabilitySnapshot`, `EntitlementClaim`, `EvaluationEvidence`,
`ConnectionExecutionReceipt`), repositório escopado por principal,
`ConnectionProfileService` idempotente e
`ConnectionExecutionReceiptService`. Faixa de erro `PIA-8065..8068`;
próximo livre `PIA-8069`.

`app/orchestration/services/orchestration_query_service.py` — fronteira
pública de leitura da E7, criada **antes** de qualquer consumidor
externo existir.

## Invariantes que o banco impõe

```text
ck_connection_profiles_available_method          ENUM_OR_REGISTRY != AVAILABLE
ix_connection_profiles_manual_singleton          NULL_NÃO_COLIDE_COM_NULL
uq_connection_profiles_id_principal              alvo da FK composta
FK (attempt_id, step_id, schedule_id)            -> handoff_attempts (DEFERRED)
FK (connection_id, control_principal_ref)        -> connection_profiles
UNIQUE (attempt_id)                              1 Attempt = 1 recibo
CHECK (attestation='attested') = (observed_model IS NOT NULL)
triggers append-only                             snapshot, evidência, recibo
trigger de ciclo de vida                         entitlement monotônico
```

```text
TWO_VALID_REFERENCES != ONE_COHERENT_REFERENCE
COERÊNCIA SOBREVIVE FORA DOS SERVIÇOS
```

## Decisões declaradas

- `control_principal_ref` é **copiado** no recibo, nunca derivado por
  join: derivá-lo faria a coerência depender da consulta em vez do
  schema, e um perfil alterado amanhã reescreveria a execução de ontem.
- O entitlement é `IMMUTABLE_PAYLOAD + MONOTONIC_LIFECYCLE`, e
  deliberadamente **não** é chamado de append-only: o estado avança.
- `BROWSER_ASSISTED_HANDOFF` nasce `DECLARED`, não `UNSUPPORTED` — é
  fluxo humano assistido, com dono na E8.
- Nenhum recibo retroativo para Attempts anteriores a esta entrega:
  `LEGACY_ATTEMPT_WITHOUT_RECEIPT != FABRICATE_HISTORY`.
- A categoria `INFRASTRUCTURE` do repositório é lista **fechada** de dois
  métodos; uma categoria sem enumeração literal seria a porta dos fundos
  da classificação exaustiva.

## Três falsos verdes encontrados por mutação

Registrados porque a lição é o produto:

```text
REFUSAL_BY_THE_WRONG_GUARD      = UNPROVEN_INVARIANT
MUTATED_FILE                    != MUTATED_SCHEMA
LOCK SERIALIZATION              != SAVEPOINT RACE RECOVERY
DEFENSE_IN_DEPTH_NÃO_EXERCITADA = DEFENSE_NÃO_PROVADA
```

A prova de vínculo bilateral era recusada pelo `UNIQUE`, não pela FK
composta; a prova de imutabilidade do entitlement era recusada pela
guarda de transição, não pela de payload; e o savepoint nunca era
exercitado porque o lock consultivo serializava antes. Os três passavam
verdes. Corrigidos na camada própria, com mutante próprio para cada
mecanismo.

## Corretivo R1 — achados C1, C2 e C3 da auditoria da Chain118

Migration `c58d1e0a94f7`, filha única de `b47e9c05d3fa`.

### C1 — o recibo podia falsificar a rota

```text
COHERENT_OWNER != COHERENT_ROUTE
RECEIPT_METHOD == PROFILE_METHOD
```

O vínculo bilateral provava dono, não rota: um perfil `manual_handoff`
aceitava recibo `direct_provider_api`. E a verdade do manual só existia
no value object para um dos quatro campos, de modo que por SQL bruto
entrava um repasse manual com operador, modelo solicitado, modelo
observado e atestação `attested` — atribuição inteiramente inventada.

Correção: alvo ternário `uq_connection_profiles_id_principal_method`, FK
do recibo incluindo `connection_method` (a binária foi **substituída**,
não somada) e `ck_connection_execution_receipts_manual_truth`.

## Corretivo R2 — os dois resíduos do R1

Migration inalterada; o R2 é de código e de guarda.

### R2-1 — a view do recibo ainda aceitava manual falso

```text
SILENT_EDIT = UNAPPLIED_EDIT
UM CONSTRUTOR PÚBLICO PROVADO != TODOS OS CONSTRUTORES PÚBLICOS
```

O corretivo R1 **declarou** o invariante em `ExecutionAttribution` e em
`ConnectionExecutionReceiptView`, e o aplicou só no primeiro: a edição do
segundo usou um `str.replace` que não casou e falhou em silêncio. A prova
`p15` exercitava apenas um construtor, então nada reprovou.

Corrigido com assertiva de aplicação, quatro provas de violação
(`u04`), não-vacuidade nos dois sentidos (`u05`) e mutante próprio
(`M-VIEW-MANUAL`).

### R2-2 — a guarda excluía o router por arquivo

```text
ARQUIVO_EXCLUÍDO_DA_GUARDA != FUNÇÃO_EXCLUÍDA_DA_GUARDA
```

`s16` exclui o router inteiro — correto, porque ele conserva 48 ignores
históricos legítimos. Mas isso deixava os seis mapeadores convertidos sem
proteção: dava para rebaixá-los a `object` e reintroduzir `attr-defined`
sem reprovação. A guarda passou a ser **por função** (`s18`, `s19`), com
a contagem histórica presa em `s20`, e mutante `M-ROUTER-OBJECT`.

### C2 — a fronteira nova estava silenciada

```text
SILENCED_BOUNDARY = UNCHECKED_BOUNDARY
NEW_ATTR_DEFINED_IN_TYPED_BOUNDARIES = 0
HISTORICAL_ROUTER_ATTR_DEFINED       = 48
```

O commit da Chain118 acrescentou 90 `# type: ignore[attr-defined]`.
Tipar concretamente revelou **dois defeitos reais** que eles escondiam:
`provenance_record_ref` declarado `str` sendo `UUID`, e três campos
`NOT NULL` declarados opcionais na projeção. Nenhum quebrava em runtime,
e era exatamente isso que os ignores garantiam para o drift seguinte.

Os 48 restantes no router são **históricos**, em helpers que recebem
linha ORM viva dentro da transação de escrita; tipá-los é ampliação que
esta auditoria não pediu. O zero é das fronteiras novas, não global.

### C3 — a afirmação era ampla demais

```text
MCP_QUERY_BYPASS_AST = 0    (doze leituras de superfície)
ROUTER_INTERNAL_CALLS = 5   (classificadas e permitidas)
```

`BYPASS_AST = 0` provava "zero dentre as consultas catalogadas", e
sobravam cinco chamadas diretas permitidas pelo plano (`lock_schedule`,
`get_command_receipt`, `get_control_event`, `get_audit_opinion`,
`get_delegation`). A guarda passou a classificar **exaustivamente**, e
reprova chamada nova não classificada.

## Escopo negativo cumprido

Sem MCP, OAuth/IdP, authorization server, token, senha, cookie, segredo,
rede, conexão automática, FAROL, E8, E9, enum de marcas, catálogo
estático de releases. `sdk/` sem delta; `alembic/env.py` alterado apenas
para registrar o pacote novo, nunca para mascarar logging.
