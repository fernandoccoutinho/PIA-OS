# E3.2 / LIB-02 — COID Manager

## Objetivo

Implementar `CoidManager`: geração, validação, garantia de unicidade
e política de colisão da identidade permanente (COID) de
`CognitiveObject`.

## COID representation found

Confirmado por inspeção do código real de E3.1: `coid ≡ id`, o campo
`id` herdado de `BaseModel`/`UUIDMixin` (PK, `default=uuid.uuid4`,
resolvido no flush). A propriedade `coid` em `CognitiveObject` é um
alias de leitura, não um segundo mecanismo de identidade. Nenhum
conflito documental encontrado — não foi necessário nenhum novo campo
nem migração.

## COID Manager contract

`app/cognitive/services/coid_manager.py` — primeira vez que
`app.cognitive.services` é usado (E3.1 deliberadamente não criou essa
camada; `CoidManager` tem responsabilidade real de domínio que não
pertence a um repositório: geração e política de colisão).

```python
class CoidManager:
    def __init__(self, object_repository: ObjectRepository) -> None: ...
    def generate(self) -> uuid.UUID: ...
    def generate_unique(self, *, max_attempts: int = 5) -> uuid.UUID: ...
    def validate(self, value: object) -> uuid.UUID: ...
    def assert_unique(self, coid: uuid.UUID) -> None: ...
    def validate_imported_coid(self, value: object) -> ImportedCoidValidation: ...
```

- `generate()` — `uuid.uuid4()`, sem argumentos (não pode depender de
  payload/provider/sessão por construção — a assinatura não aceita
  nenhum).
- `generate_unique()` — gera + pré-checa unicidade, com retry limitado
  (defesa em profundidade; colisão real de UUID v4 é ~2^-122, o retry
  existe para não deixar comportamento indefinido, não porque seja
  esperado).
- `validate()` — aceita `uuid.UUID` ou `str` parseável; já retorna
  normalizado. Não existe `normalize()` separado — seria redundante.
- `assert_unique()` — considera soft-deleted também (`include_deleted=True`)
  porque identidade nunca é reciclada.
- `validate_imported_coid()` — classifica em `VALID`/`INVALID`/`COLLISION`
  (`ImportedCoidValidation`), sem side effects, sem auto-remap.

Não persiste, não commita, não conhece CLID/provenance/lineage/
provider de IA/busca semântica/deduplicação/seleção/equivalência
causal (§7 do módulo).

## Collision strategy

Duas camadas, como exigido pelo módulo (§9-§10, §22-§23):

1. **Pré-checagem** (`CoidManager.assert_unique`) — rápida, evita a
   maioria das tentativas de colisão antes de chegar ao banco.
2. **Autoridade final**: a constraint de PK do PostgreSQL real.
   `ObjectRepository.add()` foi estendido para traduzir uma
   `PersistenceError` (violação de integridade) em `CoidCollisionError`
   — cobre a janela de corrida (TOCTOU) que a pré-checagem sozinha não
   cobre. `cognitive_objects` não tem, hoje, nenhuma unique constraint
   além da PK (`id`) — por eliminação, qualquer `PersistenceError` em
   `add()` é uma colisão de COID; esta suposição deve ser revisada se
   uma migração futura adicionar outra unique constraint à tabela.
   **Testado e confirmado contra PostgreSQL real** (não só SQLite) —
   ver `tests/integration/cognitive/test_object_repository_integration.py::test_coid_collision_is_rejected_by_the_real_database_constraint`.

Para import: `validate_imported_coid()` classifica como `COLLISION`
sem nenhum auto-remap — um COID colidente nunca é silenciosamente
trocado por outro. Remapeamento auditável, se um dia existir, pertence
a `LIB-11 Synchronization Manager` (E3.11), fora do escopo deste
módulo.

## Error codes criados

| Código | Categoria | HTTP | Situação |
|---|---|---|---|
| `PIA-8003` | VALIDATION | 422 | COID com formato inválido (`CoidManager.validate`) |
| `PIA-8004` | VALIDATION | 409 | COID já existe — colisão na criação local ou no import |

`PIA-8001`/`PIA-8002` (E3.1) não cobrem esses casos — são sobre
mutação de um objeto já persistido, não sobre formato/colisão na
criação/import. `ERROR_CODE_INTEGRATION_STATUS` continua `RESOLVED`
via Opção B (E3.0) — nenhuma edição em `error_codes.py`.

## Migration status

`NOT_REQUIRED` — a constraint de PK (`id`) já é a unique constraint
necessária; nenhuma tabela/coluna nova.

## Imutabilidade (consolidação do contrato formal)

E3.1 já implementava a proteção (evento `before_update`); E3.2
consolida como contrato formal testado explicitamente sob a ótica do
COID Manager (`I1`-`I5`): `COID_A → COID_B` rejeitado, `COID_A → NULL`
rejeitado, schema de update não expõe `id`/`coid`,
`ObjectRepository.update()` não contorna a proteção, rollback preserva
a identidade original.

## Multi-IA readiness

Nenhum método público de `CoidManager` aceita
`provider`/`model`/`agent` (verificado por introspecção de assinatura
em teste dedicado). Duas origens independentes (simulando
`COMPETITIVE`) recebem COIDs distintos por padrão — nenhuma lógica de
agente participa da geração.

```
COMPETITIVE_READY = TRUE
COMPLEMENTARY_READY = TRUE
SEQUENTIAL_READY = TRUE
```
(estrutural — nenhum modo é implementado; ver `EDR_COUT_PIA_E3.md`.)

## COUT-PIA

COID é infraestrutura de identidade, não avaliação causal. Nenhum
código deste módulo deriva equivalência, importância, admissibilidade,
confiança ou ranking a partir de COID — `COID identity != COUT
equivalence`, exatamente como o módulo exige. `COID diferente` nunca é
interpretado como "divergência semântica"; isso pertence a
`CausalComparison` (contrato preparado, não implementado nesta
entrega).

## API status

`DEFERRED` — nenhuma evidência de exigência de endpoint HTTP para
COID Manager nesta fase; nenhum router criado/modificado.

## Arquivos

| Arquivo | Papel |
|---|---|
| `app/cognitive/services/coid_manager.py` | `CoidManager`, `ImportedCoidStatus`, `ImportedCoidValidation` |
| `app/cognitive/errors/codes.py` | +`PIA_8003_COID_INVALID`, +`PIA_8004_COID_COLLISION` |
| `app/cognitive/errors/exceptions.py` | +`CoidInvalidError`, +`CoidCollisionError` |
| `app/cognitive/repositories/object_repository.py` | `add()` traduz `PersistenceError` → `CoidCollisionError` |

## Testes

66 testes de E3.1/E3.1.1/E3.1.2 continuam passando (nenhum modificado
além do necessário) + 32 novos:

- **Geração** (G1-G6 + `generate_unique`): formato, unicidade entre
  múltiplas gerações, independência de payload/provider/sessão
  (verificado por introspecção de assinatura, não apenas por não uso),
  retry em colisão simulada, esgotamento de tentativas.
- **Validação** (V1-V5): aceitação de `UUID`/`str` válidos, rejeição
  de valor/tipo inválido, `None` rejeitado, idempotência da
  normalização.
- **Imutabilidade** (I1-I5): consolidação formal do contrato já
  implementado em E3.1.
- **Colisão** (C1-C5): tentativa explícita de persistir COID
  existente, erro mapeado para `PIA-8004` (não vaza
  `PersistenceError`), objeto/payload existente não alterado,
  rollback correto via `UnitOfWork`.
- **Import** (IMP1-IMP5): `VALID`/`INVALID`/`COLLISION`, sem
  auto-remap, resultado estruturalmente identificável
  (`ImportedCoidValidation.status`).
- **Multi-IA-ready**: duas origens independentes, ausência de
  parâmetro provider/model/agent em qualquer método público.
- **Integração contra PostgreSQL real**: round-trip completo (já
  existente) + **novo teste de colisão real** confirmando que a
  constraint de PK do banco de fato rejeita e é traduzida
  corretamente para `CoidCollisionError`.

Total: 32 testes novos, 100% de cobertura de linha em todo
`app/cognitive/` (incluindo o `services/` novo).

## Non-regression

`E1/E2`: suíte completa 553 passed, 3 skipped, 96,77% (acima do
threshold de 95%). `E3.1 FINAL`: os 66 testes de E3.1/E3.1.1/E3.1.2
continuam passando sem modificação de comportamento — a única mudança
em arquivo pré-existente de E3 foi a extensão de `ObjectRepository.add()`,
aditiva (novo `try/except` em torno da chamada já existente a
`super().add()`, nenhum comportamento anterior removido).

## Decisões

1. `add()` (não um método novo separado) é o ponto de tradução de
   colisão — é o único caminho de criação de `CognitiveObject`, então
   estender esse método garante que a proteção se aplica a todo
   chamador, não apenas a quem usar `CoidManager` explicitamente.
2. `assert_unique()`/`validate_imported_coid()` consideram
   soft-deleted (`include_deleted=True`) — identidade nunca é
   reciclada, mesmo por um objeto logicamente apagado.
3. `generate_unique()` foi incluído (não apenas `generate()` +
   `assert_unique()` manualmente) porque o módulo pede explicitamente
   uma política de "retry controlado" para colisão na geração local —
   evita que cada chamador reimplemente o mesmo laço.

## Limitações

- A tradução de `PersistenceError` → `CoidCollisionError` em `add()`
  assume que `cognitive_objects` não tem nenhuma unique constraint
  além da PK — verdadeiro hoje, mas frágil a mudanças futuras de
  schema sem revisão explícita (documentado no código-fonte).
- `generate_unique()` não é usado automaticamente por `ObjectRepository.add()`
  — quem cria um `CognitiveObject` hoje usa o `default=uuid.uuid4` do
  próprio `UUIDMixin` (sem passar por `CoidManager` para geração).
  `CoidManager.generate()`/`generate_unique()` ficam disponíveis para
  quando um módulo futuro precisar gerar um COID *antes* da construção
  do objeto (ex.: para referenciá-lo em outra estrutura antes de
  persistir) — não é o caminho usado pelo fluxo de criação simples
  atual, que continua funcionando exatamente como em E3.1.

## Itens deferidos

- CLID Manager, lineage, branch, merge, derivation graph: `E3.3`.
- Import/export completos (Synchronization Manager): `E3.11`.
- Remapeamento auditável de COID colidente: `E3.11`.
- Endpoints HTTP: nenhuma evidência de exigência nesta fase.
