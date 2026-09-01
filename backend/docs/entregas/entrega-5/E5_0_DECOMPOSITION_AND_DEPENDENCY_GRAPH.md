# E5.0 — Decomposição e Grafo de Dependências

Retorno ao índice: [E5.0 — Architectural Documentary Freeze](E5_0_ARCHITECTURE_FREEZE.md)

```text
E5_INTERNAL_DECOMPOSITION = FROZEN_AS_ARCHITECTURAL_PROPOSAL
NENHUMA ETAPA ABRE SEM PASS_FINAL DA ANTERIOR E AUTORIZAÇÃO EXPRESSA
```

---

## 1. Aviso sobre os rótulos

Os rótulos `E5.a` a `E5.t` são identificadores, **não** sequência de execução e
**não** numeração canônica de entrega. Foram escolhidos próprios justamente para
não colidir com as duas tabelas `E5.0`–`E5.12` das fontes v1.2, que se
contradizem entre si — em uma, `E5.4` é o estimador de acessibilidade; na outra,
é o detector de mudança de regime.

```text
HANDOFF_STAGE_TABLE = INPUT_TO_E5_PLAN
HANDOFF_STAGE_TABLE = NOT_CANONICAL_DELIVERY_SEQUENCE
GRAPH_DEFINES_ORDER = TRUE
ALPHABETICAL_LABEL_ORDER != EXECUTION_ORDER
```

Em particular, o grafo determina `E5.k -> E5.j -> E5.m`. A ordem alfabética
diverge do grafo de propósito: trocar os rótulos exigiria reescrever dezenas de
referências cruzadas em gates, kill tests e escopos negativos, e cada reescrita
seria uma chance de introduzir divergência. Onde ordem visual e correção
estrutural competem, prevalece a segunda.

---

## 2. Tabela de decomposição

| ID | Nome | Owner | Entradas | Saídas | Escopo negativo |
|---|---|---|---|---|---|
| **E5.a** | PIAP Envelope e Version Contract | E5 | contratos E4 read-only | envelope versionado, porta read-only tipada | não interpreta ciência; não escreve E4; não é envelope de repasse multi-IA |
| **E5.b** | Read-Only Boundary e Naming Guards | E5 | E5.a | guardas estáticas de fronteira e nomenclatura, com mutantes | não altera E4; não introduz capacidade |
| **E5.c** | Claim Contract | E5 | E5.a | alegação: alvo, sinal, horizonte, instante, regime, proveniência, pressupostos, restrições | não estima; não compara alegações |
| **E5.d** | Channel Registry e classe (C,S) | E5 | E5.c | registro de canais e biblioteca pré-registrada | não mede |
| **E5.e** | Causal Availability Gate | E5 | E5.d | `avail(Z,t,Delta)`; rejeição ANTES do estimador | não estima; não pondera |
| **E5.f** | Historical Validity | E5 | E5.e | `R(k->t)`, `V_t`, `K_history` | não apaga; não escreve E4; `K_history` transiente |
| **E5.g** | Regime Assessment | E5 | E5.f | `D_regime`, theta, candidato de mudança | não confirma sozinho; não reconfigura |
| **E5.h** | Accessibility Estimator A- | E5 | E5.e, E5.f | `A-` mais evidência | não classifica estado |
| **E5.i** | Null, Placebo e Power | E5 | E5.h | `A*_worst`, multiplicidade, alpha corrigido | não classifica estado |
| **E5.k** | Horizon Spectrum | E5 | E5.h | `H_pred(R_t)`, `Delta_cont`, `R_pred` | não roteia; não classifica |
| **E5.j** | Epistemic State Classification and Claim Evaluation Assembly | E5 | E5.c + E5.f + E5.g + E5.h + E5.i + E5.k | os TRÊS estados por alegação **e** `CLAIM_EVALUATION_RESULT` montado e imutável | não roteia; não compara alegações; não pondera; não recalcula componentes |
| **E5.l** | Reconfiguration Gate | E5 | E5.g + `CLAIM_EVALUATION_RESULT` + metadados de aprovação do PIAP | candidato, validação cega, versão, rollback; promoção SOMENTE com referência válida, vigente, compatível e no escopo | não troca provedor; não retreina em silêncio; não concede aprovação |
| **E5.m** | Claim Conflict e Commensurability | E5 | `CLAIM_EVALUATION_RESULT` de E5.j, para todas as alegações comparadas | comensurabilidade, conflito real x falso, restrição decisiva | não faz média, voto ou escolha; não arbitra provedor |
| **E5.n** | Primary Conclusion Candidate / Claim-Level Assertiveness | E5 | E5.m | conclusão principal candidata; assertividade POR ALEGAÇÃO | não decide pelo usuário; não é UX; não é a assertividade final |
| **E5.o** | Protective Candidates and Materiality | E5 | E5.n + `CLAIM_EVALUATION_RESULT` + metadados de materialidade e autoridade do PIAP | candidatos ACEITOS, REJEITADOS e NÃO RESOLVIDOS, com razão e proveniência; `MATERIALITY_STATUS` por ramo | não expande artificialmente; não executa; não omite em silêncio |
| **E5.p** | Emergency Guidance Provenance Validation | E5 | E5.o + entrada OPCIONAL de orientação via PIAP | resultado tipado: valid, missing, stale, invalid, jurisdiction/version mismatch | não gera instrução; não adquire nem escolhe fonte |
| **E5.q** | Counterfactual and Complete Candidate Assembly | E5 | E5.n + E5.o + E5.p | A0, A1, A2 em base comparável, sobre candidatos completos e validados | não executa; não contrata; não gasta |
| **E5.r** | Total Burden Vector, Incidence e Dominance | E5 | E5.q | vetor de 6 dimensões, incidência, dominância, trade-offs | não monetiza; não pondera; não agrega |
| **E5.s** | Final Recommendation and Response Routing | E5 | `CLAIM_EVALUATION_RESULT` + E5.l + E5.n + E5.o + E5.p + E5.r + metadados de aprovação e autoridade do PIAP | rota por alegação e rota composta, RECOMENDADAS; assertividade FINAL revalidada; `ROBUST` somente com limites autorizados ou validados; rota ou `NO_SAFE_ROUTE` | não executa; não escolhe IA; não produz efeito externo |
| **E5.t** | Final Integration e Kill Gate | E5 | todas | 45 kill tests, fixture composto, mutantes, aceitação, pacote | não implementa capacidade nova; não declara prova de E9 |

---

## 3. Grafo de dependências

### 3.1 Cadeia de recomendação e o portão de proveniência

```text
E5.k Horizon Spectrum
  <- E5.h

E5.j Epistemic State Classification and Claim Evaluation Assembly
  <- E5.c + E5.f + E5.g + E5.h + E5.i + E5.k
  -> CLAIM_EVALUATION_RESULT
     = claim + provenance + regime + evidence + uncertainty + horizon + state

E5.m Claim Conflict
  <- CLAIM_EVALUATION_RESULT de E5.j, para todas as alegações comparadas

E5.n Primary Conclusion Candidate / Claim-Level Assertiveness
  <- E5.m

E5.o Protective Candidates and Materiality
  <- E5.n + CLAIM_EVALUATION_RESULT + PIAP materiality/authority metadata
  -> accepted + rejected + unresolved candidates, all with reasons/provenance

E5.p Emergency Guidance Provenance Validation
  <- E5.o + optional PIAP guidance input
  -> valid | missing | stale | invalid | jurisdiction/version mismatch

E5.q Counterfactual and Complete Candidate Assembly
  <- E5.n + E5.o + E5.p

E5.r Total Burden Vector
  <- E5.q

E5.s Final Recommendation and Response Routing
  <- CLAIM_EVALUATION_RESULT + E5.l + E5.n + E5.o + E5.p + E5.r
     + PIAP approval/authority metadata
  -> final assertiveness revalidated; route or NO_SAFE_ROUTE
  -> ROBUST somente com limites autorizados ou validados

E5.t Final Integration / Kill Gate
  <- all stages
```

```text
NO_MATERIAL_GUIDANCE_BRANCH_REACHES_E5_q_r_OR_s_WITHOUT_EXPLICIT_E5_p_RESULT = TRUE
MISSING_STALE_OR_INVALID_GUIDANCE_REMAINS_USEFUL = TRUE
MISSING_STALE_OR_INVALID_GUIDANCE_AUTHORIZES_ONLY_REFERRAL_OR_DETAIL_ABSTENTION = TRUE
E5_t_DOES_NOT_SUBSTITUTE_A_MISSING_EDGE = TRUE
```

Um validador cujo resultado não precisa chegar ao consumidor não é um portão.

```text
DOCUMENTED_VALIDATOR_WITHOUT_REQUIRED_DOWNSTREAM_EDGE != ENFORCED_GATE
```

O gate final PODE detectar que a proveniência não foi validada, mas detectar
depois não torna a validação obrigatória no caminho operacional. A
obrigatoriedade está na aresta, não no teste.

### 3.2 Portão de autoridade

```text
E5.l <- E5.g + CLAIM_EVALUATION_RESULT + PIAP approval metadata
E5.o <- E5.n + CLAIM_EVALUATION_RESULT + PIAP materiality/authority metadata
E5.s <- CLAIM_EVALUATION_RESULT + E5.l + E5.n + E5.o + E5.p + E5.r
        + PIAP approval/authority metadata
```

```text
NO_PROMOTION_IN_E5_l_WITHOUT_VALIDATED_PIAP_APPROVAL_METADATA = TRUE
NO_ROBUST_ROUTE_IN_E5_s_WITHOUT_VALIDATED_BOUNDS_AND_AUTHORITY = TRUE
MISSING_EXPIRED_MISMATCHED_OR_OUT_OF_SCOPE_APPROVAL_BLOCKS_PROMOTION_BOUND_AND_ROBUST = TRUE
APPROVAL_VALIDATION_FAILURE != AUTHORIZATION_TO_INVENT_APPROVAL
DOCUMENTED_APPROVAL_GATE_WITHOUT_REQUIRED_INPUT_EDGE != ENFORCED_APPROVAL_GATE
```

O limite material e a promoção continuam vivendo nos seus próprios objetos. O
PIAP transporta a REFERÊNCIA de autoridade e o VÍNCULO com o objeto, sem
duplicar a fonte de verdade. Ver
[Architecture Freeze](E5_0_ARCHITECTURE_FREEZE.md) secao 3.

---

## 4. Dependências que não são negociáveis

```text
E5.b ANTES de qualquer ciência
     a guarda de fronteira e de nomenclatura precisa existir antes do primeiro
     módulo que possa violá-la. Foi assim que a E4 fechou G17 e MD6.

E5.c ANTES de E5.e..E5.j
     sem a alegação como unidade, os gates rodam sobre pergunta composta e o
     resultado por alegação fica irrecuperável.

E5.e ANTES de E5.f, E5.g e E5.h
     torna a ausência de vazamento estrutural, inclusive para variáveis de regime.

E5.i ANTES de E5.j
     impede a conversão proibida de A- <= 0 em PREDICTIVELY_INACCESSIBLE.

E5.k ANTES de E5.j
     o horizonte é um dos sete componentes do CLAIM_EVALUATION_RESULT.

E5.j ANTES de E5.l e de E5.m
     E5.j é o PRODUTOR do CLAIM_EVALUATION_RESULT. Nomear um momento não define
     um produtor, e consumidor nenhum materializa a própria entrada.
     NAMED_COMPOSITE_INPUT_WITHOUT_PRODUCER != IMPLEMENTABLE_DEPENDENCY_GRAPH

E5.q e E5.r ANTES de E5.s
     o router não pode concentrar o contrafactual. Se o contrafactual vivesse
     dentro do router, G18 não teria objeto próprio e não haveria como provar
     independentemente que a inação foi comparada.
```

### 4.1 Notas de desenho por etapa sensível

`E5.j`, `E5.n` e `E5.s` são value objects com função pura ou parcial pura, não
managers. `E5.s` é função PARCIAL: devolve rota ou `NO_SAFE_ROUTE`.

`E5.j` monta, não interpreta. A montagem é composição imutável dos sete
componentes já produzidos a montante; não recalcula regime, não reestima
evidência, não reduz incerteza e não trunca horizonte. Componente ausente é
defeito, não valor vazio.

`E5.l` é a única etapa que pode precisar de persistência própria — versão,
proveniência, aprovação e rollback. Persistência da E5, com ownership e
repository/port PRÓPRIOS (D3). Reuso ou escrita de `ApprovalRecord` da E4 é
proibido. Obrigações de concorrência declaradas: version check atômico,
prevenção de dupla promoção concorrente, idempotência, aprovação vinculada à
versão e rollback auditável.

`E5.p` nunca falha por ausência de entrada; a entrada é opcional e `missing` é
resultado válido. O mesmo vale para os metadados de aprovação em `E5.l` e `E5.s`.

`E5.r` não produz score. Produz vetor, incidência e relação de dominância.

Obrigações de não omissão de `E5.o`, `E5.q`, `E5.r` e `E5.s` em
[Completude e proteção](E5_0_COMPLETENESS_AND_PROTECTION.md) secao 8.

---

## 5. Caracterização bilateral

A E5 é código novo. Nenhuma sonda falha antes e passa depois no sentido
clássico, porque antes não havia nada. Alegar que um teste falhava quando ele
apenas não existia é proibido.

```text
PARTE 1 — CARACTERIZAÇÃO DE AUSÊNCIA
  instrumento que reprova se a capacidade da etapa JÁ existir na baseline.
  Medição obrigatoriamente TRILATERAL:
     baseline anterior   -> N/N  (todas as sondas acusam ausência)
     candidato da etapa  -> 0/N  (capacidade presente e correta)
     raiz inválida       -> INSTRUMENT_INVALID (exit próprio)

PARTE 2 — CLASSIFICAÇÃO HONESTA DE CADA TESTE
     NEW_CONTRACT_TEST     não existia antes; não falhava
     DEFECT_PROVING        falha medida contra o pai, por execução
     REGRESSION_GUARD      passa nos dois lados, e isso é reportado
     INSTRUMENT_MUTANT     m99_*
  A classificação vem de EXECUÇÃO contra o pai, nunca de afirmação.
```

```text
GUARDA_SEM_MUTANTE = GUARDA_NAO_VERIFICADA
STATIC_NAMING_AND_BOUNDARY_GUARDS_REQUIRE_MUTANTS = TRUE
```

---

## 6. Distribuição dos 45 kill tests

```text
KILL_TEST_COUNT = 13 + 10 + 10 + 12 = 45
```

### 6.1 Casos 1 a 13 — fontes v1.2

| # | Caso | Etapa | Resultado exigido |
|---:|---|---|---|
| 1 | uniform negative | E5.j | nunca `PREDICTABLE` |
| 2 | positive synthetic | E5.h, E5.j | `PREDICTABLE` |
| 3 | weak signal | E5.i | `UNRESOLVED`, nunca inacessível |
| 4 | real positive | E5.t | `PREDICTABLE` |
| 5 | real negative conforme potência | E5.t | inacessível ou unresolved |
| 6 | future leakage rejection | E5.e | `avail=0` implica REJECT antes do estimador |
| 7 | periodic / discontinuous horizon | E5.k | `H_pred` descontínuo, sem falso `Delta_C` |
| 8 | response routing sem recusa simples | E5.s | inacessível não produz recusa quando há rota robusta |
| 9 | abrupt regime shift | E5.g | detectar perda de validade |
| 10 | false regime shift | E5.g | NO RECONFIGURE |
| 11 | recoverable shift | E5.l | OLD -> RECONFIGURE -> PREDICT, **e somente com aprovação válida**; reprova se a promoção ocorrer com aprovação ausente, expirada, de versão divergente ou fora de escopo |
| 12 | unrecoverable shift | E5.l | INVESTIGATE ou ROBUST |
| 13 | old-but-relevant | E5.f | idade não é irrelevância |

### 6.2 Casos 14 a 23 — conflito e assertividade

Tabela completa em
[Conflito e assertividade](E5_0_CONFLICT_AND_ASSERTIVENESS.md) secao 7.

### 6.3 Casos 24 a 33 — completude e proteção

Tabela completa em
[Completude e proteção](E5_0_COMPLETENESS_AND_PROTECTION.md) secao 10, incluindo
a exigência 33b, que é adicional ao caso 24 e **não** cria um 46º caso.

### 6.4 Casos 34 a 45 e fixture composto — custo total

Tabela completa e fixture em
[Custo total e contrafactual](E5_0_TOTAL_BURDEN_AND_COUNTERFACTUAL.md)
secoes 7 e 8.

---

## 7. Mutantes de instrumento

Nenhum caso novo. A contagem permanece 45 mais o fixture composto.

```text
m99_claim_evaluation_result_incompleto
   entrada sintética em que um dos SETE componentes falta.
   O instrumento deve REPROVAR. Componente ausente é defeito de montagem,
   não valor vazio.  Ancorado em E5.j.

m99_approval_metadata_invalido
   quatro entradas sintéticas: ausente, expirada, versão divergente e escopo
   insuficiente. O instrumento deve REPROVAR promoção em E5.l e `ROBUST` em
   E5.s nos quatro casos, e deve DISTINGUIR os quatro na saída tipada.
   Ancorado em E5.l e E5.s; exercitado pelos casos 11, 17 e 18.
```

```text
MUTANTE != NOVO_KILL_TEST
KILL_TEST_COUNT = 45  (inalterado)
```

---

## 8. Matriz G0 a G18

`X` = aplicável. `-` = `NOT_APPLICABLE`, com justificativa abaixo.

| Gate | a | b | c | d | e | f | g | h | i | j | k | l | m | n | o | p | q | r | s | t |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| G0 Autoridade | X | X | X | X | X | X | X | X | X | X | X | X | X | X | X | X | X | X | X | X |
| G1 Integridade | X | X | X | X | X | X | X | X | X | X | X | X | X | X | X | X | X | X | X | X |
| G2 Identidade | X | X | X | X | X | X | X | X | X | X | X | X | X | X | X | X | X | X | X | X |
| G3 Escopo | X | X | X | X | X | X | X | X | X | X | X | X | X | X | X | X | X | X | X | X |
| G4 Contratos | X | X | X | X | X | X | X | X | X | X | X | X | X | X | X | X | X | X | X | X |
| G5 Caracterização | X | X | X | X | X | X | X | X | X | X | X | X | X | X | X | X | X | X | X | X |
| G6 Testes | X | X | X | X | X | X | X | X | X | X | X | X | X | X | X | X | X | X | X | X |
| G7 Dados | - | - | - | - | - | - | - | - | - | - | - | X | - | - | - | - | - | - | - | X |
| G8 PIAP | X | X | X | - | - | - | - | - | - | X | - | X | - | X | X | X | - | - | X | X |
| G9 COUT-P | - | - | X | X | X | X | X | X | X | X | X | X | X | - | - | - | - | - | X | X |
| G10 Temporalidade | - | - | X | - | X | X | X | X | X | - | X | X | X | - | X | X | X | - | - | X |
| G11 Roteamento | - | X | - | - | - | - | - | - | - | X | - | - | X | X | - | - | - | - | X | X |
| G12 Reconfiguração | - | - | - | - | - | - | X | - | - | - | - | X | - | - | - | - | - | - | X | X |
| G13 Fronteiras | X | X | X | X | X | X | X | X | X | X | X | X | X | X | X | X | X | X | X | X |
| G14 Produto | - | - | - | - | - | - | - | - | - | - | - | - | X | X | X | X | X | X | X | X |
| G15 Reprodutibilidade | X | X | X | X | X | X | X | X | X | X | X | X | X | X | X | X | X | X | X | X |
| G16 Conflito/assertividade | - | X | X | - | - | - | X | - | - | X | - | - | X | X | X | - | X | - | X | X |
| G17 Completude/proteção | - | X | - | - | - | - | - | - | - | - | - | - | X | X | X | X | X | X | X | X |
| G18 Custo total/ação-inação | - | X | - | - | - | - | - | - | - | - | - | - | - | X | X | - | X | X | X | X |

Justificativas dos `NOT_APPLICABLE`:

```text
G7 Dados
   só E5.l tem persistência própria e só E5.t exercita o pacote completo.
   As demais não criam tabela nem migration, e criar uma só para satisfazer o
   gate seria código artificial para simular compatibilidade.

G8 PIAP
   aplica-se onde o envelope é definido, atravessado, montado ou validado:
   E5.a que o cria, E5.b que o guarda, E5.c que descreve a alegação
   transportada, E5.j que monta a proveniência dentro do
   CLAIM_EVALUATION_RESULT, E5.l que valida os metadados de aprovação antes de
   promover, E5.n e E5.s que produzem o envelope de saída, E5.o que consome os
   metadados de materialidade e autoridade, E5.p que valida proveniência de
   orientação, e E5.t.
   Marcar G8 como NOT_APPLICABLE numa etapa que consome metadados PIAP é
   contradição entre a matriz e o grafo, e é Stop Condition própria.
   As etapas puramente estimativas — E5.d a E5.i, E5.k, E5.q e E5.r — consomem
   dados já desembrulhados e não redefinem semântica de protocolo.

G9 COUT-P
   aplica-se ao núcleo científico, E5.c a E5.m mais o router e o gate final.
   E5.a, E5.b, E5.n, E5.o, E5.p, E5.q e E5.r não produzem estado epistêmico nem
   tocam Power Gate, multiplicidade ou audit trail científico.

G10 Temporalidade
   aplica-se onde disponibilidade, regime ou transportabilidade importam,
   inclusive em E5.o e E5.p (janela e validade da orientação) e E5.q (base
   comparável exige mesmo horizonte). Não se aplica a E5.r, que recebe
   alternativas já normalizadas no tempo, nem a E5.j, que classifica sobre
   medidas já produzidas.

G11 Roteamento
   estado, rota e execução. E5.j produz estado e não pode produzir rota; E5.m e
   E5.n não podem produzir rota nem execução; E5.s e E5.t fecham; E5.b guarda
   estaticamente a separação.

G12 Reconfiguração
   E5.g detecta candidato, E5.l governa promoção e rollback, E5.s roteia
   RECONFIGURE e E5.t fecha.

G14 Produto
   resposta útil sem ação forçada ou overclaim. Aplica-se de E5.m em diante,
   quando já existe algo apresentável ao usuário.

G16, G17 e G18
   aplicam-se às etapas que criam o objeto correspondente, ao router, ao gate
   final e a E5.b. A presença de E5.b nos três é deliberada: não escolher
   provedor, não produzir efeito externo e não executar comparação são
   mensuráveis estaticamente, e guarda estática é mais barata e mais difícil de
   burlar que teste de runtime.
   G16 aplica-se também a E5.q, que recebe a conclusão candidata e não pode
   apagar a restrição decisiva nem a incerteza por alegação ao compor A0, A1 e
   A2. G17 aplica-se também a E5.r, porque medir ônus de um ramo cuja orientação
   é stale sem carregar esse resultado reintroduziria o defeito um passo adiante.
```

Cada plano de etapa deverá reapresentar sua própria coluna com comandos,
fixtures, resultados esperados e Stop Conditions. `NOT_APPLICABLE` sem
justificativa é defeito de plano.

---

## 9. Stop Conditions cumulativas

Valem integralmente as do kit E5 v2.8, nos **nove** blocos: (1) autoridade e
sequência; (2) PIAP e fronteiras; (3) ciência e temporalidade; (4) estado, rota
e execução; (5) conflitos e assertividade; (6) completude e proteção; (7) custo
total e ação-inação; (8) regime e reconfiguração; (9) auditoria e produto.

### 9.1 Da auditoria do plano

```text
SC-1  usar qualquer kit anterior a v2.8 como autoridade
SC-2  incluir ABSTAIN no conjunto RESPONSE_ROUTE
SC-3  omitir G16, G17 ou G18
SC-4  omitir qualquer um dos 32 kill tests v2.6 a v2.8
SC-5  confundir PIAP com AIHandoffEnvelope ou orquestração E7
SC-6  iniciar código, teste, migration, schema, enum, API, commit ou escrita
SC-7  entregar arquivo que não seja UTF-8 válido
SC-8  declarar PASS_FINAL no retorno do implementador
```

### 9.2 Do preflight E5.0

```text
SC-E5.0-A  símbolo de runtime com prefixo COUT_P ou COUTP
SC-E5.0-B  INACCESSIBLE sem qualificação para o estado epistêmico
SC-E5.0-C  tipo de conflito preditivo nomeado apenas Conflict
SC-E5.0-D  guarda de fronteira ou nomenclatura sem mutante próprio
SC-E5.0-E  guarda de ausência que meça só nome de definição e seja reportada
           como prova de ausência de capacidade
SC-E5.0-F  K_history materializado como coluna, flag ou estado em E3 ou E4
SC-E5.0-G  A*_worst reportado como cota universal, sem a ressalva (C,S)
SC-E5.0-H  etapa que reuse a numeração E5.x das fontes sem dizer de qual tabela
SC-E5.0-I  alteração em backend/app, backend/alembic ou migrations da E3 para
           preparar a E5
SC-E5.0-J  gate reportado sem o comando literal, ou executado antes da última
           mudança do artefato
SC-E5.0-K  resposta composta que sobrescreve estado, rota, evidência ou
           incerteza por alegação
SC-E5.0-L  fixture El Niño e SIN em 2027 apresentado como previsão real,
           evidência setorial ou limite autorizado
SC-E5.0-M  entrega sem validação UTF-8 estrita após a última alteração
SC-E5.0-N  ramo com orientação material alcançando E5.q, E5.r ou E5.s sem
           resultado explícito de E5.p
SC-E5.0-O  ramo UNRESOLVED incluído ou excluído em silêncio, ou resposta
           apresentada como COMPLETA havendo qualquer ramo UNRESOLVED
SC-E5.0-P  gate final E5.t usado como substituto de aresta ausente no grafo
SC-E5.0-Q  E5.p exigindo entrada de orientação para operar, ou escolhendo ou
           adquirindo fornecedor
SC-E5.0-R  reuso ou escrita de ApprovalRecord da E4 pela E5
SC-E5.0-S  fórmula de L_total tratada como implementação numérica autorizada
```

### 9.3 Da reauditoria

```text
SC-T3-A  consumir CLAIM_EVALUATION_RESULT sem produtor e sem arestas para os
         sete componentes obrigatórios
SC-T3-B  promover em E5.l, ou retornar ROBUST em E5.s, sem consumir e validar
         os metadados de aprovação e autoridade transportados pelo PIAP
SC-T3-C  marcar G8 como NOT_APPLICABLE em etapa que consome metadados PIAP
SC-T3-D  declarar E5.o como único componente sujeito a falha por omissão
```

---

## 10. Regra mecânica R10

Três achados de auditoria — proveniência sem aresta de saída, aprovação sem
aresta de entrada e objeto composto sem produtor — foram da mesma classe:
contrato corretamente escrito e não exigível no grafo. Enunciar o invariante em
prosa não bastou para aplicá-lo.

Regra de revisão obrigatória, mecânica e não de julgamento:

```text
1. Para CADA invariante na forma "X impede Y" ou "Y exige X", verificar que
   existe aresta entregando X à etapa que decide Y.
2. Para CADA objeto composto nomeado, verificar que existe uma etapa que o
   PRODUZ, com aresta para cada componente.
3. Toda etapa declara quem CONSOME sua saída, não apenas o que produz.

DOCUMENTED_VALIDATOR_WITHOUT_REQUIRED_DOWNSTREAM_EDGE != ENFORCED_GATE
DOCUMENTED_APPROVAL_GATE_WITHOUT_REQUIRED_INPUT_EDGE != ENFORCED_APPROVAL_GATE
NAMED_COMPOSITE_INPUT_WITHOUT_PRODUCER != IMPLEMENTABLE_DEPENDENCY_GRAPH
```

Um componente cuja saída não tem consumidor obrigatório é relatório paralelo, e
relatório paralelo não é portão.
