# EDR E5.0 — Registro de Decisões Arquiteturais

Retorno ao índice: [E5.0 — Architectural Documentary Freeze](E5_0_ARCHITECTURE_FREEZE.md)

```text
OPEN_ARCHITECTURAL_DECISIONS = NONE
E5_RUNTIME_IMPLEMENTED = NO
```

---

## 1. Cadeia de autoridade

| Artefato | SHA256 | Veredito |
|---|---|---|
| `PRE_IMPLEMENTATION_PLAN_E5_0.md` (tentativa 1) | `4df85131667c41c4e0223e9c87dfb1ed1fa3123a8d432e5cb2341300f0daf005` | FAIL — B1, B2, M1–M4, m1 |
| `..._CORRECTIVE_v2.8.md` (tentativa 2) | `5e47641c5c0e3a7dda8fe9602b94e221563aca8c662ad341cf813ad8e4020174` | FAIL — B3, M5, M6, m2, m3 |
| `..._CORRECTIVE_v2.8.1.md` (tentativa 3) | `8d510189c44851f11f2a6be0f9363e9184189ff3c24069c799f6770d4cb840ae` | FAIL — B4, M7, m4, m5 |
| `..._CORRECTIVE_v2.8.2.md` (tentativa 4) | `8c52f1209cc221a24ce964b6bd0f009ded2872e33dee0e0cc4f6aabcc08669f4` | **PASS_FINAL** — 30/30 |
| `PASS_FINAL_AUDITORIA_INDEPENDENTE_E5_0_PLAN_v2.8.2.md` | `73f81bb395d3255542d8a37f73b25f2343ce903f12e7b78ed0083ee18bdb94a2` | veredito |

As tentativas rejeitadas foram preservadas sem edição. Histórico é evidência.

### 1.1 Baseline e ambiente medidos

Medições da tentativa 2, contra o kit v2.8, verificadas independentemente e
preservadas sem reexecução nas tentativas seguintes.

```text
KIT v2.8            48/48 checksums PASS; zero path traversal, symlink ou CRC inválido
MASTER v2.8         389f44816161a6f884f043ee50160c805fb08721398b2b0eacc5c1f31660f3df
HEAD                340443aa96da16824b624ff767ea24cf1e019daf
PARENT              5eeab210627ae631bc2e58237fc5268dc663a93d
TREE                f45013d9927b0c4898a247e2f8958ad4a26f2c5b
PATCH_ID            51d0b416c7825454b36529dc77613e4e1d6eaf51
COMMIT_COUNT        98
MIGRATION_HEAD      e7c25a91f4b3 (cabeça única)
WORKTREE            limpa · git fsck --full limpo

COLETA              4456
FULL                4455 passed / 1 skipped / 0 failed
RAW                 4455 passed / 1 skipped / 0 failed
COVERAGE            99.31%
RUFF                PASS
BLACK               436 arquivos sem alteração
MYPY                7 erros históricos, NEW = 0
ALEMBIC             round trip up/down/up
```

```text
MEASUREMENT_PROVENANCE = ATTEMPT_2_AGAINST_KIT_v2_8
PRESERVED_HISTORICAL_MEASUREMENT != NEW_MEASUREMENT
HISTORICAL_MEASUREMENT != CURRENT_MEASUREMENT
```

Não medido, com causa e impacto declarados: reconstrução por `git am` isolado
sobre o parent (identidade do resultado provada por PATCH_ID e TREE);
reexecução das 18 sondas de caracterização da E4.12 contra a cadeia 96 e os dois
candidatos rejeitados (árvores fora do kit); kit de aceitação de 28 gates
(equivalentes reexecutados individualmente).

---

## 2. Inventário medido da baseline

```text
backend/app            201 arquivos .py de produção
backend/tests          209 arquivos: 113 unit, 35 integração, 14 static
backend/alembic        21 revisions, cabeça única
docs/entregas          raiz do repo: 61 documentos em entrega-4
backend/docs/entregas  raiz do backend: 7 documentos, com checker
DOC_ROOTS_UNIFIED      NO

PIAP em backend/app, tests, alembic        0
PIAP no repositório                        1 menção narrativa em README
símbolo preditivo em produção              0
próximo código de erro livre               PIA-8052
CognitiveOperation                         ONZE membros
```

Contratos E4 que a E5 consome, todos verificados no código: `MemoryContext`,
`ContextManager`, `GovernanceResolution`, `PersistenceAssessment`,
`MemoryRetrievalResult`, `AccessibilityTransitionResult`,
`MemoryIsolationManager`, `ErasureTargetResolverPort`,
`DestructiveApprovalEnvelope`, `ErasureEffectPort`, `RetentionAssessment`,
`ComplianceReport`, `ValidatedExperienceAppend`. A porta real de recuperação é o
`MemoryRetrievalManager`, não o `SearchEngine` — lição paga no corretivo g01_1 da
E4.12.

---

## 3. Decisões arquiteturais

### D1 — PIAP mínimo protocolar

**Decisão.** `PIAP = VERSIONED_PROVENANCE_PRESERVING_PROTOCOL_ENVELOPE`.
Transporta contexto, alegações, evidência e metadados de contrato. Não interpreta
ciência, não decide estado nem rota, não escreve E4, não executa nem seleciona
provedor. `PIAP_ENVELOPE != AI_HANDOFF_ENVELOPE`.

**Razão.** O código não contém PIAP — uma menção narrativa em README, zero em
produção — e as duas fontes v1.2 não o mencionam. A E5 não reusa PIAP: cria PIAP.
O envelope mínimo é o que faz `MATERIAL_LIMIT_REQUIRES_PROVENANCE_AND_AUTHORITY`
e `EMERGENCY_GUIDANCE_REQUIRES_AUTHORITATIVE_PROVENANCE` terem por onde chegar ao
avaliador.

**Alternativas rejeitadas.** PIAP maior com especificação própria — sem fonte
normativa suficiente. PIAP adiado, começando pela ciência — contraria
`COUT_P_USES_PIAP_CONTRACTS = TRUE`.

**Impacto.** Campos e tipos de runtime permanecem proposta da etapa `E5.a`.

### D2 — Registro de nomenclatura

Congelada. Ver [Nomenclatura e colisões](E5_0_NAMING_AND_COLLISIONS.md) secao 3.

### C4 — Nome do conflito preditivo

**Decisão.** O tipo conceitual usa nome específico conservando `Predictive` e
`Claim`. `Conflict` isolado é proibido no namespace `predictive_accessibility`.

**Razão.** A baseline já usa `Conflict` com três significados de identidade.
Sem a regra, a guarda de nomenclatura não distinguiria os casos.

### D3 — Persistência da reconfiguração

**Decisão.** Se a reconfiguração exigir persistência, usa ownership e
repository/port PRÓPRIOS da E5. `E4_APPROVAL_RECORD_REUSE = FORBIDDEN`.

**Razão.** Reutilizar `ApprovalRecord` da E4.9.9.a reabriria a fatia de origem e
exigiria corretivo autorizado da E4 congelada.

**Impacto.** Mecanismo físico e migration exigem preflight e autorização de
`E5.l`.

### D4 — Aprovação

**Decisão.** A E5 NÃO concede aprovação.
`PIAP_TRANSPORTS_APPROVAL_REFERENCE_AND_STATUS = TRUE`;
`E5_VALIDATES_BUT_DOES_NOT_GRANT_APPROVAL = TRUE`. Ausência, expiração, versão
divergente ou escopo insuficiente impedem promoção, limite material e rota
`ROBUST`. UX e coleta de aprovação permanecem na E8.

**Razão.** É D4 que torna
`ROBUST_ROUTE_WITHOUT_AUTHORIZED_OR_VALIDATED_BOUNDS = FORBIDDEN` verificável.
Sem referência de aprovação transportada e validável, limite autorizado seria
afirmação sem objeto.

**Impacto.** Arestas obrigatórias para `E5.l`, `E5.o` e `E5.s` — ver
[Decomposição](E5_0_DECOMPOSITION_AND_DEPENDENCY_GRAPH.md) secao 3.2.

### D5 — ValidatedExperience

**Decisão.** `NO_VALIDATED_EXPERIENCE_WRITE_BY_E5`. A E5 não grava
`ValidatedExperience` e não altera `SECTION_BY_TABLE` na E3 nem na E4.

**Razão.** Habilitar o transporte hoje exigiria reabrir a E3 congelada.

**Impacto.** A divergência do transporte diferido deixa de ser questão aberta
para a E5. Integração futura exige módulo e autoridade separados.

### D6 — Operação de governança da leitura

**Decisão.** `CognitiveOperation.READ`. Nenhum décimo segundo membro é criado; o
enum permanece com onze.

**Razão.** Ampliar o enum exigiria EDR próprio, e o precedente E4.3.3 mostra que
a resposta não é automática.

### D7 — Fonte de orientação emergencial

**Decisão.** `GUIDANCE_SOURCE_SELECTION = OUTSIDE_E5`;
`GUIDANCE_INPUT = OPTIONAL_PIAP_INPUT`. `E5.p` valida proveniência e produz
resultado tipado; não adquire, não gera e não escolhe fornecedor.

**Razão.** A pergunta que a etapa precisa responder não é de onde vem a
orientação, e sim se ela é válida agora, aqui, nesta versão — respondível sem
saber quem a forneceu. Exigir a escolha do fornecedor criaria o acoplamento que a
fronteira com E6 e E8 existe para evitar.

### L4 — Materialidade

**Decisão.** `MATERIALITY_STATUS = SUPPORTED | NOT_SUPPORTED | UNRESOLVED`, sem
limiar universal. `UNRESOLVED` impede que a resposta seja apresentada como
completa.

**Razão.** Não inventar limiar é correto; deixar a materialidade como juízo
futuro permitiria omissão silenciosa. Não saber decidir é resultado legítimo
apenas quando existe um lugar governado para esse resultado.

Detalhe completo em
[Completude e proteção](E5_0_COMPLETENESS_AND_PROTECTION.md) secao 3.

---

## 4. Colisões nominais e lacunas

Colisões C1 a C4 detalhadas em
[Nomenclatura e colisões](E5_0_NAMING_AND_COLLISIONS.md) secao 2.

```text
L1  a guarda M14 da E4.12 mede apenas nome de definição.
    DEFINITION_NAME_GUARD != ABSENCE_OF_CAPABILITY
    A E4 está congelada e não será corrigida por isso; a guarda equivalente da
    E5 nasce correta, com escopo ampliado e mutante próprio.

L2  não há guarda de fronteira read-only E5 para E4, nem de ausência de efeito
    externo. Lacuna esperada — a E5 não existe. Entregável de E5.b.

L3  as duas tabelas E5.x das fontes v1.2 colidem entre si. Resolvida por
    rótulos próprios E5.a a E5.t.

L4  RESOLVIDA — ver secao 3.
```

### 4.1 Divergências documentais registradas, não corrigidas

```text
DIV-1  E4_TO_E5_HANDOFF.md declara READY_FOR_E5 = FALSE e
       PASS_FINAL = NOT_DECLARED, enquanto o estado autoritativo é
       READY_FOR_E5 = TRUE. O documento foi commitado ANTES da auditoria
       independente. Histórico esperado; NÃO editar.
       HISTORICAL_DOCUMENT_STATE != CURRENT_EXTERNAL_AUDIT_STATE

DIV-2  O mesmo handoff rotula o candidato como COUT_P_V1_2, enquanto a
       autoridade vigente é COUT-P v1.3 FROZEN_CANDIDATE. Histórico.

DIV-3  DOC_ROOTS_UNIFIED = NO. Duas raízes documentais, uma com checker e outra
       sem. DEFERRED na E4; a decomposição da E5 não depende disso, e este
       freeze usa apenas a raiz com checker para não ampliar a divergência.
       DEFERRED_ITEM != UNIVERSAL_PRECONDITION

DIV-4  Transporte de ValidatedExperience DEFERRED. Encerrado para a E5 por D5.
```

---

## 5. Histórico de achados de auditoria

Preservado integralmente. Nenhuma tentativa rejeitada foi apagada.

| Achado | Classe | Tentativa | Substância |
|---|---|---|---|
| B1 | BLOCKER | 1 | autoridade histórica usada como canônica |
| B2 | BLOCKER | 1 | `ABSTAIN` criado como quinta rota |
| M1 | MAJOR | 1 | contratos v2.6–v2.8 ausentes |
| M2 | MAJOR | 1 | matriz de testes incompleta |
| M3 | MAJOR | 1 | PIAP sem freeze |
| M4 | MAJOR | 1 | nomenclatura pendente |
| m1 | MINOR | 1 | arquivo não era UTF-8 válido |
| B3 | BLOCKER | 2 | proveniência e completude não eram predecessores causais do router |
| M5 | MAJOR | 2 | D7 tratada como bloqueio quando o contrato já define a saída ausente |
| M6 | MAJOR | 2 | L4 sem saída implementável para materialidade não resolvida |
| m2 | MINOR | 2 | dois `OK` excessivos no checklist de operação |
| m3 | MINOR | 2 | contagem dos blocos de Stop Conditions |
| B4 | BLOCKER | 3 | aprovação declarada, mas sem aresta de entrada para promoção e `ROBUST` |
| M7 | MAJOR | 3 | `CLAIM_EVALUATION_RESULT` consumido sem produtor |
| m4 | MINOR | 3 | matriz G8 contradizia as entradas PIAP declaradas |
| m5 | MINOR | 3 | estado agregado de recursos, queue e overclaim sobre omissão |

### 5.1 A classe recorrente

B3, B4 e M7 foram a mesma classe: contrato corretamente escrito e não exigível no
grafo. O invariante geral foi enunciado após B3 e ainda assim não impediu B4 nem
M7 — enunciar não bastou para aplicar. A regra mecânica que resultou disso está
em [Decomposição](E5_0_DECOMPOSITION_AND_DEPENDENCY_GRAPH.md) secao 10.

Sobre m1: o byte inválido não veio do conteúdo, veio do transporte de escrita.
Validação UTF-8 estrita após a última alteração passou a ser passo obrigatório de
encerramento, na mesma linha em que se calcula o hash.

---

## 6. Riscos

```text
R1  ALTO — colisão semântica de acessibilidade (C3) e de conflito (C4).
    Mitigação: D2 e C4 mais guarda estática com mutante, em E5.b, antes de
    qualquer ciência.

R2  ALTO — cientificização decorativa: COUT-P vira justificativa para resposta
    já escolhida.
    Mitigação: rota é função pura de estado, evidência e limites; a evidência é
    obrigatória na saída; o benchmark de L_total é cego.

R3  MÉDIO-ALTO — completude e contrafactual falham por OMISSÃO, e omissão é o
    modo de falha mais difícil de testar.
    Mitigação 1: testes de ausência (24, 25, 31, 34, 39).
    Mitigação 2: E5.o emite três conjuntos — aceitos, rejeitados e não
    resolvidos — com razão e proveniência.
    Mitigação 3: MATERIALITY_STATUS = UNRESOLVED impede declarar a resposta
    completa, dando à omissão custo visível.
    Mitigação residual: ainda existe. As três cobrem o ramo AVALIADO e não
    decidido; nenhuma cobre o ramo em que ninguém pensou. Só fecha no benchmark
    cego da E9.

R4  MÉDIO-ALTO — overfitting de instrumento, repetindo o padrão da E4.12 em que
    três dos quatro achados iniciais eram do INSTRUMENTO.
    Mitigação: medição trilateral, mutante por sonda e INSTRUMENT_INVALID com
    exit próprio.

R5  MÉDIO — escopo inflar até virar preditor, ou até virar conselheiro de
    política pública. A E5 não é um predictor.
    Mitigação: a E5 não hospeda modelo de previsão nem produz juízo de valor
    próprio; governa quando um modelo pode ser usado e preserva o vetor de ônus
    SEM ponderá-lo. Ponderar seria virar conselheiro.

R6  MÉDIO — deriva de fronteira: "só ler para calcular" vira cache, que vira
    estado, que vira escrita; e "só recomendar" vira "propor com um botão", que
    vira efeito.
    Mitigação: E5.b antes de tudo, e os casos 30 e 45 ancorados em guarda
    estática.

R7  BAIXO-MÉDIO — ambiente: PostgreSQL não vem instalado no container de
    trabalho e processos em segundo plano não sobrevivem entre chamadas.
    Mitigação: custo fixo declarado de cada etapa futura.

R8  BAIXO — tabelas E5.x das fontes ressurgirem como sequência canônica.
    Mitigação: rótulos próprios e SC-E5.0-H.

R9  BAIXO — corrupção de encoding na escrita do artefato.
    Mitigação: validação UTF-8 estrita após a última alteração, antes do hash.

R10 ALTO — um contrato pode estar corretamente escrito e não ser exigível no
    grafo. Reincidiu três vezes (B3, B4, M7).
    Mitigação: regra mecânica de revisão em
    [Decomposição](E5_0_DECOMPOSITION_AND_DEPENDENCY_GRAPH.md) secao 10.
```

---

## 7. Checklists cumulativos do Master v2.8

Os três checklists foram preenchidos e auditados no plano aprovado, com
resultado `PASS`. Resumo dos pontos que exigem atenção nas etapas:

```text
PIA_OS_SOPHIA_MASTER_COMPATIBILITY
  APPROVAL_GATES_DECLARED             OK, exigível no grafo (D4 + arestas)
  RESOURCE_LIMITS_QUEUE_AND_COST      OK, com queue = NOT_APPLICABLE
  FAILURE_ROLLBACK_AND_CONCURRENCY    OK; obrigações de E5.l declaradas
  MULTI_AI_RESULT_ATTRIBUTION         OK por alegação; entre IAs continua E7
  FROZEN_MODULES_UNCHANGED            OK, medido

SOPHIA_UX_COMPATIBILITY
  RESOURCE_LIMITS_AND_QUEUE           OK, com queue = NOT_APPLICABLE
  RESULT_APPROVAL_AND_PERSISTENCE     OK, com enforcement causal
  PROVIDER_NEUTRALITY_PRESERVED       OK; escolha silenciosa é o caso 23

E5_HANDOFF_RECONCILIATION_COMPATIBILITY
  E4_READ_ONLY_BOUNDARY_PROVED        PROPOSED — a prova é entregável de E5.b
  E6_TO_E9_OWNERSHIP_BOUNDARIES_PROVED PROPOSED — prova em E5.b e E5.t
  demais linhas                        PASS
```

Duas linhas permanecem `PROPOSED` e não `OK` deliberadamente: prova exige
execução, e não há código.

```text
DECLARED != PROVED
```

Não aplicáveis, com causa: interface e distribuição (a E5.0 não cria cliente,
endpoint, stack nem perfil); multi-IA e repasse automático como produto (é E7);
execução, conectores e operações remotas (`E5_EXTERNAL_EFFECT_AUTHORITY = NONE`).
Se alguma etapa futura tocar aquisição real de dado ou acesso a fonte de
orientação, esses checklists deixam de ser não aplicáveis.

---

## 8. Decisões abertas e escolhas deferidas

```text
OPEN_ARCHITECTURAL_DECISIONS = NONE
```

O que permanece aberto é de outra natureza: escolhas de etapa, que nascem no
preflight da própria etapa e não bloqueiam este freeze.

```text
ESCOLHA DE ETAPA                                     NASCE EM
nome exato de runtime do conflito preditivo          preflight de E5.m
campos e tipos concretos do envelope PIAP            preflight de E5.a
mecanismo físico e migration da persistência         preflight de E5.l
forma concreta do CLAIM_EVALUATION_RESULT            preflight de E5.c e E5.j
fixtures sintéticos do El Niño e SIN 2027            preflight de E5.q e E5.t
```

---

## 9. O que este freeze não faz

```text
E5_0_FREEZE_DOCUMENTS = FREEZE_CANDIDATE_PENDING_INDEPENDENT_AUDIT
PRODUCTION_CODE_WRITTEN = NO
TEST_CODE_WRITTEN = NO
MIGRATION_CREATED = NO
SCHEMA_ENUM_OR_API_CREATED = NO
E5_RUNTIME_IMPLEMENTED = NO
E5_IMPLEMENTATION = NOT_STARTED
```

O preflight E5.0 não alterou nenhum arquivo do repositório: as quatro tentativas
de plano viveram fora da árvore, e as medições usaram clones descartáveis. Este
freeze documental é o primeiro delta da E5 no repositório, e cria apenas
documentos.

```text
FREEZE_DOCUMENT != IMPLEMENTATION
PLAN_PASS != IMPLEMENTATION_PASS
IMPLEMENTER_REPORT != INDEPENDENT_AUDIT
NEXT_STAGE != AUTOMATIC
```
