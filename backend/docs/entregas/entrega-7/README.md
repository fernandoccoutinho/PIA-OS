# Entrega 7 — orquestração e handoff multi-IA

Índice local dos documentos congelados da E7.0. Nenhum código de produção
foi escrito nesta etapa.

```text
E7_0 = DOCUMENTAL_FREEZE
E7_CODE = NOT_STARTED
CODE_PATCHES_APROVADOS = 3
BASE_PARENT = 91fdfe4d36a01f317fd35282f4ea8d4b84f948e9
```

Este arquivo existe porque o verificador documental trata documento nunca
referenciado como órfão, e `README.md` é o ponto de entrada previsto por
ele. É índice de navegação: não acrescenta, resume nem reinterpreta
nenhuma decisão dos quatro documentos abaixo, que são a autoridade.

| documento | conteúdo |
|---|---|
| [MAI-001 R1 — arquitetura de handoff, orquestração e auditoria](MAI-001_MULTI_AI_HANDOFF_ORCHESTRATION_AND_AUDIT_ARCHITECTURE_R1.md) | contrato arquitetural: vocabulário, `AIHandoffEnvelope`, modos, ciclo de vida, autoridade, grafo produtor→consumidor, checklist §19.10, decisões D1–D10 |
| [Plano de pré-implementação E7.0 R1](PRE_IMPLEMENTATION_PLAN_E7_0_CHAIN108_R1.md) | sequenciamento em três patches (E7.1, E7.2, E7.3), com resultado binário, migration, testes, mutantes, escopo negativo e parent esperado de cada um |
| [Addendum — bindings de segurança v1](ADDENDUM_E7_0_BINDINGS_DE_SEGURANCA_v1.md) | vinculante junto à aprovação: `Schedule.control_principal_ref`, acesso ao repositório escopado por esse principal e escopo de idempotência |
| [PASS_FINAL da auditoria independente](PASS_FINAL_AUDITORIA_INDEPENDENTE_E7_0_CHAIN108_R1.md) | veredito da auditoria sobre a arquitetura, com as cinco correções verificadas e a sequência aprovada |

## Sequência aprovada

```text
E7.0 freeze documental                 -> count 109
E7.1 contrato, estado e persistência   -> count 110
E7.2 fluxo manual ponta a ponta e API  -> count 111
E7.3 gates, cancelamento e auditoria   -> count 112
```
