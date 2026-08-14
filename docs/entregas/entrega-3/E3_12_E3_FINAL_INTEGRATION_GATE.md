# E3.12 — FINAL INTEGRATION GATE (Entrega 3)

**Módulo:** E3.12 / AWP-E3-INTEGRATION
**Patch:** `e3-12-e3-final-integration-gate.patch` (34º da cadeia)
**Natureza:** testes de integração + documentação + manifests.
**Produção modificada:** NÃO. **Migração nova:** NÃO. **Feature nova:** NÃO.

---

## 1. Missão

A E3.12 não constrói nada. Ela existe para provar que o que foi
construído separadamente em `E3.1`–`E3.11` funciona **como um sistema
integrado**, e para demonstrar formalmente o gate `E3 → E4`.

A distinção é importante e não é retórica: cada módulo anterior provou
uma propriedade **isoladamente**. Nada até aqui provava que a
composição delas preserva o que cada uma preserva sozinha. Um sistema
pode ter identidade correta, linhagem correta, proveniência correta e
sincronização correta — e ainda assim perder história na junção.

---

## 2. Inventário pré-integração (§2)

Auditado por inspeção do repositório real, não por documentação
histórica de contagem.

| Módulo | Componente | Status real na árvore |
|---|---|---|
| E3.1 / LIB-01 | Object Repository | implementado (+E3.1.1, E3.1.2) |
| E3.2 / LIB-02 | COID Manager | implementado (+E3.2.1) |
| E3.3 / LIB-03 | CLID / Lineage | implementado (+E3.3.1) |
| E3.4 / LIB-04 | Version / Transformation | implementado (+E3.4.1, E3.4.1a) |
| E3.5 / LIB-05 | Relationship | implementado (+E3.5.1, E3.5.2, E3.5.2a) |
| E3.6 / LIB-06 | Provenance / Accessibility | implementado (+E3.6.1, .1a–.1d, E3.6.2, E3.6.2a) |
| E3.7 / LIB-07 | Index | implementado |
| E3.8 / LIB-08 | Search | implementado |
| E3.9 / LIB-09 | Causal History | implementado (+E3.9.1, E3.9.1a) |
| E3.10 / LIB-10 | Integrity | implementado (+E3.10.1) |
| E3.11 / LIB-11 | Synchronization | implementado (+E3.11.1, E3.11.1a) |

**Volume real do domínio cognitivo:** 7 models, 10 repositories,
11 services, 4 schemas, 2 módulos de erro, 13 migrations, 42 arquivos
de teste cognitivo, 6.444 linhas em `app/cognitive/`.

---

## 3. Cadeia de patches (§3)

```
PATCHES_PRESENT        = 33/33 (+ este = 34)
PATCHES_APPLY_IN_ORDER = PASS
NO_PATCH_REWRITTEN     = TRUE
NO_SQUASH              = TRUE
BASELINE_HEAD          = 7de327a  (E1/E2, Módulo 2.13)
HEAD ANTES DA E3.12    = bf9788c  (E3.11.1a)
```

Um commit por patch, aplicados em ordem sobre a baseline E1/E2, em
clone limpo e independente.

---

## 4. Alembic (§4, §42)

```
ALEMBIC_SINGLE_HEAD = c9a3f61b74d2
REVISÕES            = 13
ORPHAN_REVISIONS    = NONE
DUPLICATE_IDS       = NONE
DOWN_REVISION_CHAIN = íntegra, linear
```

**Executado contra PostgreSQL 16.14 real:**

- `fresh database → alembic upgrade head` — PASS;
- ciclo `head → base → head` em banco **vazio** — PASS (as guardas
  permitem downgrade quando não há história a perder);
- downgrade com **história presente** — corretamente **BLOQUEADO**
  (`SEMANTICALLY_BLOCKED`), cadeia permanece em `c9a3f61b74d2`.

As guardas de E3.5.2, E3.6.1 e E3.9 continuam alcançáveis a partir da
head atual. Nenhuma migração publicada foi editada.

---

## 5. Contrato COUT-PIA — matriz normativa congelada (§5)

Cada princípio abaixo é aqui **comportamento testável**, não afirmação
documental. A coluna "onde" aponta o teste que o demonstra.

| Código | Princípio | Onde |
|---|---|---|
| COUT-P1 | Distinction preservation | G2 |
| COUT-P2 | Continuity preservation | G1, G1b |
| COUT-P3 | Provenance preservation | G5, G1b |
| COUT-P4 | Multiple history preservation | G8, G2 |
| COUT-P5 | Transformation preservation / declared loss | G1b |
| COUT-P6 | Accessibility != existence | G10, G11 |
| COUT-P7 | Equivalence != destructive collapse | G2 |
| COUT-P8 | Incomparable / unresolved são válidos | G11, G15(A) |
| COUT-P9 | COUT informa; não decide | G17 |
| COUT-P10 | Memória cognitiva persistente pertence ao PIA-OS | G6, G17 |

---

## 6. Regras COUT transversais (§6)

Congeladas e verificadas:

```
SAME CURRENT STATE          != SAME CAUSAL HISTORY      (G2)
ACCESSIBILITY               != EXISTENCE                (G10)
TEMPORAL PRECEDENCE         != CAUSALITY                (G8)
HISTORY BOUNDARY            != CAUSAL BOUNDARY          (G8)
DIVERGENCE                  != INVALIDITY               (G15 A vs B)
TRANSMISSION                != OVERWRITE                (G1, G14)
DISTINCTION EXTINCTION      != HISTORICAL ERASURE       (G10)
MISSING EVIDENCE            != AUTHORIZATION TO FABRICATE (G11)
INTERNAL CONSISTENCY        != TRUTH ABOUT REALITY      (documental — E3.10)
```

---

## 7. O que COUT **não** é (§7)

Confirmado por varredura de código executável (teste G17):

```
COUT_DECISION_ENGINE            = NONE
COUT_GLOBAL_SCORE               = NONE
A_R_P_T_CANONICAL_SCORE         = NONE
COUT_PROVIDER_SELECTOR          = NONE
COUT_KERNEL_DECISION_DEPENDENCY = NONE
```

Reforço estrutural verificado: **nenhum módulo fora de
`app/cognitive/` importa `app.cognitive`**. Kernel, runtime e
scheduler não interpretam semântica COUT porque sequer conhecem o
domínio cognitivo.

---

## 8. Testes da E3.12

Arquivo único: `tests/integration/cognitive/test_e3_12_final_integration_gate.py`
— 23 testes, todos contra PostgreSQL real, duas instâncias reais.

| Teste | Seção do prompt | O que prova |
|---|---|---|
| G1 | §8, §9, §24, §47 | Pipeline completo com `P_after == P_before` e origem intacta |
| G1b | §9 | Continuidade sobrevive a transformação **e** transmissão |
| G2 | §10, §48 | Retenção de distinção entre trajetórias equivalentes |
| G3 | §11 | Branch/merge reconstruível após sync |
| G4 | §12 | CURRENT/SUPERSEDED coexistem; SUPERSEDED não é corrupção |
| G5 | §13 | Proveniência ponta a ponta; provider/model NULL válidos |
| G6 | §14 | `PROVIDER_NEUTRAL_DOMAIN` — sem import nem ramo por fornecedor |
| G7 | §15 | Relações: retirada, recriação, ciclo legítimo, semântica idêntica |
| G8 | §16 | One history per subject, cross-history predecessor, occurred_at nullable |
| G9 | §18 | Galaxy Trace atravessa a transmissão |
| G10 | §19 | Broken Glass — história sobrevive à extinção da distinção |
| G11 | §20 | Não-fabricação epistêmica |
| G12 | §21, §24 | Search/Index derivados, read-only, censo idêntico |
| G13 | §22 | Integrity detecta e **não** repara |
| G14 | §23 | Round-trip idempotente, zero overwrite |
| G15 | §49 | **Negative strong gate** — 5 defeitos, 5 diagnósticos distintos |
| G16 | §25 | `TRANSCRIPT_AUTO_STORAGE = NONE` no schema real |
| G17 | §7 | COUT não-decisional |
| G18 | §26 | Sem primitiva de Metadata cognitivo |
| G19 | §22, §27, §28, §45 | Fronteiras não implementadas continuam não implementadas |
| G20 | §17 | Matriz de garantias do DAG sem overclaim |
| G21 | §50 | Smoke de volume — sem comportamento patológico |
| G22 | §23 | Envelope versionado e export determinístico |

### 8.1 O teste central (G1)

Um patrimônio `P0` único atravessa
`CREATE → TRANSFORM → RELATE → TRACE → SEARCH → INTEGRITY → EXPORT →
IMPORT → SEARCH → INTEGRITY`, e o gate exige três coisas ao mesmo
tempo:

1. `canonical(P_after) == canonical(P_before)` — nada se perde na
   transmissão;
2. o censo da **origem** permanece byte a byte idêntico — transmitir
   não altera quem transmitiu;
3. auditoria de integridade PASS nos dois lados.

`P0` contém simultaneamente: 4 objetos partilhando uma continuidade
(CLID) com 4 identidades (COID) distintas; `CURRENT` + `SUPERSEDED`;
diamante de linhagem O1 → {O2, O3} → O4; proveniência humana, de dois
providers distintos e uma sem provider algum; transformações com
preservação e perda declaradas; os quatro `AccessibilityState`;
múltiplas `CausalHistory`; predecessor atravessando histórias;
múltiplos caminhos causais; Galaxy Trace; Broken Glass.

### 8.2 O negative strong gate (G15)

Cinco classes de defeito, injetadas separadamente:

| Classe | Diagnóstico produzido |
|---|---|
| A. conflito de identidade | `SyncStatus.CONFLICT` + `differing_fields`, zero escritas |
| B. pacote causalmente inválido | `SyncPackageInvalidError` / `PIA-8022`, rejeitado antes de escrever |
| C. corrupção de linhagem | `INTEGRITY-LIN-001` (LINEAGE_CYCLE) |
| D. `actor_ref` pendente | `INTEGRITY-TRF-001` |
| E. vocabulário de acessibilidade inválido | `INTEGRITY-IDN-001` |

A propriedade protegida **não é "detectar"**. É **não colapsar**: cinco
defeitos produzem cinco diagnósticos distintos. Um sistema que
respondesse "inválido" para os cinco destruiria exatamente a distinção
que a E3 existe para preservar — e nenhum teste de detecção sozinho
teria percebido.

### 8.3 Dois achados registrados por honestidade

**(a) Suposição errada sobre propagação de CLID.** Ao escrever G1 eu
havia **assumido** que `O3`, criado por
`derive(..., relation_type=BRANCH)`, não herdaria o CLID de `O1`. O
teste falhou e mostrou que herda: `ClidManager.inherit` propaga a
continuidade inclusive por BRANCH e MERGE.

Isso **não é defeito** — é exatamente o contrato de E3.3 §11
(`COID identity != CLID continuity`: quatro identidades, uma
continuidade). O que foi corrigido foi a **expectativa do teste**, não
o código.

**(b) Teste frágil descoberto na validação em clone limpo.** A versão
inicial de G15(A) mutava `package["objects"][0]` para `latent` e
esperava conflito. Quando esse objeto **já estava** `latent`, as duas
representações ficavam idênticas e o import corretamente reportava
`APPLIED` — o teste falhava por depender de qual objeto viesse
primeiro na ordenação.

O produto estava certo; o teste é que presumia a divergência em vez de
garanti-la. Corrigido para ler o estado atual e escolher um estado
explicitamente diferente. Validado com três execuções isoladas
consecutivas.

Ambos ficam registrados porque um gate final que silenciasse as
próprias suposições erradas seria menos confiável, não mais — e porque
o segundo só apareceu **por causa** da validação em clone limpo, o que
é precisamente a função dela.

---

## 9. Matriz de garantias do DAG (§17)

Classificação **não alterada** por esta entrega. Reafirmada e agora
provada nos dois sentidos por G20:

**Causal:**
```
APPLICATION_STRUCTURAL_DAG    = TRUE
DB_LEVEL_GLOBAL_DAG_GUARANTEE = FALSE
INTEGRITY_GLOBAL_AUDIT        = TRUE
SYNC_PREFLIGHT                = TRUE
```

**Lineage:**
```
DB_SELF_PROTECTION       = TRUE
FULL_DAG_DB_GUARANTEE    = FALSE
INTEGRITY_FULL_DAG_AUDIT = TRUE
```

G20 prova a classificação **nos dois sentidos**: o `UPDATE` direto que
cria o ciclo é aceito pelo banco (logo `DB_LEVEL = FALSE` não é
modéstia retórica) e a auditoria global o encontra (logo
`INTEGRITY_GLOBAL_AUDIT = TRUE` não é promessa vazia).

---

## 10. Evidência canônica de testes (revisado em E3.12.1)

> **Aviso de supersessão.** Todas as contagens de teste publicadas
> antes da E3.12.1 — tanto nesta seção quanto no manifest e no
> relatório externo — são **HISTORICAL / SUPERSEDED EVIDENCE**. Elas
> não eram falsas: cada uma media uma configuração diferente (com e
> sem os testes da E3.12 no tree; com `.env` de conteúdos distintos).
> Mas duas contagens divergentes para o mesmo rótulo `RAW` são um
> defeito documental, e a E3.12.1 existe para eliminá-lo.
>
> A **única evidência normativa** passa a ser
> `E3_12_1_CANONICAL_TEST_RESULT`, abaixo — produzida em execução
> única, em clone limpo, com patches 1–35 aplicados.

### 10.1 Definições sem ambiguidade

**`RAW_ENV`** — clone limpo, patches 1–35 aplicados, **nenhuma
intervenção manual após o clone**, configuração padrão do projeto.
Sem `.env`, sem `chmod`, sem variável de ambiente adicional. Nesta
configuração o projeto não sabe onde está o banco, então os testes que
exigem PostgreSQL real **pulam** — corretamente, pelo `skipif`
declarado neles.

**`NORMALIZED_ENV`** — idêntico ao acima, acrescido **exclusivamente**
da configuração externa legítima que qualquer suíte precisa para
alcançar um banco de teste:

```
ENVIRONMENT=testing
DATABASE_URL=postgresql+psycopg://<user>:<pw>@<host>:<port>/<db>_test
```

exportadas como **variáveis de processo**. Nada mais.

Após o patch 35, três coisas deixaram de fazer parte da normalização:

- **`chmod` manual — proibido.** O bit executável passa a vir do Git
  (`100755` no tree). Se um `chmod` voltasse a ser necessário, o patch
  35 teria falhado no seu único objetivo.
- **Arquivo `.env` — desnecessário.** Passar `DATABASE_URL` como
  variável de processo é a forma mais limpa, e resolve o conflito
  descrito em 10.3.
- **`--deselect` — eliminado.** Nenhum teste é excluído da execução
  canônica. A suíte roda inteira.

### 10.2 Por que o bit de execução não era ambiental

O registro histórico deste projeto classificava as 6 falhas de
`test_script_exists_and_is_executable` como perda do bit na
**descompactação de um ZIP** — e, para aquele veículo de entrega, a
classificação era correta.

Com git bundle ela **deixa de ser verdadeira**. Git registra o modo do
arquivo, e a baseline gravou `100644`:

```
git ls-tree main backend/deploy/scripts/
100644 blob acc5cf24…  backup.sh
100644 blob a1b0d4c0…  healthcheck.sh
100644 blob 7626e452…  restore.sh
100644 blob 800919cb…  start.sh
100644 blob 9d749f6a…  stop.sh
100644 blob 709ebf6f…  wait_for_db.sh
```

O teste que exige `os.X_OK` existe na mesma baseline. Consequência
verificada em clone virgem: **qualquer clone limpo da baseline falhava
6 dos seus próprios testes**, sem qualquer interferência de ambiente.

Isso era defeito real do estado versionado — não artefato de
transporte. Não era **regressão**: a E3 não o causou, e os conjuntos
de falha de baseline e E3 eram idênticos teste a teste
(`E3_REGRESSION_DELTA = 0`).

**Resolução (patch 35):** modo corrigido para `100755` **no estado
final do repositório**, sem tocar um byte do conteúdo dos scripts e
**sem reescrever a história** — o commit da baseline permanece como
sempre foi. O registro histórico continua verdadeiro; o estado final
passa a ser reproduzível.

### 10.3 Por que o `.env` deixou de ser usado

`test_database_url_composed_from_parts_when_db_host_set` remove
`DATABASE_URL` do ambiente e verifica que `Settings` compõe a URL a
partir de partes discretas. Com um arquivo `.env` presente,
`pydantic-settings` o lê e `DATABASE_URL` reaparece — vencendo por
contrato. O teste então falhava, e a E3.12 o tratou com `--deselect`.

Isso nunca foi defeito de código, nem do teste: era a consequência
correta de fornecer a configuração pelo canal errado. Passando
`DATABASE_URL` como **variável de processo**, o `monkeypatch.delenv`
do teste funciona como projetado, o teste passa, e os testes de
PostgreSQL continuam alcançando o banco.

Resultado: o `--deselect` desapareceu, e com ele a última exceção na
contagem canônica.

### 10.4 `E3_12_1_CANONICAL_TEST_RESULT`

Execução única, clone limpo, patches 1–35, PostgreSQL 16.14 real.
Números transcritos da saída do pytest, sem aritmética manual.

*(preenchido na §11 — números idênticos aos do manifest JSON,
verificados por comparação automatizada)*

---

## 11. `E3_12_1_CANONICAL_TEST_RESULT` — números finais

Evidência normativa única. Execução em clone limpo, patches 1–35,
PostgreSQL 16.14 real. Transcrito da saída do pytest, sem aritmética
manual. Idêntico, campo a campo, ao `E3_FINAL_MANIFEST.json`
(verificado por comparação automatizada).

```
RAW_ENV_FULL_SUITE
    collected  = 1054
    passed     = 948
    failed     = 0
    skipped    = 106
    deselected = 0
    warnings   = 7

NORMALIZED_FULL_SUITE
    collected  = 1054
    passed     = 1053
    failed     = 0
    skipped    = 1
    deselected = 0
    warnings   = 7

NORMALIZED_FULL_SUITE_FAILED = 0

BASELINE_SAME_ENV = 6 failed, 448 passed, 1 skipped
E3_FAILURE_SET       = {} (vazio)
BASELINE_FAILURE_SET = {test_script_exists_and_is_executable[×6]}
E3_REGRESSION_DELTA  = 0

COGNITIVE_UNIT_COLLECTED        = 493
COGNITIVE_INTEGRATION_COLLECTED = 105
TOTAL_TESTS_COLLECTED           = 1054

GLOBAL_COVERAGE        = 98,46%
APP_COGNITIVE_COVERAGE = 100%

RUFF  = PASS
BLACK = PASS
MYPY_TOTAL_ERRORS = 7 (todos fora de app/cognitive/)
MYPY_NEW_ERRORS   = 0

POSTGRESQL = 16.14 (Ubuntu 24.04)
DRIVER     = psycopg 3.2.3
SCHEMA_ORM_SYNC         = PASS (compare_metadata: 0 diffs)
PUBLIC_API_IMPORT_AUDIT = PASS (39 módulos, 0 falhas, 0 ciclos)
```

### Notas de leitura honesta

**Os 106 skips do `RAW_ENV` não são falhas nem omissões.** São os
testes que declaram `skipif` para PostgreSQL real e que, sem
`DATABASE_URL`, corretamente não rodam. Um `RAW_ENV` que os executasse
não seria "cru" — teria configuração de banco embutida em algum lugar.

**O 1 skip do `NORMALIZED_ENV`** é
`tests/unit/database/test_concurrency.py:90` — o pool SQLite em
memória (`SingletonThreadPool`) não expõe `checkedout()`. Skip
declarado e justificado desde E1/E2, não intermitente.

**`GLOBAL_COVERAGE` subiu de 98,28% para 98,46%.** Não houve mudança
de código: o teste antes excluído por `--deselect` agora executa e
cobre linhas que antes não eram exercidas. O número anterior era
correto para aquela execução; este é o correto para a execução
canônica.

**`E3_REGRESSION_DELTA = 0` por conjunto vazio.** Depois do patch 35 a
relação deixou de ser "conjuntos idênticos" e passou a ser
estritamente melhor: a E3 não tem nenhuma falha, e corrige as 6 que a
baseline tinha. Delta zero continua verdadeiro — nenhuma falha existe
em E3 que não exista na baseline — mas a leitura mudou e é registrada
para não induzir o auditor a esperar simetria.

---

## 12. Fronteiras — o que a E3 **não** entrega (§27)

Verificado por teste executável (G19), não apenas declarado:

```
CognitiveDistinction                     = DEFERRED
CausalClassRef                           = DEFERRED
CausalComparison                         = DEFERRED
full Accessibility policy                = E4
Governance                               = E4
Compliance / Conformance                 = DEFERRED
Continuous Cognitive Improvement         = DEFERRED
CognitiveExecution                       = E7
Multi-AI Orchestration                   = E7
Artifact Storage                         = DEFERRED
full-text / vector / embedding search    = DEFERRED
input_refs / output_refs referential int.= DEFERRED
external / tombstone policy              = DEFERRED
REPAIR_IMPLEMENTED                       = NO
GOVERNANCE_IMPLEMENTED                   = NO
LEARNING_ENGINE_IMPLEMENTED              = NO
COGNITIVE_DOMAIN_METADATA_PRIMITIVE      = NONE
```

Um gate final que verificasse apenas o que existe deixaria a fronteira
aberta. A promessa da E3 inclui explicitamente o que ela **não** faz.

---

## 13. Aprendizado — fronteira final da E3 (§28)

A E3 **não** implementa learning engine. Os princípios abaixo estão
congelados como orientação futura e **nenhum deles produz
comportamento decisório em E3**:

```
ERROR                != LEARNING
VARIATION            != ERROR
NON_SELECTION        != ERROR
SELECTION            != TRUTH
DISUSE               != HISTORICAL_ERASURE
PIA_LEARNING_SOURCE   = VALIDATED_EXPERIENCE
```

---

## 14. Continuidade cognitiva vs modelo (§29)

Registrado como **objetivo futuro e hipótese tecnológica**, não como
resultado demonstrado:

```
COGNITIVE_CONTINUITY > MODEL_CONTINUITY   ← HIPÓTESE, NÃO RESULTADO
```

A E3 fornece a infraestrutura necessária — identidade, proveniência,
linhagem, história causal, sincronização, neutralidade de provider. Ela
**não** demonstra o avanço empírico. Esse teste pertence a fases
futuras, com modelos efetivamente substituíveis. Nada nesta entrega
autoriza a afirmação mais forte.

---

## 15. CLEO / LOP (§30)

Nenhuma física entrou no software por este gate.

```
NO GR — NO COSMOLOGY — NO HORIZON PHYSICS — NO PHYSICAL COUT VALIDATION
GRAVITATIONAL_LENSING = ANALOGY_ONLY
```

O cenário "Galaxy Trace" é analogia nominal para separar
evento/história de fonte atual. Nenhuma equação física existe em
`app/`.

---

## 16. Stop conditions (§51)

```
STOP_CONDITIONS = NONE
```

Nenhuma das 20 condições ocorreu. Em particular: nenhuma feature nova
foi necessária, nenhum model/schema novo, nenhuma migração nova,
nenhuma história precisou ser apagada para um teste passar, nenhum
conflito precisou de vencedor, e nenhuma afirmação de PASS depende de
teste não executado.

**Defeito reportado em E3.12, resolvido em E3.12.1:** o bit de
execução ausente nos 6 scripts de deploy (§10.2). Na E3.12 foi
reportado e **não** corrigido, conforme §1 exigia. O patch 35
(E3.12.1) o corrige no estado final do repositório —
`git update-index --chmod=+x`, conteúdo byte-identical, baseline não
reescrita.

Nenhuma Stop Condition da E3.12.1 ocorreu: nenhum conteúdo de código
de produção mudou, nenhuma migração foi criada, nenhuma feature foi
introduzida, nenhum script teve conteúdo alterado, a suíte normalizada
está sem falhas, o delta de regressão é zero, documento e manifest
são numericamente idênticos, a cadeia de patches reproduz o tree,
nenhum chmod manual é necessário após o clone, e nenhuma decisão COUT
foi reaberta.

---

## 17. Gate

```
E3.12_IMPLEMENTATION_GATE   = PASS
E3.12.1_IMPLEMENTATION_GATE = PASS
```

Mas, conforme §55 e §58 do prompt canônico:

```
E3_FINAL_FREEZE = PENDING_INDEPENDENT_AUDIT
GATE_E3_TO_E4   = PENDING
READY_FOR_E4    = FALSE
```

A E3.12 **não pode se autoatribuir** o gate definitivo E3 → E4. O
executor produz evidência reproduzível; a confirmação é do auditor
independente. Enquanto a auditoria externa não confirmar
`PATCH_CHAIN_REPRODUCIBLE`, `TEST_EVIDENCE_REPRODUCED`,
`E1_E2_REGRESSION = PASS`, `COUT_GATE = PASS`, `DOCUMENTATION = PASS` e
`NO_STOP_CONDITIONS`, a Entrega 3 permanece **não congelada** e a
Entrega 4 **não inicia**.
