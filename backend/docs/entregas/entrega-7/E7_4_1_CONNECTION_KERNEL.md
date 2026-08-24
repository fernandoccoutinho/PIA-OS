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

## Escopo negativo cumprido

Sem MCP, OAuth/IdP, authorization server, token, senha, cookie, segredo,
rede, conexão automática, FAROL, E8, E9, enum de marcas, catálogo
estático de releases. `sdk/` sem delta; `alembic/env.py` alterado apenas
para registrar o pacote novo, nunca para mascarar logging.
