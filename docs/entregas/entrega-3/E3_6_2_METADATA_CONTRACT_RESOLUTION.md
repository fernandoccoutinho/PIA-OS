# E3.6.2 — Metadata Contract Resolution

**Tipo**: resolução documental. Nenhum código de produção, teste ou
migração é criado ou alterado por este módulo.

**Baseline**: `E3.0`–`E3.6.1d` congelada, 21 patches aplicados e
auditados. `E3.6` permanece funcionalmente congelado — nada do que
`LIB-06` implementou é revisto aqui.

## Por que este documento existe

Durante a inspeção obrigatória que precede `E3.7`, a tabela de
ownership de `E3_IMPLEMENTATION_SEQUENCE.md` foi lida como se
atribuísse a `E3.6` uma primitiva persistente chamada `Metadata`, e a
linha de `E3.7` diz que o `Index Manager` "consome
`Metadata`/`CognitiveObject` já existentes". Como nenhum modelo,
tabela, repositório ou serviço de `Metadata` existe em
`app/cognitive/`, a pergunta legítima era: `LIB-06` deixou uma
obrigação congelada por cumprir?

A resposta, apurada por inspeção documental completa, é **não** — mas a
ambiguidade era real e precisava ser fechada antes que `E3.7` fosse
construído sobre uma dependência inexistente.

## Evidência apurada

1. **`E3_DOMAIN_MODEL_DRAFT.md` não define `Metadata` como primitiva.**
   As seções de primitivas são `CognitiveObject`,
   `CognitiveDistinction`, `ProvenanceRecord`,
   `CausalHistory`/`CausalHistoryEvent`, `AccessibilityState`,
   `CausalClassRef`, `TransformationRecord`, `CausalComparison` e
   `LineageEdge`. O índice de dependências entre primitivas, ao final
   do documento, também não a lista. A única ocorrência da palavra no
   Draft inteiro está dentro do **nome do módulo** `LIB-06`, na linha
   de propriedade de `ProvenanceRecord`.

2. **`Metadata` já existe em `E1`/`E2`, e não é do domínio cognitivo.**
   `E3_BASELINE_INTERFACE_MAP.md` a registra como schema Pydantic
   reutilizável de `app.schemas.common` — `extra: dict[str, object]`,
   metadados livres de **resposta de API**, ao lado de
   `PaginationParams`/`SortParams`/`PaginationMeta`/`Message`. A
   orientação daquele mapa é compor esses schemas, nunca
   reimplementá-los.

3. **`CognitiveObject` não tem, e não pode ganhar, campo de metadata
   por esta via.** O Draft é explícito: nenhum campo de
   conteúdo/domínio além de `coid`, `clid`, `accessibility` e os
   timestamps herdados de `BaseModel`.

4. **Nenhum código depende de `Metadata` cognitivo.** Verificado por
   inspeção de `app/cognitive/`, `tests/unit/cognitive/`,
   `tests/integration/cognitive/` e de todas as migrações: zero
   referências.

5. **`E3_6_LIB06_PROVENANCE_ACCESSIBILITY.md` não menciona `Metadata`
   nenhuma vez.** `LIB-06` nunca declarou a primitiva implementada nem
   deferida — o termo simplesmente não fazia parte do contrato que
   aquele módulo executou.

## Resolução

```text
METADATA_CONTRACT_SUFFICIENCY = INSUFFICIENT_FOR_NEW_DOMAIN_PRIMITIVE

INTERPRETATION = I1 + I3

COGNITIVE_DOMAIN_METADATA_PRIMITIVE = NONE
E1_E2_COMMON_METADATA               = API_RESPONSE_SCHEMA_ONLY
LIB06_METADATA_TERM                 = HISTORICAL_MODULE_NAMING_UMBRELLA

PROVENANCE_STATUS    = EXISTING_STRUCTURED_MECHANISM
ACCESSIBILITY_STATUS = EXISTING_STRUCTURED_MECHANISM

ARBITRARY_METADATA_DICT          = NOT_AUTHORIZED
COGNITIVE_OBJECT_METADATA_COLUMN = NOT_AUTHORIZED

TRANSCRIPT_AUTO_STORAGE = NONE

E3_7_INDEX_INPUT       = TYPED_EXISTING_COGNITIVE_STRUCTURES
INDEX_SOURCE_OF_TRUTH  = FALSE
INDEX_REBUILDABLE      = TRUE

FUTURE_COGNITIVE_METADATA = REQUIRES_EXPLICIT_EDR
```

`I1` — o termo `Metadata` no título `LIB-06 Metadata Manager +
Provenance + Accessibility` é **guarda-chuva de nomenclatura do
módulo**, não a designação de uma entidade. Os mecanismos
estruturados que `LIB-06` efetivamente entregou —
`ProvenanceRecord` e `AccessibilityState`/`AccessibilityManager` —
**são** os metadados cognitivos do PIA, tipados e com contrato
próprio.

`I3` — `app.schemas.common.Metadata` permanece o que sempre foi:
schema de resposta de API de `E1`/`E2`. Não é entidade do domínio
cognitivo e **não deve ser reutilizado como armazenamento
cognitivo**.

## O que fica proibido a partir daqui

Nenhum destes pode ser criado sem um EDR novo e explícito:

- modelo, tabela, repositório ou manager de `Metadata` cognitivo;
- coluna de metadata em `CognitiveObject`;
- dicionário arbitrário chave-valor como campo de domínio.

A razão não é purismo de modelagem. Um `dict[str, object]` livre
anexado a objetos cognitivos é a via lateral mais fácil para
armazenar prompts, respostas e transcripts sem que ninguém decida
armazená-los — exatamente o que `TRANSCRIPT_AUTO_STORAGE = NONE` e o
princípio congelado `LOGICAL IMMUTABILITY != PHYSICAL DUPLICATION`
existem para impedir. Um campo assim passaria pela auditoria de
schema como "uma coluna JSON" e só apareceria como problema depois de
populado.

## Consequência direta para E3.7 / LIB-07

O `Index Manager` consome **estruturas cognitivas tipadas já
existentes** — `CognitiveObject` (COID/CLID), `AccessibilityState`,
`LineageEdge`, `Relationship`, `TransformationRecord`,
`ProvenanceRecord` —, não um saco de metadata livre.

Duas regras derivam disso e valem para o desenho de `E3.7`:

```text
INDEX != METADATA
INDEX != SOURCE OF TRUTH
```

O índice é estrutura **derivada e reconstruível**. A Biblioteca
Cognitiva permanece a fonte da verdade; nada pode existir apenas no
índice, e destruir o índice não pode destruir informação.

## Débito futuro

Metadata cognitivo persistente continua sendo uma possibilidade
legítima de arquitetura — apenas não uma obrigação pendente de `E3.6`.
Se algum módulo futuro precisar dele, o caminho é um EDR próprio que
decida explicitamente: natureza (entidade ou atributo), âncora
(`coid`/`clid`/`CognitiveDistinction`), identidade, forma (livre ou
catálogo tipado), cardinalidade, lifecycle, interação com Provenance e
Accessibility, limite de armazenamento e contrato de indexação.
Nenhuma dessas decisões é dedutível da baseline congelada — foi
precisamente por isso que este módulo parou e pediu decisão em vez de
inventar semântica.

## Escopo desta resolução

```text
FILES_MODIFIED           = 2 (este documento + nota em E3_IMPLEMENTATION_SEQUENCE.md)
PRODUCTION_CODE_MODIFIED = NO
TESTS_MODIFIED           = NO
MIGRATIONS_MODIFIED      = NO
DOMAIN_MODEL_MODIFIED    = NO
```

O texto histórico da tabela de ownership é preservado — `Metadata` não
é apagado dela. A nota acrescentada registra que aquele termo não
designa primitiva persistente adicional, sem reescrever
retroativamente a história do projeto.
