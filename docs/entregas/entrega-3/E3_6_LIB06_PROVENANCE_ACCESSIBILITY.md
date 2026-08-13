# E3.6 / LIB-06 — Provenance & Accessibility Manager

## Objetivo

Responder a duas perguntas: **Provenance** — "de onde veio esta
distinção cognitiva e por quais agentes/operações ela passou?" —
**Accessibility** — "esta distinção continua acessível ao sistema e
em qual condição?". Preservar a história causal necessária para
reconstruir origem/transmissão de uma distinção, **sem** armazenar
indefinidamente todo o conteúdo intermediário produzido por IAs — a
analogia do módulo: preservar a trajetória causal do fóton, não todos
os estados do Universo atravessados.

## Baseline confirmada por inspeção real

`CognitiveObject` (COID=`id`, `clid`, `accessibility` sem guard de
transição até esta entrega, `revision_status`), `AccessibilityState`
já existente e suficiente (4 valores — **nenhum segundo enum
criado**), `TransformationRecord.actor_ref: UUID|None` já reservado
desde E3.4 (**mantido intocado**, conforme "não alterar E3.4" — nenhum
FK foi adicionado a ele), faixa `PIA-8xxx` livre a partir de
`PIA-8017` (confirmado por inspeção de `codes.py`, não suposição).

## ProvenanceRecord contract

Contrato base: `E3_DOMAIN_MODEL_DRAFT.md`, seção "2. ProvenanceRecord".

**Conflito real encontrado, resolvido sem Stop Condition**: o prompt
do módulo E3.6 usa a terminologia `execution_id`/`parent_execution_id`
(§2, §12); o Draft congelado **não tem** esses nomes — tem
`agent_instance_id`, `agent_sequence`, `orchestration_run_id`,
`agent_role`, `parent_agent_output_ref`. Resolvido priorizando o Draft
(autoritativo, conforme o próprio §2 do módulo instrui) — o conflito
é entre o *prompt* e o *Draft*, não entre o Draft e código já
existente; o Draft prevalece por ser o contrato congelado:

- `provenance_id` (=`id`) já identifica univocamente "esta
  contribuição/execução" — cumpre o papel que o prompt chama de
  `execution_id`.
- `agent_instance_id` distingue instâncias/execuções do mesmo agente
  numa mesma orquestração.
- `parent_agent_output_ref` (tipado `str?` no Draft — referência
  solta, não FK estruturada) cumpre o papel causal que o prompt chama
  de `parent_execution_id`.
- `actor_id` cumpre o papel de `agent_id` do prompt (nome genérico do
  Draft, não específico de IA — também serve `HUMAN`/`SYSTEM`).

Nenhum campo duplicado foi criado.

**Campo `coid` concretizado** (não está no Draft): o Draft só define
`ProvenanceRecord` como referenciado *por* `CognitiveDistinction.origin`/
`.provenance` — `CognitiveDistinction` está `DEFERRED` desde E3.1. Sem
essa entidade intermediária, `ProvenanceRecord` precisa de uma âncora
direta para ser utilizável nesta fase — `coid: UUID`, FK obrigatória
para `cognitive_objects.id`. Mesmo padrão de concretização já usado em
E3.3 (`transformation_ref`→estrutural), E3.4 (`actor_ref`→nulo), E3.5
(endpoints por COID em vez de `CognitiveDistinction`).

**`source_type`/`actor_type` como enums fechados**: o próprio Draft
delega isso a E3.6 — "enum fechado em E3.6, aberto aqui [no Draft]"
para `source_type`. Implementados: `ProvenanceSourceType` (`HUMAN` |
`AGENT` | `IMPORT` | `SYSTEM`) e `ProvenanceActorType` (`HUMAN` |
`AGENT` | `SYSTEM`) — exatamente os valores já listados no Draft,
nenhum inventado.

`provider_id`/`model_id` **nunca obrigatórios**, mesmo quando
`actor_type == AGENT` — nenhuma validação condicional foi
implementada que os exija.

## Provenance != Transcript

Nenhum campo de conteúdo/payload/transcript existe no modelo —
confirmado por inspeção estrutural das colunas reais e por inspeção
da assinatura pública de `ProvenanceManager.record()`. `evidence_refs`
é uma lista de *referências* (strings), nunca conteúdo bruto embutido.

## Multi-IA Triple-Mode

```
COMPETITIVE_READY = TRUE
COMPLEMENTARY_READY = TRUE
SEQUENTIAL_READY = TRUE
```

`PROVENANCE(A) != PROVENANCE(B)` sempre — cada `ProvenanceRecord` é
uma linha própria, testado (`MIA1`) com duas IAs produzindo
contribuições independentes para o mesmo `coid`, ambas coexistindo
sem uma sobrescrever a outra. `MIA2` (roles `generator`/`critic`
preservados), `MIA3` (cadeia `SEQUENTIAL` reconstruída via
`agent_sequence`/`parent_agent_output_ref`), `MIA4` (nenhuma
contribuição sobrescreve outra), `MIA5` (nenhum SDK de IA é importado).

## Storage discipline

`LOGICAL IMMUTABILITY != PHYSICAL DUPLICATION` — múltiplos
`ProvenanceRecord`s referenciam o mesmo `coid` sem duplicar o conteúdo
do `CognitiveObject` (o modelo nem tem campo de conteúdo — herdado da
ausência já documentada em E3.1). Nenhuma deduplicação genérica de
blobs implementada — fora de escopo nesta fase.

## Append-only

`ProvenanceRepository.update()`/`.delete()` sempre rejeitam
(`ProvenanceRecordImmutableError`, `PIA-8017`) — mesma disciplina de
`LineageRepository`/`TransformationRepository`/`RelationshipRepository`.
Diferente de `Relationship`, `ProvenanceRecord` **não tem** lifecycle
de `retire()` — é puramente append-only, sem nenhuma transição
legítima pós-criação.

## Accessibility semantics

**Escopo deliberadamente restrito** — decisão registrada, não Stop
Condition. O Domain Model Draft é explícito (§4): "a máquina de
transição de estados completa (quem pode mover o quê, sob qual
autoridade) é escopo de `E4` — E3 apenas define e persiste o enum e
valida que a transição para `CAUSALLY_EXTINCT` sempre tem um evento
causal associado, nunca é o valor default nem um efeito colateral de
query."

`AccessibilityManager`, portanto:

- **não** restringe qual estado pode transicionar para qual — a
  matriz completa de autoridade não é antecipada aqui;
- garante que `CAUSALLY_EXTINCT` nunca é o default (já estrutural
  desde E3.1);
- exige `reason` não-vazio especificamente para a transição a
  `CAUSALLY_EXTINCT`.

**Limitação documentada honestamente**: a exigência formal do Draft —
"sempre tem um evento causal associado" — depende de
`CausalHistoryEvent` (`E3.9`, ainda não implementado). Como proxy
interino, genuinamente aplicável hoje, uso um `reason` explícito
não-vazio (`AccessibilityInvalidTransitionError`, `PIA-8018`) — não é
o mesmo que um evento causal formalmente referenciado, mas garante que
a transição nunca é silenciosa/automática.

Transição idempotente é sempre permitida, inclusive para
`CAUSALLY_EXTINCT` já atingido — não exige `reason` novamente.

## Concurrency

Nenhum invariante formal do tipo "no máximo um X" existe para
`AccessibilityState` nesta fase (diferente de CLID/CURRENT). Ainda
assim, `AccessibilityManager.transition()` reaproveita
`ObjectRepository.refresh_for_update()` (E3.3.1) como defesa razoável
contra anomalias de leitura-decide-escreve. Validado com concorrência
genuína contra PostgreSQL real (duas threads, duas sessões/conexões
distintas) — ambas as transições podem commitar, o estado final é
sempre um dos dois alvos válidos, nunca corrompido/parcial. Executado
4+ vezes, estável.

## Migration

`e2c89ee3aa59_create_provenance_records_table_e3_6_.py` — tabela nova,
aditiva. `coid` com FK real para `cognitive_objects.id` (sem `ON
DELETE CASCADE`), **sem** `UniqueConstraint` em `coid` isolado.
Nenhuma migração de `AccessibilityState` foi necessária — o campo já
existe desde E3.1.

**Análise explícita SCHEMA REVERSIBILITY vs HISTORICAL PRESERVATION**
(aplicando a COUT Data Preservation Rule de E3.5.2): o `downgrade()`
desta migração remove a tabela inteira — diferente do caso de E3.5.1
(constraint mais restritiva substituindo uma menos restritiva sobre
tabela já existente), aqui não existe um "schema anterior" capaz de
representar parcialmente os dados — a tabela simplesmente não existia
antes desta migração. Isso é o comportamento padrão de qualquer
migração introdutora de entidade — não é uma nova violação da regra
de preservação. `MIGRATION_REVERSIBILITY = REVERSIBLE` (não
condicional) — com a ressalva óbvia de que reverter remove os dados de
proveniência registrados, mesmo comportamento de reverter qualquer
outra migração de criação de tabela.

Testado `upgrade → downgrade → upgrade` contra PostgreSQL 16 real —
`cognitive_objects`, `lineage_edges`, `relationships` (incluindo os
índices/constraints de E3.5.1) e `uq_cognitive_objects_one_current_per_clid`
(E3.4.1) confirmados intactos em todo o ciclo.

## Error Codes

| Código | Situação |
|---|---|
| `PIA-8017` (novo) | `update`/`delete` físico de `ProvenanceRecord` rejeitado (append-only) |
| `PIA-8018` (novo) | Transição para `CAUSALLY_EXTINCT` sem `reason` |

`PIA-8001`-`PIA-8016` inspecionados; nenhum reaproveitável.

## Relação com Revision/Derivation e Relationship

Não alterado E3.4/E3.5. Um novo `CognitiveObject` criado por
`revise()`/`derive()` pode receber nova `Provenance` — a proveniência
do objeto anterior permanece intacta. `Relationship != Provenance` —
nenhuma `Relationship` é criada automaticamente para representar
proveniência.

## Testes

91 testes novos (87 unitários + 4 de integração):

- **Model** (`test_provenance_record.py`, 8): criação, campos
  opcionais, todos `source_type`×`actor_type`, `provider_id`/
  `model_id` nunca obrigatórios, múltiplos registros por COID, FK,
  `evidence_refs`, ausência de coluna de conteúdo.
- **ProvenanceManager** (`test_provenance_manager.py`, 22): `P1`-`P13`,
  não-commit, `MIA1`-`MIA5`.
- **AccessibilityManager** (`test_accessibility_manager.py`, 15):
  `A1`-`A10`, idempotência, `assert_accessible`, não-commit.
- **Integração contra PostgreSQL real**
  (`test_provenance_accessibility_integration.py`, 4): round-trip com
  múltiplos agentes, append-only real, transição real, e
  **concorrência genuína de Accessibility**.

**100% de cobertura de linha em todo `app/cognitive/`** (364 testes
unitários).

## Non-Regression

819 passed, 25 skipped (sem `.env` local; inclui 2 skips permanentes
esperados dos testes de guarda de downgrade de E3.5.2/E3.5.2a, que
checam a head antiga `f11551e97026` — não é mais a head real após
esta migração, skip correto, não regressão), 97,65% (acima do
anterior, 97,54%). Nenhum arquivo protegido tocado;
`TransformationRecord`, `Relationship`, `LineageEdge`,
`VersionManager`, `RelationshipEngine`, `ClidManager`, `CoidManager`,
`CognitiveObject` (incluindo `accessibility` — nenhuma coluna nova) —
todos intocados nesta entrega.

## Deferred Items

`Hypervisor E7`, consensus engine, seleção automática de resposta,
agent ranking, trust/quality score, armazenamento de chat integral,
`CausalHistory`/`CausalHistoryEvent` completos (`E3.9`),
`CausalComparison`, `CausalClassRef`, `CognitiveDistinction`,
traversal multi-hop, APIs HTTP, `E3.7+`.

## Riscos

- `AccessibilityManager` não impõe uma matriz de transição — qualquer
  estado pode ir para qualquer outro (exceto `reason` para
  `CAUSALLY_EXTINCT`). Deliberado, mas `E4` precisará definir a
  autoridade real antes de expor isso a chamadores não confiáveis.
- O proxy `reason`-obrigatório não é estruturalmente verificável
  (nenhuma FK a um evento causal real) — aceito como limitação
  interina até `E3.9`.
