# E7.4-1 B1a — ponte de enforcement da proteção humana

Resultado binário desta fatia, os invariantes que o banco impõe e o escopo
negativo cumprido. Autoridade: Master v2.9.12 (adendo E7.4-1 e §20),
`PASS_FINAL_PRE_IMPLEMENTATION_E7_4_1_R10_1` e o prompt B1a da Chain122.

```text
E7_4_1_HUMAN_PROTECTION_GATE = CURRENT_DELIVERY
CONNECTION_KERNEL_CHAIN122 = INHERITED_COMPONENT_CLOSED_PASS_FINAL
PASS_FINAL_CHAIN122_DOES_NOT_COVER_HUMAN_PROTECTION_GATE = TRUE
```

A etiqueta `E7.4-1` já designou o kernel de conexões, que está fechado. Este
documento trata do **gate de proteção humana**, entrega diferente e com
`PASS_FINAL` próprio ainda não concedido.

## 1. Resultado binário

```text
B1A_IMPLEMENTED = YES
ROUTER_MODIFIED = NO
PRODUCTION_COMPOSITION = NO
E4_MODIFIED = NO
E8_IMPLEMENTED = NO
E7_4_2_STARTED = NO
MCP_RUNTIME = NOT_IMPLEMENTED
PASS_FINAL_E7_4_1 = NOT_DECLARED_BY_IMPLEMENTER
```

```text
BRIDGE_READY != OPERATIONAL_PROTECTION
```

A ponte existe, compila, é provada e **não está composta**. Nenhum
composition root produtivo a instancia, e nenhuma das quatro posições de gate
está ligada ao caminho real. Ligar é B1b, e só depois do `PASS_FINAL` da E8
IAB — que é quem produz o descritor semântico autorizado.

## 2. Quem decide o quê

```text
NORMATIVE_PROHIBITION_OWNER = E4 GOVERNANCE
SEMANTIC_DESCRIPTOR_OWNER   = E8 IAB
EFFECT_ENFORCEMENT_OWNER    = E7.4-1
```

A E7 não cria catálogo de dano, não classifica, não pontua e não lê forma. A
autoridade normativa é a fronteira de plataforma da E4.3, cuja regra inteira
é consumida e nunca reimplementada:

| descritor | fronteira E4 |
|---|---|
| sem capacidade crítica | `NOT_APPLICABLE` |
| capacidade + `ANALYTICAL` | `NOT_APPLICABLE` |
| capacidade + `PREVENTIVE` | `NOT_APPLICABLE` |
| capacidade + `OPERATIONAL_ENABLEMENT` | `PROHIBITED` |
| capacidade + `UNSPECIFIED` | `PROHIBITED` |

```text
TOPIC != CAPABILITY
ANALYSIS != OPERATIONAL_ENABLEMENT
PREVENTION != OPERATIONAL_ENABLEMENT
STRUCTURAL_COMPLEXITY_HAS_DECISION_AUTHORITY = NO
DUPLICATE_PROTECTION_CATEGORY_OWNER = PROHIBITED
```

Trabalho científico, jurídico, jornalístico, defensivo, preventivo, de
detecção, proteção, resposta ou denúncia continua alcançável. Bloquear por
assunto destruiria exatamente esse trabalho, e há prova permanente disso.

## 3. Como a fronteira de pacote foi atravessada

`app.memory` é proibido em toda a superfície da E7 pelas guardas congeladas
`e71b02` e `e72b10` — a segunda varre inclusive o router e o DTO.

```text
BRIDGE_BY_DIRECT_IMPORT = FROZEN_GUARD_VIOLATION
PORT_IN_THE_CONSUMER · ADAPTER_WHERE_THE_IMPORT_IS_LEGAL
E7_STATIC_GUARDS = UNCHANGED
```

A porta vive em `app/orchestration/ports/governance.py`; o adaptador, único
módulo do caminho que importa `app.memory`, vive em
`app/services/governance_bridge.py`. Precedente literal: a
`MultiInputTransformationPort` da E4.5 resolveu a mesma tensão do mesmo jeito.

O vocabulário de fronteira é declarado **por valor** em
`ports/governance_vocabulary.py` e sua paridade com os quatro enums da E4 é
provada por igualdade de conjuntos — nunca de inclusão, porque uma cópia
parcial passaria numa comparação de subconjunto.

```text
E7_HOLDS_LITERALS · E4_HOLDS_AUTHORITY · THE_PROOF_HOLDS_THEM_EQUAL
VOCABULARY_COPY_WITHOUT_PARITY_PROOF = SECOND_SOURCE_OF_TRUTH
```

## 4. Duas identidades, e por que são duas

```text
decision_fingerprint = IDENTITY_OF_DECISION
binding_sha256       = IDENTITY_OF_GATE_APPLICATION
DECISION_IS_ABOUT_AN_OBJECTIVE · APPLICATION_IS_ABOUT_A_GATE
```

A mesma decisão aplicada em duas posições produz **um** fingerprint e **dois**
bindings. É assim que se prova que a classificação ocorreu uma vez por
snapshot e foi reutilizada, em vez de recalculada quatro vezes.

O binding tem dez campos, e o décimo que importa é o `attempt_id` prealocado:
em G3 ele entra na chave, de modo que uma nova submissão produz outra chave e
o evento anterior deixa de ser reencontrável.

```text
G3_APPLICATION_WITHOUT_ATTEMPT_ID = STALE_ATTEMPT_PROOF
```

Nenhuma lista de campos é escrita à mão. O binding deriva de
`dataclasses.fields(GovernanceBinding)`; as entradas do fingerprint derivam de
`dataclasses.fields(GovernanceResolution)`, na E4. Um campo novo entra
sozinho; um campo removido some sozinho.

```text
HAND_WRITTEN_COUNT = COUNT_THAT_DRIFTS
COUNT_DERIVED_FROM_HANDWRITTEN_LIST != SCHEMA_DERIVED_MANIFEST
```

Os quatro totais do manifesto — subcasos de fingerprint, de binding, campos
comparados no vencedor e subcasos de contexto — **não são publicados aqui**.
Eles são derivados em tempo de teste pelas provas correspondentes, e uma
guarda reprova qualquer documento que os fixe em prosa.

## 5. O que o banco impõe

```text
DB_LEVEL  30 CHECK de linha no evento, 2 na associação
DB_LEVEL  3 FKs no evento, 1 na associação
DB_LEVEL  UNIQUE(decision_fingerprint, gate_position, binding_sha256)
DB_LEVEL  UPDATE/DELETE/TRUNCATE recusados por gatilho nas duas tabelas
DB_LEVEL  coerência pai/filha avaliada no COMMIT, constraint triggers diferidos
APPLICATION_LEVEL  as mesmas regras de linha, em HumanProtectionApplication
```

Três FKs, e nenhuma derivada de outra: a do Schedule prova dono, a da etapa
prova que a etapa é daquele Schedule, a da tentativa prova a rota inteira.

```text
TWO_VALID_REFERENCES != ONE_COHERENT_REFERENCE
COHERENT_OWNER != COHERENT_ROUTE
```

A coerência entre pai e filha não é reimplementada em código: `CHECK` não
cruza tabelas, e duplicá-la daria a duas fontes a chance de divergir — o
defeito que a E4.5.1 já pagou uma vez.

Achado preservado da validação R10.1: o `TRUNCATE` do pai é recusado **pela
FK do filho**, antes do gatilho; só `TRUNCATE CASCADE` alcança o gatilho do
evento.

```text
FK_REFUSAL != TRIGGER_REFUSAL
```

## 6. Ausência nunca vira permissão

```text
MISSING_AUTHORIZED_DESCRIPTOR != AUTHORIZED_EMPTY_DESCRIPTOR
SOFTWARE_FAILURE != HUMAN_HARM_CATEGORY
ABSENCE_OF_EVIDENCE != ABSENCE_OF_DECISION
UNEXPECTED_OUTCOME_INTERPRETED = FABRICATED_AUTHORITY
```

Porta ausente, exceção, tipo errado, binding incompatível, validade vencida,
instante incoerente ou desfecho fora de `{prohibited, not_applicable}`
produzem `PIA-8069` — falha técnica tipada, zero efeito. Nenhuma dessas
situações cria desfecho, categoria, capacidade ou evento.

O caminho permitido produz `ALLOWED` **registrado**, com engajamento nulo:
sem um desfecho positivo durável, qualquer defeito do gate viraria permissão
silenciosa, indistinguível de "o gate nem rodou".

`REVIEW_REQUIRED` permanece no vocabulário e **sem produtor** em v1: a
fronteira da E4 é binária, e descritor inconclusivo é capacidade futura da E8.

```text
REVIEW_REQUIRED_PRODUCER_IN_v1 = NONE
DECLARED_VOCABULARY != EXECUTABLE_TRANSITION
```

## 7. Minimização de conteúdo

```text
HUMAN_PROTECTION_EVENT_CONTENT = NONE
SAFETY_AUDIT_METADATA != DANGEROUS_PAYLOAD_ARCHIVE
```

Nenhuma coluna recebe prompt, resposta, instrução, documento, segredo ou
memória do usuário. `stated_intent` não atravessa a porta: a finalidade
declarada é registro na E4, nunca prova, e mandá-la cruzar a fronteira só
arriscaria conteúdo numa camada que se comprometeu a não guardá-lo.

Os campos textuais da resolução entram no `decision_fingerprint` e não na
vista nem no evento — é o que permite provar a decisão sem arquivar o pedido.

## 8. Retenção: obrigação declarada, sem executor

```text
POLICY_ID = human_protection_evidence_v1 · MINIMUM_AGE_DAYS = 365
EXPIRACAO_DO_EVENTO = NOT_IMPLEMENTED · EXPIRY_EXECUTOR = E4.9.PEA-0
§20.6_RETENTION_COMPLIANCE = NOT_SATISFIED_BY_E7_4_1_ALONE
E4_9_PEA_0_BLOCKS_PASS_FINAL_E7_4_1 = NO
```

Nada nesta entrega apaga evento. Enquanto a E4.9.PEA-0 não existir, a
evidência permanece por mais tempo — o que não autoriza apagamento por
processo comum nem reduz o append-only.

```text
DELETE_E7_4_1_EVIDENCE != DELETE_USER_MEMORY != DELETE_SCHEDULE
```

## 9. Escopo negativo cumprido

```text
ROUTER_MODIFIED_IN_B1A               = NO
PRODUCTION_COMPOSITION_IN_B1A        = NO
ADAPTER_INJECTED_IN_PRODUCTION       = NO
SCHEDULE_SERVICE_GATE_ACTIVATED      = NO
HANDOFF_RUNTIME_GATE_ACTIVATED       = NO
G1_OR_G4_PRODUCTION_WIRING           = NO
E4_MODIFIED                          = NO
E8_IMPLEMENTED                       = NO
E4_9_PEA_0_IMPLEMENTED               = NO
E7_4_2_STARTED                       = NO
NETWORK_OR_OAUTH_CONNECTOR           = NO
typed_fixture / decision_source      = INEXISTENTES NO CÓDIGO E NO SCHEMA
```

Duas exclusões deliberadas, aprovadas pelo titular:
`ControlReasonCode.PROTECTION_GATE_UNAVAILABLE` e a migration
`widen_control_reason_check` ficam para B1b. Elas só têm produtor no router,
que esta fatia não toca — e vocabulário sem produtor é a armadilha que este
programa já nomeou.

```text
DECLARED_VOCABULARY != EXECUTABLE_TRANSITION
NO_WIRED_BUT_INACTIVE_CODE · DELIVERY_SEQUENCING != RUNTIME_TOGGLE
```

## 10. Precedência aplicada

Onde o plano R9 e o delta R10.1 divergem, prevalece o R10.1: sem
`typed_fixture`, sem `decision_source`, e `cognitive_operation = expose` nas
quatro posições (`SC-HP-25 = CLOSED`), onde o R9 propunha `DERIVE` em G1.
