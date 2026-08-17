# EDR E4.9.5 — `ErasureRecord` Persistence Foundation

**Natureza:** primeira fatia de **runtime** da E4.9. Implementa a
primitiva persistente e nada além dela.
**Baseline:** cadeia 74 (`ecb630b0`), auditada como
`E4_9_4_AUDIT = PASS_FINAL`.

```text
ERASURE_RECORD_MODEL          = IMPLEMENTED_CANDIDATE
ERASURE_RECORD_TABLE          = IMPLEMENTED_CANDIDATE
ERASURE_RECORD_REPOSITORY     = IMPLEMENTED_CANDIDATE
ERASURE_RECORD_APPEND_ONLY    = ENFORCED_ORM_REPOSITORY_DATABASE
ERASURE_RECORD_RUNTIME_WRITER = NOT_COMPOSED
ERASURE_EFFECT                = NONE
E4_9_IMPLEMENTATION           = IN_PROGRESS_NOT_OPERATIONAL
```

Nada nesta entrega apaga, oculta, move para lixeira, resolve alvo,
autentica, aprova ou executa.

---

## 1. Fatos da baseline

Medidos, não presumidos.

```text
HEAD ecb630b0…  PARENT 9b2e0738…  TREE 16e2be5e…  PATCH_ID a3bfbb50…
MIGRATION_HEAD 7b2e4c9a15df   árvore limpa
FULL 2446 passed / 1 skipped / 0 failed      RAW 2073 / 374
NEXT_FREE_ERROR_CODE = PIA-8041  (zero ocorrências em app/ e tests/)
to_regclass('erasure_records') = NULL
CognitiveOperation = 11 membros, incluindo legal_erasure
```

**Divergência menor registrada.** O §2 do prompt nomeia o bundle
`pia-os-e4-9-4-destructive-execution-authority.bundle`; o arquivo
entregue chama-se `pia-os-chain74.bundle`. O SHA-256 confere
exatamente com o declarado (`211bd4bf…cbee8b`), então é apenas o
nome. Registrado por disciplina, sem impacto.

---

## 2. Dois achados que mudaram o desenho

### 2.1 O projeto não tinha padrão de trigger

O §8.3 manda usar "o padrão real do projeto para trigger/function".
**Não existe padrão:** busca por `CREATE TRIGGER` e `CREATE FUNCTION`
em `alembic/versions/` retorna zero. Até aqui, `GovernancePolicy` e
`AccessibilityPolicy` garantiam imutabilidade em duas camadas e
registravam **honestamente**, no próprio docstring, que um
`UPDATE`/`DELETE` em SQL bruto continuava possível.

Para este registro essa honestidade não basta, e a razão é específica:

```text
ERASING THE RECEIPT OF AN ERASURE = MAKING DESTRUCTION UNAUDITABLE
```

O recibo que prova o que foi destruído é justamente o que alguém teria
motivo para reescrever. Estabeleci o padrão: função `plpgsql` com
`search_path` fixo em `pg_catalog`, trigger `BEFORE UPDATE OR DELETE
FOR EACH ROW`, nomes determinísticos, downgrade que remove trigger,
função e tabela na ordem segura — testada, sem função órfã.

A trigger é criada **apenas** no PostgreSQL. A suíte RAW roda em
SQLite, onde a garantia segue sendo ORM + repositório; os testes de
integração provam a terceira camada no banco real.

### 2.2 A estratégia de enum do projeto não verifica nada no banco

Este é o achado mais importante da fatia, e só apareceu porque um
teste meu falhou por engano.

`Enum(..., native_enum=False)` no SQLAlchemy 2.x tem
`create_constraint=False` por padrão: a coluna vira `VARCHAR` **sem
verificação**. Medido na baseline: `cognitive_objects` tem **zero**
`CHECK`, apesar de `accessibility` ser um enum fechado.

Para as tabelas da E3 isso é aceitável — o ORM é o único escritor.
Aqui não é. A trigger existe justamente porque este registro pode
receber SQL bruto, e sem verificação um `INSERT` direto gravaria:

```sql
INSERT INTO erasure_records (..., outcome, ...) VALUES (..., 'pending', ...)
```

`pending` é exatamente o `FORBIDDEN_OUTCOME` que a E4.9.0 proibiu.
Acrescentei dois `CHECK` explícitos de vocabulário, indo **além** do
padrão herdado:

```text
ck_erasure_records_outcome_vocabulary
ck_erasure_records_target_class_vocabulary
```

```text
CLOSED ENUM IN PYTHON != CLOSED VOCABULARY IN THE DATABASE
```

---

## 3. Decisões de modelagem

### 3.1 `completed_at` é NOT NULL

O §5.2 pede; a razão merece registro. Se fosse nullable, um registro
sem `completed_at` seria um `PENDING` disfarçado — a coisa proibida
com outro nome e sem nenhuma coluna que a delatasse.

```text
NO_RECORD_BEFORE_OBSERVED_ATTEMPT
```

Não existe estado em andamento. Um recibo nasce depois da observação.

### 3.2 Nenhuma FK, em lugar nenhum

```text
SUBJECT_LINK = HISTORICAL_IDENTIFIER_NOT_FK
```

Zero FKs na tabela, provado em integração. Uma FK para o sujeito
criaria um dilema sem saída: com cascade, o recibo some junto com o
que registra; sem cascade, o recibo **impede** a operação que
registra. Identidade histórica não tem esse problema.

O mesmo raciocínio vale para `governance_policy_id` — obrigatório como
evidência histórica, sem FK — e para aprovação, resolução, executor e
retenção. Para retenção há ainda a razão trivial: `RetentionPolicy`
não existe, `to_regclass` devolve `NULL`.

### 3.3 Nenhum campo capaz de guardar conteúdo

Não há coluna JSON, `metadata`, `details`, `payload`, `message`,
`description` ou qualquer campo livre. Isso é **estrutural**, não uma
regra de uso: um campo livre acabaria recebendo o trecho "só para
contexto", e o recibo viraria o último lugar onde o apagado
sobreviveu.

```text
IF THE RECEIPT CAN RECOMPOSE THE CONTENT, IT IS CONTENT
```

Provado por lista proibida de 29 nomes sobre as colunas reais, e por
`extra="forbid"` nos schemas — que rejeita, por exemplo,
`effect_digest`, deliberadamente **fora** desta fatia porque mecanismo
e canonicalização continuam deferidos.

### 3.4 Ordenação determinística

`attempted_at DESC, id ASC`, com índice composto. O desempate não é
enfeite: recibos de um mesmo lote nascem na mesma transação, e
`now()` do PostgreSQL é o timestamp de **início da transação** — lição
paga na E4.6.3. Ordenar só por tempo faria a paginação repetir ou
pular linhas conforme o plano de execução.

---

## 4. Append-only em três camadas

| Camada | Mecanismo | O que pega |
|---|---|---|
| 1 | eventos `before_update` / `before_delete` | mutação **por fora** do repositório — carregar, mutar, `commit()`; defeito reproduzido de verdade na E4.3.1 |
| 2 | `ErasureRecordRepository` | `update`, `delete`, `soft_delete`, `bulk_update`, `bulk_delete` |
| 3 | trigger PostgreSQL | `UPDATE`/`DELETE` em **SQL bruto**, fora do ORM |

`soft_delete` é rejeitado explicitamente embora o modelo não componha
`SoftDeleteMixin` e não tenha `deleted_at`: uma tentativa futura de
"só esconder da listagem" encontra recusa em vez de `AttributeError`
ambíguo.

`INSERT` bruto continua permitido — append-only é *append* only.

---

## 5. O escritor runtime **não** foi composto

```text
ERASURE_RECORD_RUNTIME_WRITER = NOT_COMPOSED
```

Nenhum serviço, manager ou orquestrador importa a primitiva. Provado
por AST sobre todo `app/`, com lista fechada de arquivos autorizados,
mais busca textual em `services/` para pegar acoplamento por string ou
`importlib`.

A razão é simples: compor o escritor antes de existir executor,
resolvedor de alvo, identidade e aprovação criaria um caminho capaz de
fabricar recibos de apagamentos que **nunca aconteceram**. Um recibo
falso é pior que recibo nenhum, porque parece prova.

`append_observed` recebe entidade validada, nunca dicionário livre — o
nome diz a pré-condição que `create` ou `save` não diriam.

---

## 6. Guardas que envelheceram

Dez testes existentes falharam, e **nenhum** por regressão de
comportamento. Todos afirmavam o estado da baseline anterior:

| Guarda | O que afirmava | O que fiz |
|---|---|---|
| 6 testes de migration head | head é `7b2e4c9a15df` | atualizado para `9d4f1a7c2be8` com nota; o que protegem é a **ausência de branching**, não a imobilidade |
| `ci28`, `ri25`, `pi13` | conjunto exato de tabelas de memória | acrescentado `erasure_records` com nota; continuam exigindo conjunto EXATO |
| `test_e435_corrective_created_no_retention_capability` | nada em `app/memory` menciona `ErasureRecord` | isentei **apenas** os arquivos autorizados; a proibição vale em todo o resto, e **todas** as proibições de retenção seguem intactas |

Nenhuma asserção foi afrouxada. O precedente é do próprio repositório —
esses testes já traziam notas "Atualizado pela E4.7". Um teste que
envelheceu é atualizado com nota; um teste que falha por regressão é
outra coisa inteiramente.

`app/cognitive` permanece **byte a byte idêntico**: `git diff` sobre a
árvore de produção da E3 é vazio.

---

## 7. Três correções minhas durante a fatia

**(a) `UnitOfWork` faz rollback por omissão.** Escrevi cinco testes de
integração sem `uow.commit()`, e as releituras devolviam `None`. O
contrato está no docstring do próprio módulo: *"se `commit()` não for
chamado, nada persiste"*.

**(b) Comparação por identidade com enum relido do banco.** Escrevi
`lido.outcome is ErasureOutcome.SUCCEEDED`. Com `native_enum=False` o
SQLAlchemy devolve a **string crua** na releitura, e `StrEnum` compara
igual por valor mas não é o mesmo objeto. Testar identidade ali seria
testar o carregador do ORM, não o contrato do recibo.

**(c) Um teste que passava pelo motivo errado.** Meu teste de
vocabulário de `outcome` passou antes mesmo de existir o `CHECK` de
vocabulário — porque `pending` violava a matriz `failure_code`. Foi o
teste de `target_class` que denunciou a ausência real. Ajustei o teste
para não fixar qual das duas constraints dispara, já que a ordem de
avaliação é decisão do PostgreSQL, e passei a asseverar o que
importa: a linha não entra.

---

## 8. Gates medidos

```text
FULL_SUITE       2559 passed / 1 skipped / 0 failed
RAW_SUITE        2149 passed / 409 skipped / 0 failed
GLOBAL_COVERAGE  99,17%
  erasure_enums.py             100%
  erasure_record.py            100%
  erasure_record_repository.py 100%
  erasure_record/schemas       100%
RUFF PASS   BLACK PASS   MYPY 7 históricos em 3 arquivos, NEW = 0
DRIFT 5 passed   ALEMBIC single head 9d4f1a7c2be8
migration upgrade → downgrade → upgrade: limpo, sem função órfã
git diff --check CLEAN
```

**Regressões, delta 0:** E3 = 732 · E4.1 = 40 · E4.2 = 42 · E4.3 = 255 ·
E4.4 = 74 · E4.5 = 187 · E4.6 = 275 · E4.7 = 240 · E4.8 = 146.
Fatia nova: **113** (67 unitários + 37 integração + 9 estáticos),
rodados três vezes com resultado idêntico.

**LOC medido:** produção 1038 linhas (enums 82, model 372, schemas
203, repository 160, migration 221); testes 1116.

---

## 9. Limites desta fatia

```text
ERASURE_RECORD_PERSISTENCE != ERASURE_EXECUTION
ERASURE_RECORD_PERSISTENCE != DELETION_AUTHORITY
ERASURE_RECORD_PERSISTENCE != RETENTION_POLICY
```

Continuam ausentes em runtime: fronteira de identidade e autenticação;
step-up; envelope e registro de aprovação; orquestrador dos cinco
estados; resolvedor de alvo e portas de efeito; `ArtifactStorage` e
conectores; `RetentionPolicy`; lixeira.

`CausalEventType` e `CognitiveOperation` inalterados. Nenhuma rota,
nenhum endpoint, nenhum Sync — `erasure_records` não entra em
`SECTION_BY_TABLE`, porque um recibo exportado levaria a outra
instalação a lista do que foi apagado aqui.

```text
SYNC_BOUNDARY = LOCAL_ONLY
CONTRACTS CLOSED != MODULE READY
```

---

## 10. Riscos que declaro por conta própria

**(a) A tabela existe e ninguém escreve nela.** É o estado correto
hoje e é frágil socialmente: uma primitiva pronta e inerte convida a
"só ligar o escritor" na próxima fatia, antes de existir aprovação e
executor. As guardas por AST protegem contra isso enquanto ninguém as
alterar — e alterá-las é fácil. A E4.9.8 precisa tratar a composição
do escritor como decisão explícita, não como consequência.

**(b) `scope_token` é o campo mais frágil do modelo.** Ele é opaco por
contrato e string livre por tipo. Nada no banco impede alguém de pôr
ali um caminho de arquivo — e a validação recusa vazio, controle e
excesso de tamanho, mas não adivinha semântica, deliberadamente:
heurística que falha em silêncio seria pior. O risco é real e a
mitigação é a disciplina de quem preencher.

**(c) A trigger protege a tabela, não o banco.** Um superusuário pode
`DROP TRIGGER`. A camada 3 eleva o custo de adulteração de trivial
para deliberado e rastreável; não a torna impossível. Dizer o
contrário seria a alegação falsa que a E4.9.1 recusou.

**(d) `governance_policy_id` sem FK é escolha, não descuido.** O preço
é que um `id` inválido pode ser gravado — nada verifica que a policy
existe. Preferi isso ao dilema da FK (§3.2), mas registro que a
integridade referencial da governança no recibo é, hoje, contrato e
não garantia.

---

## 11. Estado

```text
PATCH_CHAIN = 75
MIGRATION_HEAD = 9d4f1a7c2be8
E4_9_5_IMPLEMENTATION = COMPLETE_CANDIDATE
ERASURE_RECORD_FOUNDATION = COMPLETE_CANDIDATE
ERASURE_RECORD_RUNTIME_WRITER = NOT_COMPOSED
ERASURE_EFFECT = NONE
E4_9_IMPLEMENTATION = IN_PROGRESS_NOT_OPERATIONAL
E4_10_IMPLEMENTATION = NOT_STARTED
```

Não se declara `PASS_FINAL`, E4.9 pronta, erasure executável ou recibo
produzido em runtime.
