# E4.12 — Final Integration Gate

Última fatia da Entrega 4. Prova, sobre PostgreSQL real, que as
fronteiras de E4.1 a E4.11 se integram **sem apagar as distinções** que
cada uma existe para preservar.

```text
E4_12_IMPLEMENTATION_GATE = PASS
E4_FINAL_FREEZE           = PENDING_INDEPENDENT_AUDIT
PRODUCTION_DELTA          = NONE
MIGRATION_DELTA           = NONE
PASS_FINAL                = NOT_DECLARED
```

---

## 1. Baseline

```text
HEAD    5eeab210627ae631bc2e58237fc5268dc663a93d
TREE    c2dea87112b1c87cae793ca3421c78329ff555fc
PATCH_ID 06eb1987f82b0264e6814c5b2fa424d98c8ce565
COMMITS 97 · CHECKSUMS 30/30 OK · git fsck RC=0
COLETA 4398 · FULL 4397/1/0 · RAW 4397/1/0 · COVERAGE 99,31%
ruff PASS · black 434 · mypy 7 históricos NEW=0 · alembic e7c25a91f4b3
```

Sem divergência. `STOP_CONDITION = NONE`.

## 2. Objetivo e não objetivos

**Objetivo.** Medir integração: que nenhuma fronteira, usada junto com
as outras, reescreve patrimônio, concede autoridade que não tem ou faz
uma distinção colapsar em outra.

**Não objetivos.** A E4.12 não cria produção, migration, código de erro,
tabela, API, worker, scheduler ou provider. Ela acrescenta **provas**,
não capacidades.

```text
INTEGRATION_GATE != NEW_CAPABILITY
```

## 3. Cenário integrado

Catorze testes contínuos sobre PostgreSQL real, usando exclusivamente
APIs públicas já entregues e dublês confinados a `tests/`:

```text
g01  Accessible(P,C1) != Accessible(P,C2)
g02  patrimônio invariante à mudança de contexto, por censo canônico
g03  CONTEXT CHANGES VIEW
g04  CONTEXT DOES NOT REWRITE PATRIMONY
g05  INACCESSIBLE REMAINS HISTORICALLY REPRESENTABLE
g06  NOT_RETRIEVED != FORGOTTEN
g07  POLICY_CAN_ALTER_EXISTENCE = NO
g08  compliance é diagnóstico, com zero writes
g09  S1 <- {M1, M2, M3}, fontes preservadas
g10  RETENTION_ASSESSMENT != DELETION_AUTHORITY
g11  VALIDATED_RECORD != BEHAVIORAL_AUTHORITY
g12  Galaxy Trace sob contexto
g13  Broken Glass: extinto fora da vista, não da história
g14  seis desfechos materialmente distintos não colapsam
g15  aprovação consumida -> execução destrutiva -> replay recusado
```

Mais `g01_1`, isolamento entre domínios declarados. Dezesseis ao todo.

### Censo canônico, não contagem

```text
ROW_COUNT != CANONICAL_CENSUS
```

Todo `before/after` compara um censo **linha a linha**, ordenado e
determinístico, cobrindo identidade, CLID, estado, revisão, remoção
lógica, história causal e linhagem. Contagem igual não detectaria um
estado reescrito.

## 4. Matriz das doze condições

| # | Condição | Evidência |
|---:|---|---|
| 1 | `Accessible(P,C1) != Accessible(P,C2)` | `g01`, PostgreSQL real |
| 2 | patrimônio invariante | `g02`, `g07`, `g08`, `g10`, `g11` por censo canônico |
| 3 | quatro distinções | `g03`–`g06`, literais |
| 4 | policy não altera existência | `g07` + `test_m07`/`m08` por AST |
| 5 | E3 efetivamente congelada | `test_m01`–`m03`, blobs e árvore |
| 6 | consolidação rastreável | `g09` |
| 7 | Galaxy/Broken Glass | `g12`, `g13` |
| 8 | sem learning engine | `g11` + `test_m09`/`m10` com mutante |
| 9 | neutralidade de provider | `test_m11`–`m14` |
| 10 | deferidos completos | manifesto humano e JSON, `test_m15`–`m19` |
| 11 | sem stop condition ativa | `ACTIVE_STOP_CONDITION = NONE` |
| 12 | reproduzível | clone limpo do bundle, relatório de gates |

Acrescentadas pelo corretivo, fora da matriz das doze porque não são
condições do prompt original e sim consequências dos achados:

| Prova | Evidência |
|---|---|
| isolamento entre domínios | `g01_1`, `MemoryIsolationManager` real |
| aprovação → execução destrutiva | `g15`, com replay recusado |

## 5. Freeze efetivo da E3

```text
E3_ORIGINAL_DELTA = ONLY_AUTHORIZED_E3_4_2_AND_E3_4_2_1
E3_AFTER_EFFECTIVE_FREEZE_MODIFIED = NO
```

A E3 foi **explicitamente reaberta** para dois corretivos autorizados. O
freeze efetivo é a cadeia 47, `b4e61a4702a4428dd1dea7464efe09a180bf797c`.
Comparar cegamente com a árvore original reportaria o corretivo como
regressão; ignorar o original perderia a prova de que só ele entrou. A
guarda usa os dois lados.

### Achado da própria E4.12

No plano eu escrevi que o delta autorizado **não tocou arquivo
pré-existente**. Estava errado, e o erro é de método: eu inferi isso de
"0 remoções".

```text
INSERTION_STATS != PATH_STATUS
```

A medição por `git diff --raw` mostra **três modificados e dois
adicionados**, com blobs distintos dos dois lados. A guarda `test_m01`
passou a comparar caminho, status, modo e blob — não estatística — e
`test_m99_2` é o mutante que apresenta um `M` como `A`.

## 6. Provas negativas

```text
INACCESSIBLE             != NONEXISTENT
NOT_RETRIEVED            != FORGOTTEN
POLICY_NOT_APPLICABLE    != COMPLIANT
INSUFFICIENT_INFORMATION != VIOLATION_CONFIRMED
NO_MATERIAL_ATTEMPT      != FAILED_EFFECT
VALIDATED_RECORD         != BEHAVIORAL_AUTHORITY
```

Nenhum `INVALID` genérico: cada par é medido por tipo disjunto ou por
membro de vocabulário fechado, não por mensagem.

## 7. Guardas e mutantes

Vinte e três guardas, cada uma com mutante que a faz falhar pela mesma
lógica. As que mais custaram:

- `m01` compara **blobs e modos**, não estatísticas;
- `m07` distingue receptor: `SET_ADD != SESSION_ADD`;
- `m09` mede chamada e ramificação: `IMPORT != BEHAVIOR`;
- `m13` distingue `Protocol` com corpo `...` de adaptador com corpo vivo;
- `m16` compara manifesto humano e JSON **automaticamente**;
- `m22` recusa censo por `count(*)`.

## 8. Achados da própria fatia

Cinco desencontros entre o que a documentação sugeria e o que o código
realmente expõe, todos corrigidos contra a fonte:

1. `CausalHistoryManager.record`, não `append_event`;
2. `actor_ref` tem FK real para `provenance_records` — um UUID inventado
   violaria a integridade da E3.6, então o evento **não nomeia ator**;
   fabricar identidade seria pior que omiti-la;
3. `MemoryContext` guarda `domain_ids` (conjunto), não `domain_id`;
4. `lineage_edges` usa `parent_coid`/`child_coid`;
5. `GovernanceManager.resolve` recebe `descriptor`, não `operation` —
   porque a fronteira de plataforma vem **antes** da policy local.

E uma disciplina de sessão: atributos ORM são lidos **dentro** da
`UnitOfWork`; fora dela a instância está desanexada e qualquer acesso
dispararia refresh sem sessão.

Nenhum defeito material foi encontrado em E4.1–E4.11. Se tivesse sido,
a E4.12 o reportaria — não é licença para corrigir módulo congelado.

## 8.1 Candidato REJEITADO pela auditoria — `938c553a`

O candidato publicado da cadeia 97,
`938c553a08981ae29266fbb27531bb1deb754167`, foi **rejeitado pela
auditoria independente** com sete achados. Ele foi corrigido por
`git commit --amend`, sem criar cadeia 98, e permanece nomeado aqui.

```text
REJECTED_CANDIDATE = 938c553a
PATCH_CHAIN        = 97  (mantida)
CHAIN_98           = NOT_CREATED
```

O instrumento foi **fortalecido primeiro**, e os defeitos foram
reproduzidos no candidato rejeitado antes de qualquer correção:

```text
cadeia 96                    14/14 DEFECT_REPRODUCED
candidato rejeitado 938c553a  4/14 DEFECT_REPRODUCED
árvore corrigida              0/14 DEFECT_NOT_REPRODUCED
```

Duas sondas novas nasceram do corretivo —
`ISOLATION_AND_DESTRUCTIVE_COMPOSITION_ABSENT` e
`APPEND_ONLY_GUARANTEE_DISABLED_BY_TEST` — e três foram fortalecidas. O
total foi de doze para **catorze**, declarado em vez de preservado
artificialmente.

### A1 — `g01` não comparava vistas reais

**Causa.** O teste provava que uma **transição persistente** mudou o
estado gravado do objeto.

```text
PERSISTENT_TRANSITION != CONTEXTUAL_VIEW
```

Isso é outra coisa. A condição 1 exige que o **alcance** difira entre
contextos.

**Correção.** `g01` compara dois conjuntos canônicos de COIDs, vindos de
dois `retrieve` reais do `MemoryRetrievalManager`. Os dois contextos
declaram domínios distintos, e o patrimônio pertence apenas ao primeiro:
`vista_um == esperados`, `vista_dois == set()`.

### A2 — E4.6, E4.8 e o fluxo destrutivo não estavam compostos

**Correção.** `g01_1` compõe o `MemoryIsolationManager` **sobre o
`MemoryRetrievalManager`** — é ele a porta de recuperação, não o motor
de busca — e mede que o patrimônio do domínio de `C1` não vaza sob o
escopo de `C2`. `g15` compõe aprovação persistida e
`DestructiveExecutionService`, com replay recusado por consumo já
efetuado, e censo do patrimônio idêntico antes e depois.

As portas `_ResolvedorDeTeste` e `_EfeitoDeTeste` vivem **em
`tests/`**; `TEST_SANDBOX_PORT != PRODUCTION_ADAPTER`, e a guarda `m13`
continua medindo que nenhum adaptador com corpo vivo existe em produção.

### A3 — `g03`–`g06` confundiam transição com mudança contextual

**Correção.** As quatro distinções passaram a medir a **vista**:
`g03` compara o conjunto alcançado antes e depois, `g06` prova que a
vista não alcança o objeto **e** que ele continua existindo com história
intacta.

`g03` usa `inaccessible` e não `latent` de propósito:

```text
LATENT != INACCESSIBLE
```

O estado latente permanece alcançável, e usá-lo seria a prova errada
para esta linha.

### A4 — Galaxy e Broken Glass não passavam pelas vistas

**Correção.** `g12` e `g13` consultam a vista contextual além do
repositório da E3: o objeto sai do alcance, os demais continuam
alcançáveis, e linhagem e história permanecem intactas.

### A5 — `g11` contornava as triggers

**Causa.** A limpeza usava `SET session_replication_role = replica`, que
desliga exatamente a trigger que prova o append-only.

```text
A_TEST_MUST_NOT_DISABLE_THE_GUARANTEE_IT_MEASURES
```

**Correção.** No cenário, a limpeza é por **rollback transacional**: a
linha existe dentro da transação, todas as garantias valem, e nada é
desativado. No teste da E4.11, a limpeza passou a ser **DDL
deliberado** — a tabela é derrubada e recriada pela migration — e as
três garantias DML (`UPDATE`, `DELETE`, `TRUNCATE`) permanecem **ativas
durante todos os testes**, que é o que `i35` mede.

A sonda `APPEND_ONLY_GUARANTEE_DISABLED_BY_TEST` varre a árvore de
testes inteira e conta apenas o que é **executado como SQL**:
`MENTIONED_IN_PROSE != APPLIED`.

### A6 — blobs abreviados e migrations da E3 desprotegidas

**Correção.** `git diff --raw --no-abbrev` devolve os blobs completos de
40 caracteres — `ABBREVIATED_BLOB != FULL_BLOB`, porque abreviações
podem colidir e comparam menos do que aparentam. E `m02_1` passou a
guardar os cinco arquivos de **migration da E3 original**: uma migration
alterada mudaria o schema que o patrimônio da E3 assume sem tocar em uma
linha de `app/cognitive`. Migrations novas da E4 são esperadas e não são
alteração da E3 — a guarda mede os arquivos nomeados, não a pasta.

### A7 — inventário, estatística e classificação do COUT-P

**Correção.** Inventário: **28 artefatos + `CHECKSUMS_SHA256.txt`** no
pacote corrigido, por **nome e conjunto**, sem tamanho autorreferente e
com o próprio inventário incluído na lista.

```text
SELF_REPORTED_SIZE != STABLE_FACT
```

A versão anterior declarava o tamanho de cada arquivo, inclusive o seu —
número que fica errado no instante em que o documento é escrito — e se
omitia da lista, o que produziu a contagem divergente. A igualdade entre
os arquivos do pacote, as entradas do `CHECKSUMS` e a lista do
inventário é verificada programaticamente na montagem.
Estatística do candidato rejeitado, medida: **2252 inserções em 7
arquivos** — eu havia reportado `+2191` com uma nota vaga de `+2`, em vez
de medir com `git show --numstat`.

```text
HAND_COUNTED_STAT != MEASURED_STAT
```

A estatística do commit **corrigido** é maior, porque o corretivo
acrescenta o cenário de isolamento, o fluxo destrutivo, duas sondas e as
seções A1–A7. Ela está no relatório de gates, medida sobre a árvore
final — repetir `2252` ali seria trocar um número errado por outro.

COUT-P v1.2 passou de `FUTURE_STOP_CONDITION` para **`DEFERRED`**,
candidato da E5.0:

```text
DEFERRED_CANDIDATE != FUTURE_STOP_CONDITION
```

`FUTURE_STOP_CONDITION` é reservado ao que **poderia bloquear** a
entrega se fosse exigido. Nada na E4 depende de COUT-P, então
classificá-lo assim inflava a lista de bloqueios potenciais com um item
que não é um.

## 8.2 Segundo candidato rejeitado — `d5f466ef`

O corretivo dos sete achados ainda não bastou. A auditoria rejeitou
`d5f466ef81da7268354078b0af2d361781dc0fa0` com seis achados novos, e o
instrumento foi fortalecido **antes** de qualquer correção: doze sondas
tinham virado catorze, e viraram **dezoito**.

```text
cadeia 96                 18/18
candidato 938c553a         9/18
candidato d5f466ef         5/18
árvore corrigida           0/18
```

### B1–B4 — as quatro distinções ainda não eram contextuais

`g03` e `g04` chamavam `transition`: uma transição **persistente**, no
mesmo contexto. `g05` não provava invisibilidade contextual. `g13` não
consultava a vista.

```text
PHRASE_PRESENT != PROPERTY_PROVEN
```

A sonda anterior aceitava a **presença da frase** como prova — bastava
a distinção aparecer numa docstring. Agora ela mede ausência de
`transition` em `g03`/`g04`, duas consultas reais à vista, e quatro
asserções em `g05`.

Reescritos: `g03` compara duas vistas do mesmo patrimônio, sem
transição alguma; `g04` compara censo canônico integral antes e depois
de dois retrievals, sem transição; `g05` prova que `INACCESSIBLE` e
`CAUSALLY_EXTINCT` continuam no repositório com história e linhagem, e
que **ambos** estão ausentes da vista; `g13` prova que o extinto sai da
vista enquanto o irmão permanece.

### B5 — o freeze das migrations da E3 era parcial

```text
PARTIAL_HARDCODED_LIST != COMPLETE_FREEZE
```

A guarda nomeava **cinco** arquivos à mão. O commit original da E3 tem
**treze** migrations Python mais o `.gitkeep`. Oito ficavam livres.

O conjunto passou a ser DERIVADO por
`git ls-tree -r 014455f9 backend/alembic/versions`, comparando caminho,
presença, modo e blob completo de cada artefato original. Migrations
posteriores da E4 são permitidas e medidas como tal. Há guarda de
premissa (`m02_2`, que exige as treze) e mutante (`m99_2_1`, que retira
uma da lista e mostra que a alteração passa despercebida).

### B6 — manifesto e handoff divergiam sobre COUT-P

O manifesto dizia `DEFERRED`; o handoff mantinha
`FUTURE_STOP_CONDITION`. Dois documentos, duas verdades.

```text
COUT_P_V1_2 = DEFERRED
FUTURE_STOP_CONDITION = NO
DEFERRED_ITEM != UNIVERSAL_PRECONDITION
```

Transporte de `ValidatedExperience` e unificação documental deixaram de
ser apresentados como pré-condições universais da E5: só exigem decisão
se o escopo futuro depender deles. `m16_1` compara os dois documentos, e
distingue **atribuição** de **marcador de distinção** — `!=` não é `=`.

## 8.3 Candidato local inválido — `afe2c5ec`

Um primeiro candidato local da cadeia 97,
`afe2c5ec368c7a879f59d8640cf86d5713367ea6`, **não foi publicado** e foi
refeito. Ele passava na suíte, mas reprovava a própria caracterização:
quatro das doze sondas continuavam em `DEFECT_REPRODUCED`.

Três eram defeitos do **instrumento**, medindo na granularidade errada:

- `CONSOLIDATION` exigia `ConsolidationManager` **nomeado** na função, e
  o cenário o usava por composição — `COMPOSED != NAMED`;
- `PATRIMONY_INVARIANCE` aceitava só `sorted` do Python e reprovava um
  censo que ordena no SQL — `SQL_ORDER_BY_IS_ALSO_CANONICAL_ORDER`;
- `LEARNING_ENGINE` procurava o nome literal dentro do corpo da função,
  quando a guarda o consome de uma constante de módulo.

Uma era defeito **real do cenário**: `g09` construía a linhagem por SQL
direto em vez de usar o `ConsolidationManager` da E4.5. Corrigido — a
prova passou a exercitar o gestor real, com perdas e preservações
declaradas.

```text
INVALID_LOCAL_CANDIDATE = afe2c5ec (não publicado)
```

## 9. Gates finais

Executados **depois** da última alteração, inclusive documental, em
clone limpo do bundle da cadeia 97. Números literais no relatório de
gates do pacote.

```text
GATE_EXECUTADO_ANTES_DA_ULTIMA_MUDANCA != GATE_DO_COMMIT
```

Como não há produção nova, não se alega "100% em arquivos de produção
novos": reporta-se cobertura global e cobertura das linhas efetivamente
tocadas.

## 10. Riscos e limites honestos

- **(a)** O gate mede **integração**, não capacidade material: nenhum
  adaptador de produção existe, e nada aqui prova apagamento real.
- **(b)** As fronteiras sem adaptador continuam sem adaptador; um
  adaptador futuro precisará das próprias provas.
- **(c)** `validated_by` e `origin_ref` são atribuídos, nunca
  autenticados — e a E4 não alega o contrário.
- **(d)** O transporte de `ValidatedExperience` não existe; o contrato
  de portabilidade existe.
- **(e)** As duas raízes documentais permanecem separadas.
- **(f)** Ausência de achado adicional não é prova de ausência de
  defeito.

## 11. Estado de handoff

```text
E4_9                      = FROZEN
E4_10                     = FROZEN
E4_11                     = FROZEN
E4_12_IMPLEMENTATION_GATE = PASS
E4_FINAL_FREEZE           = PENDING_INDEPENDENT_AUDIT
GATE_E4_TO_E5             = PENDING
READY_FOR_E5              = FALSE
E5                        = NOT_STARTED
PASS_FINAL                = NOT_DECLARED
```

`PASS_FINAL` e `E4_FINAL_FREEZE` pertencem exclusivamente à auditoria
independente. A E4.12 não os declara.
