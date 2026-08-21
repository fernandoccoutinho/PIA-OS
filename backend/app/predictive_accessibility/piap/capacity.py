"""
Tetos de capacidade da fronteira PIAP (`E5` — Patch 1).

```text
MAX_PIAP_INPUT_BYTES = 262144
MAX_PAYLOAD_REFERENCES = 256
MAX_APPROVAL_SCOPE_ITEMS = 32
MAX_PIAP_VERSION_NUMBER = 2147483647
```

## Por que este módulo existe separado

Na cadeia 101 a `E5.a` aceitava trabalho ilimitado: payload de qualquer
tamanho, qualquer quantidade de referências, qualquer quantidade de itens
de escopo e qualquer inteiro positivo de versão. Medido, um envelope de
5.000 referências custava 50 ms de desserialização, e um payload muito
abaixo de 256 KiB podia carregar um inteiro grande o bastante para o
parser JSON recusar com `ValueError` cru — erro que não pertence ao
vocabulário da camada.

O limite HTTP geral de 10 MiB não protege nada disso: ele lê o header
`Content-Length` declarado, não o corpo, e não existe quando a função
pública é chamada internamente.

```text
HTTP_LIMIT != PIAP_LIMIT
PUBLIC_FUNCTION_MUST_BE_SAFE_WHEN_CALLED_INTERNALLY = TRUE
UNBOUNDED_LINEAR_WORK != SAFE_RUNTIME
```

## Fonte única de verdade

Os quatro tetos vivem **aqui e somente aqui**. Repetir qualquer um deles
em `envelope.py` ou `authority.py` criaria duas fontes de verdade para o
mesmo contrato, e nada impediria que divergissem — o mesmo defeito que a
E4.11 fechou com `AuthorityContext.status` como fonte única do status de
autoridade.

```text
SINGLE_SOURCE_OF_TRUTH_FOR_CAPACITY = THIS_MODULE
DUPLICATED_CEILING_CONSTANT = DEFECT
```

## O que estes números são, e o que não são

São tetos duros normativos iniciais, congelados pelo Master. Não são
variável de ambiente, não são preferência de usuário, não são SLO e não
são política que o runtime possa afrouxar.

```text
HARD_CEILING != CONFIGURABLE_SETTING
HARD_CEILING != SERVICE_LEVEL_OBJECTIVE
APPROVED_INITIAL_HARD_CEILING = TRUE
```

## Independência

Os tetos não se derivam uns dos outros. Respeitar as duas cardinalidades
não autoriza um payload acima do teto de bytes, porque cada campo tem
comprimento próprio; e respeitar os bytes não autoriza cardinalidade
acima do teto, porque a montagem de N objetos é o custo que a
cardinalidade limita, não o tamanho do texto.

```text
CARDINALITY_WITHIN_LIMIT != BYTES_WITHIN_LIMIT
BYTES_WITHIN_LIMIT != CARDINALITY_WITHIN_LIMIT
```

Quando bytes e cardinalidade estouram juntos, o de bytes vence: ele é
verificado antes do decode, e a cardinalidade só é observável depois do
parse.

## Módulo puro

Sem I/O, sem dependência externa, sem import de `app.memory` ou
`app.cognitive`, sem enum e sem estado mutável. Um teto que pudesse ser
reatribuído em runtime não seria teto.
"""

MAX_PIAP_INPUT_BYTES = 262_144
"""Tamanho máximo, em bytes, do payload PIAP aceito na desserialização.

256 KiB. Verificado **antes** do decode UTF-8 e do parse JSON: medido, a
verificação de tamanho custa cerca de 111 ns, contra 14,6 ms para
desserializar um payload deste tamanho. Rejeitar cedo é praticamente
gratuito; rejeitar tarde paga o trabalho inteiro antes de recusá-lo.
"""

MAX_PAYLOAD_REFERENCES = 256
"""Quantidade máxima de itens em `PiapEnvelope.payload_refs`.

Verificado antes de materializar cada `SourceReference`. A validação de
ordem canônica e de ausência de duplicata é `O(N log N)` e materializa
uma tupla por referência; limitar `N` antes da montagem é o que torna
esse custo finito.
"""

MAX_APPROVAL_SCOPE_ITEMS = 32
"""Quantidade máxima de itens em `ApprovalBinding.approval_scope`.

Verificado antes de validar cada item. O escopo é o campo com a pior
razão custo/byte medida da camada, porque `validar_referencia_opaca`
percorre **cada caractere** chamando `unicodedata.category`: 1.000 itens
custam 20,8 KB e 1,80 ms, enquanto 100 referências custam 18,5 KB e
1,07 ms. Um teto de bytes protege mal este campo; ele precisa do seu
próprio teto de cardinalidade.
"""

MAX_PIAP_VERSION_NUMBER = 2_147_483_647
"""Maior número de versão aceito em qualquer versão transportada pelo PIAP.

Aplica-se uniformemente a `SourceReference.source_version`,
`ApprovalBinding.approval_version` e ao `expected_version` usado para
validá-la.

O valor não é arbitrário nem estético: é o maior inteiro positivo
representável pelos campos `Integer` de SQLAlchemy/PostgreSQL que o
PIA-OS já usa para versionar governança, acessibilidade, retenção e
experiência validada. Aceitar uma referência de versão que a própria
plataforma não consegue armazenar seria transportar uma promessa que o
sistema não pode cumprir.

Fechar o domínio pelo alto também fecha um defeito de fronteira medido:
sem teto, um inteiro decimal grande o bastante fazia o parser JSON do
CPython levantar `ValueError` cru — um erro de fora do vocabulário da
camada escapando pela função pública, num payload muito abaixo de
256 KiB.

```text
UNBOUNDED_POSITIVE_VERSION + RUNTIME_INTEGER_DIGIT_LIMIT
  -> RAW_VALUE_ERROR_BELOW_MAX_PIAP_INPUT_BYTES
RAW_VALUE_ERROR_AT_PIAP_BOUNDARY = DEFECT
```

O teto é de contrato, não de runtime: `sys.set_int_max_str_digits` **não**
é alterado. Mudar configuração global do processo para fazer uma entrada
caber é o oposto de validar a entrada.
"""

__all__ = [
    "MAX_APPROVAL_SCOPE_ITEMS",
    "MAX_PAYLOAD_REFERENCES",
    "MAX_PIAP_INPUT_BYTES",
    "MAX_PIAP_VERSION_NUMBER",
]
