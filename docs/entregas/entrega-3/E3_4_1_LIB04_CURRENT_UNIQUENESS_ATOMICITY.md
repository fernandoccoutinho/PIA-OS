# E3.4.1 / LIB-04 — CURRENT Uniqueness + Atomicity Closure

Correção incremental de `E3.4_LIB04_VERSION_TRANSFORMATION.md`. Não
reimplementa E3.4, não redesenha o Domain Model.

## 1. Problema encontrado

A documentação original de E3.4 afirmava `COUNT(CURRENT) <= 1` "para
uma linha de revisão controlada", mas `revise(source)` só bloqueava e
reavaliava `source` — confiava que o chamador sempre passa o `CURRENT`
correto. O teste de concorrência existente (`RC1`-`RC4`) provava
apenas "duas revisões concorrentes do MESMO `source` → no máximo uma
vence", não o invariante mais amplo pretendido.

## 2. Counterexample confirmado

```text
A: clid=X, revision_status=CURRENT
B: clid=X, revision_status=None   (branch de DERIVATION de A)

revise(B)  →  sem proteção adicional, produzia:
    A: CURRENT
    B: SUPERSEDED
    C: CURRENT   (dois CURRENT para o mesmo CLID)
```

Reproduzido e confirmado antes de qualquer correção
(`test_u2_wrong_source_revise_cannot_create_second_current`).

## 3. Semântica auditada de CLID

**Pergunta decisiva**: CLID identifica exatamente uma linha de revisão
controlada, ou é continuidade mais ampla?

Inspecionado: `E3_DOMAIN_MODEL_DRAFT.md` (seção CognitiveObject),
`E3_3_LIB03_CLID_LINEAGE.md`, `E3_4_LIB04_VERSION_TRANSFORMATION.md`,
código real de `ClidManager`/`VersionManager`, testes existentes
(`D7`: múltiplos branches de `DERIVATION` coexistindo com o mesmo
CLID).

**Conclusão**: CLID é continuidade ampla por natureza — `DERIVATION` e
`REVISION` deliberadamente compartilham o mesmo CLID (`inherit()` é
usado por ambas), e branches de `DERIVATION` nunca precisam de
`CURRENT`/`SUPERSEDED` entre si. Isso por si só **não** prova que CLID
seja inadequado como escopo de unicidade de `CURRENT` — apenas prova
que nem todo objeto com um dado CLID participa do "concurso" por
`CURRENT` (só quem tem `revision_status` setado participa; `None`
fica estruturalmente fora do escopo de um índice `WHERE
revision_status = 'current'`).

## 4. Decisão: CASE A

`CLID` é o escopo adotado para `CURRENT uniqueness` — `CASE A`.

Justificativa:

- Nenhum mecanismo hoje implementado (nem no Domain Model, nem em
  E3.1-E3.4) cria necessidade de dois `CURRENT` simultâneos
  legítimos para o mesmo CLID.
- O índice único parcial (`WHERE revision_status = 'current'`) não
  restringe `DERIVATION` de forma alguma — testado explicitamente
  (`test_derivation_branches_are_never_constrained_by_the_current_index`):
  5 branches do mesmo CLID coexistindo livremente, todos com
  `revision_status = None`.
- Nenhuma identidade de "linha de revisão" distinta de CLID existe no
  Domain Model — introduzir uma (`revision_line_id`,
  `controlled_asset_id`) seria arquitetura nova não demandada,
  proibida pelas Proibições de Arquitetura do prompt corretivo (§5).

**Ressalva documentada, não bloqueante**: um cenário futuro em que o
modo `COMPETITIVE` (Multi-IA, `E7` Hypervisor) precise de múltiplos
candidatos a `CURRENT` simultâneos antes de arbitragem **não é
suportado** por esta decisão — se `E7` precisar disso, exigirá um
conceito de escopo mais fino que CLID, introduzido explicitamente
naquele momento (nova migração, nova decisão), não antecipado aqui.
`E7`/Hypervisor não existe ainda — não é requisito desta fase.

## 5. Solução adotada

**Duas camadas**, nenhuma delas dependendo isoladamente de "caller
correto" (P4):

1. **Pré-checagem** (`ObjectRepository.get_current_by_clid`, novo
   método): antes de criar `target`, `VersionManager.revise()`
   verifica se já existe um `CognitiveObject` diferente de `source`
   com `revision_status = CURRENT` para o mesmo CLID. Se sim, rejeita
   imediatamente (`RevisionCurrentUniquenessViolationError`,
   `PIA-8012`). Defesa em profundidade — sujeita a TOCTOU sozinha,
   evita o caso comum sem depender do banco.
2. **Índice único parcial** (autoridade final):
   `uq_cognitive_objects_one_current_per_clid` —
   `UNIQUE(clid) WHERE revision_status = 'current'`, declarado em
   `CognitiveObject.__table_args__`, suportado nativamente por
   PostgreSQL (`postgresql_where`) e SQLite (`sqlite_where`, disponível
   desde SQLite 3.8.0 — usado nos testes unitários). Uma violação é
   traduzida do mesmo `PersistenceError` genérico para
   `RevisionCurrentUniquenessViolationError` via sinal estruturado
   (`orig.sqlstate == "23505"` / `orig.sqlite_errorname ==
   "SQLITE_CONSTRAINT_UNIQUE"`) — mesmo princípio de E3.2.1/E3.3.1,
   nunca parsing de mensagem.

**Nenhuma arquitetura proibida foi criada** — nenhuma entidade
`ControlledAsset`/`Revision`/`RevisionLine`/`Arbiter`/`PolicyEngine`
etc.

## 6. Bug real encontrado e corrigido durante o desenvolvimento

A ordem original de `revise()` — `target.revision_status = CURRENT`
antes de `source.revision_status = SUPERSEDED` — **violava o próprio
índice recém-criado**: dentro da mesma transação (mesmo sem nunca
chegar a commitar), `source` e `target` ficavam ambos `'current'`
simultaneamente por um instante, o que o índice único parcial rejeita
imediatamente no `flush()` do `UPDATE` de `target` (PostgreSQL/SQLite
não adiam a checagem de índice único até o fim da transação por
padrão). Corrigido invertendo a ordem: `source → SUPERSEDED` sempre
antes de `target → CURRENT`. Encontrado empiricamente ao validar o
cenário adversarial do prompt antes de formalizar em teste — não
descoberto por acidente depois.

## 7. Invariante formal final

```text
Para cada CLID X:

    COUNT(
        CognitiveObject
        WHERE clid = X
          AND revision_status = 'current'
    ) <= 1
```

Garantido estruturalmente (não por convenção de chamador) pelo índice
único parcial — válido sob execução sequencial, caller incorreto, duas
sessões, duas conexões, concorrência real, PostgreSQL real. Testado
em todos esses cenários (ver seção Testes).

## 8. Estratégia de concorrência

Dois níveis de teste, cobrindo dois padrões de corrida diferentes:

- **`RC1`-`RC4`** (E3.4.0, revalidado): duas transações concorrentes
  chamando `revise()` sobre o **mesmo** `source` — protegido também
  por `refresh_for_update` (lock de linha), já que ambas competem pela
  mesma linha física.
- **`U4`** (novo, E3.4.1, o cenário mais forte): duas transações
  concorrentes chamando `revise()` sobre **objetos diferentes**
  (`branch_A`, `branch_B`) que compartilham o mesmo CLID, sem nenhum
  `CURRENT` estabelecido ainda. Como são linhas físicas diferentes,
  `refresh_for_update` **não cria exclusão mútua entre elas** — a
  pré-checagem pode passar para as duas simultaneamente (nenhum
  `CURRENT` existe no momento em que ambas checam). É exclusivamente o
  índice único parcial no banco que garante que só um dos dois
  `UPDATE`s finais tem sucesso. Validado com `threading.Barrier`, duas
  sessões/conexões reais, contra PostgreSQL 16 real — executado 4+
  vezes, sempre exatamente 1 commit, o outro sempre rejeitado por
  `RevisionCurrentUniquenessViolationError`.

Nenhum teste de concorrência foi simulado exclusivamente em SQLite —
`U4`/`RC1`-`RC4` rodam contra PostgreSQL real.

## 9. Estratégia de atomicidade (fault injection completo)

Cobertos, além do já existente (falha em `TransformationRecord`,
E3.4.0):

| Ponto | Teste | O que confirma |
|---|---|---|
| A. Criação/persistência do target | `A1` | Nenhum target órfão, nenhuma lineage/transformação |
| B. Resolução/propagação de CLID | `A2` | Idem |
| C. Criação/persistência de LineageEdge | `A3` | Idem + CLID não propagado |
| D. Transição de `revision_status` em `revise()` | `A4` | `source` permanece `CURRENT` (não fica `SUPERSEDED` sem par) |
| E. Criação de TransformationRecord (revise) | `A5` | Revalidado, `source` restaurado a `CURRENT` |
| Caminho feliz — `revise()` | `A6` | Estado final completo e coerente |
| Caminho feliz — `derive()` | `A7` | Idem |

Em todos os casos, `VersionManager` não controla a transação — `flush()`
implícito via `ObjectRepository.update()`/`.add()`, commit permanece
do `UnitOfWork` chamador. Nenhum `commit()` interno foi introduzido
nesta correção (confirmado por inspeção — nenhuma chamada nova a
`.commit()` em `version_manager.py`).

## 10. Migrations

Uma migração nova, aditiva, encadeada corretamente após a última
migração de E3.4 (`2832894b5cb2`):

```text
257dc8c23ab1 (E3.1) -> 4f56e1a4936c (E3.3) -> f3e7e2b98ce3 (E3.4.0)
    -> 2832894b5cb2 (E3.4.0) -> 4f8fa05e036c (E3.4.1, este documento)
```

`4f8fa05e036c_add_unique_current_per_clid_index_e3_4_1.py` — cria
`uq_cognitive_objects_one_current_per_clid`
(`CREATE UNIQUE INDEX ... WHERE revision_status = 'current'`).
Nenhuma migração anterior foi editada (diferente de E3.4.0, onde
`2832894b5cb2` pôde ser editada por ainda não estar publicada — desta
vez, o patch de E3.4 já havia sido gerado/entregue, então a disciplina
de "só migrações aditivas novas" se aplica).

Testado `upgrade → downgrade → upgrade` contra PostgreSQL 16 real —
índice criado corretamente (`\d cognitive_objects` confirma
`UNIQUE, btree (clid) WHERE revision_status::text = 'current'::text`),
removido limpo no downgrade, `lineage_edges` e as colunas
pré-existentes de `cognitive_objects` confirmadas intactas em todo o
ciclo.

## 11. Testes

19 testes unitários novos + 1 teste de integração PostgreSQL novo =
**20 testes novos** no patch (correção E3.4.1a: contagem original
desta seção somava só os 19 unitários, sem contar `U4`
separadamente):

- **Unicidade** (`test_current_uniqueness.py`, 12): `U1` (escopo é
  CLID, não global), `U2` (cenário adversarial exato do prompt, dois
  variantes), `U3` (adversarial sequencial), `U5` (bypass total do
  `VersionManager`, autoridade do banco), classificação isolada de
  violação (4 testes, sinal estruturado Postgres/SQLite/negativo/`orig`
  nulo), caminho de fallback do banco quando a pré-checagem é
  contornada (TOCTOU simulado), branches de `DERIVATION` nunca
  restringidos, re-raise de erro não relacionado não reclassificado.
- **Fault injection** (`test_fault_injection.py`, 7): `A1`-`A7`
  completos.
- **Integração contra PostgreSQL real** (`test_version_transformation_integration.py`,
  1 novo): `U4` (concorrência mais forte).

Total após E3.4.1: 262 testes unitários (100% cobertura de linha em
todo `app/cognitive/`) + 13 de integração.

## 12. Resultados

- **Suíte unitária**: 717 passed, 14 skipped (sem `.env` local — mesmo
  padrão gracioso de sempre), 97,36% (acima do anterior, 97,23%).
- **PostgreSQL**: 13/13 testes de integração passando, incluindo `U4`
  e `RC1`-`RC4` (concorrência real, threads/sessões distintas),
  executados repetidamente (4+) para confirmar estabilidade.
- **Migration cycle**: `upgrade → downgrade → upgrade` confirmado.
- **Cobertura**: 100% em `app/cognitive/`.
- **ruff/black/mypy**: limpos — mypy com os mesmos 7 erros
  pré-existentes de sempre, zero novos.
- **Non-regression**: `E1/E2`/`E3.1`-`E3.4` intactos — nenhum arquivo
  protegido tocado; `ObjectRepository` só recebeu uma adição
  (`get_current_by_clid`), sem alterar comportamento existente;
  `ClidManager`, `CoidManager`, `LineageEdge`, `LineageRepository`,
  `TransformationRecord`, `TransformationRepository` — todos
  intocados nesta correção (confirmado por `git diff --stat`).

## 13. Limitações

- A pré-checagem (`get_current_by_clid`) é best-effort — só evita o
  caso comum; a garantia real vem sempre do índice. Isso é intencional
  (P4: "a garantia não depende de caller correto"), não uma limitação
  a corrigir.
- O escopo de unicidade (CLID) não cobre o cenário hipotético futuro
  de `COMPETITIVE` multi-candidato (`E7`) — ver seção 4, ressalva
  documentada.
- Limitações preexistentes de E3.4 (ausência de FK direta
  `LineageEdge`↔`TransformationRecord`, `input_refs`/`output_refs` sem
  integridade referencial) permanecem, inalteradas.

## 14. Decisões deferidas

- Escopo de unicidade mais fino que CLID (para suportar múltiplos
  candidatos a `CURRENT` simultâneos, ex.: modo `COMPETITIVE`): `E7`,
  se e quando necessário — não implementado, não antecipado.
- `PROMOTION_POLICY_STATUS = DEFERRED`, `REVISION_NUMBER_STATUS =
  DEFERRED` (E3.4.0, inalterados por esta correção).

## 15. Non-regression

Todos os 12 itens do §12 do prompt corretivo revalidados:

1. COID source != COID target — `V1`/`D1`/`R1`, ainda passando.
2. Continuidade existente permanece correta — `V2`/`D6`/`R2`.
3. `derive()` não supersede source — `D3`, revalidado com `source`
   já `CURRENT` também.
4. Múltiplas `DERIVATION`s continuam permitidas — `D7`, e o novo
   teste explícito de branches não restringidos pelo índice.
5. `revise()` gera `TransformationKind.REVISION` — `R7`.
6. `derive()` gera `TransformationKind.DERIVATION` — `D5`.
7. `SUPERSEDED` continua recuperável — `R5`.
8. `TransformationRecord` continua append-only — revalidado
   (`test_v3_record_is_append_only` e os testes dedicados de
   `TransformationRepository`).
9. `AccessibilityState` continua independente de `RevisionStatus` —
   `test_revision_status_independent_of_accessibility`.
10. Nenhum provider/model/agent entra no `VersionManager` — `V7`/`W4`,
    revalidados (assinatura inalterada nesse aspecto).
11. Nenhuma conversa/chat/prompt é persistida — `W3`, revalidado.
12. Nenhum commit interno introduzido — confirmado por inspeção do
    código novo (`version_manager.py` não ganhou nenhuma chamada
    `.commit()`).
13. Migrations anteriores permanecem intactas — confirmado por
    `git diff --stat` e pelo ciclo `upgrade/downgrade/upgrade`.

## 16. Micro-cleanup (E3.4.1a)

Duas correções puramente documentais/de teste, sem tocar código de
produção:

1. **Contagem de testes corrigida** — seção 11 somava só os 19 testes
   unitários, sem contar `U4` (integração) separadamente; corrigido
   para "19 unitários + 1 integração = 20 testes novos".
2. **`A4` robustecido** — identificava o ponto de fault injection por
   posição/contagem de chamadas (`call_count == 2`), frágil a
   mudanças na ordem interna de `update()` (ex.: quantas chamadas
   `inherit()` faz para propagar CLID varia conforme `source.clid` já
   estar setado ou não). Corrigido para identificação semântica
   (`entity.revision_status == CURRENT`) — mesmo princípio já usado em
   `test_unrelated_persistence_error_during_current_update_is_not_reclassified`
   (`test_current_uniqueness.py`). Nenhuma mudança de comportamento —
   `A4` continua forçando falha exatamente na transição
   `target → CURRENT`, apenas de forma robusta à ordem interna de
   chamadas, não à sua posição numérica.

Nenhum código de produção, modelo, migration ou semântica de
COID/CLID foi alterado nesta correção — apenas os dois arquivos acima
(um de documentação, um de teste).
