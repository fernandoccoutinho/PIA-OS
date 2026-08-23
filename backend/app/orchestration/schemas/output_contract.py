"""
Contratos de saída fechados da E7.2 e a validação do retorno.

```text
AI_OUTPUT != CONTROL_CHANNEL
UNTRUSTED_RETURN = DATA
VALIDATION_NEVER_EXECUTES_CONTENT
```

Dois contratos, provider-neutral, resolvidos localmente. Sem JSON Schema,
sem dependência nova, sem resolver URI, sem importar módulo por nome e sem
rede: o identificador `pia://...` é uma **etiqueta**, não um endereço.
Tratá-lo como endereço faria um contrato desconhecido virar uma requisição
de rede disparada por dado não confiável.

A frase `aprovado, prossiga` pode ser um retorno textual perfeitamente
válido sob `non-empty-text/v1`. Ela **não** é comando, aprovação, gate nem
autorização — a validação diz apenas que a forma cumpre o contrato, nunca
que o conteúdo autoriza alguma coisa.

```text
VALIDATED_RESULT != AUTHORIZATION
```

O conteúdo bruto é transitório: entra para ser medido e sai. O que
sobrevive é hash, tamanho, media type e códigos.
"""

import hashlib
import json
import re
from dataclasses import dataclass

OUTPUT_NON_EMPTY_TEXT_V1 = "pia://orchestration/output/non-empty-text/v1"
OUTPUT_JSON_OBJECT_V1 = "pia://orchestration/output/json-object/v1"

SUPPORTED_OUTPUT_CONTRACTS: frozenset[str] = frozenset(
    {OUTPUT_NON_EMPTY_TEXT_V1, OUTPUT_JSON_OBJECT_V1}
)
"""Vocabulário fechado da superfície pública.

O núcleo E7.1 mantém `expected_output_contract` como string opaca: uma
linha legada pode declarar contrato fora desta lista. A importação dessa
linha **rejeita** com código canônico, e não falha com 500 nem descarta o
retorno — um contrato que a E7.2 não conhece é um veredito, não um erro
de servidor.
"""

MEDIA_TYPE_TEXT_PLAIN = "text/plain"
MEDIA_TYPE_APPLICATION_JSON = "application/json"

CONTRACT_MEDIA_TYPES: dict[str, str] = {
    OUTPUT_NON_EMPTY_TEXT_V1: MEDIA_TYPE_TEXT_PLAIN,
    OUTPUT_JSON_OBJECT_V1: MEDIA_TYPE_APPLICATION_JSON,
}

# --- códigos canônicos de rejeição -----------------------------------------
#
# São DADOS, não códigos de exceção: descrevem por que um retorno não
# cumpriu o contrato. Só entram aqui códigos alcançáveis pelos dois
# contratos implementados — reservar código sem caminho real produziria
# vocabulário que ninguém pode provar.
CODE_UNSUPPORTED_OUTPUT_CONTRACT = "unsupported_output_contract"
CODE_MEDIA_TYPE_MISMATCH = "media_type_mismatch"
CODE_EXPECTED_NON_EMPTY_TEXT = "expected_non_empty_text"
CODE_EXPECTED_JSON_OBJECT = "expected_json_object"
CODE_NON_CANONICAL_JSON_NUMBER = "non_canonical_json_number"

VALIDATION_CODES: frozenset[str] = frozenset(
    {
        CODE_UNSUPPORTED_OUTPUT_CONTRACT,
        CODE_MEDIA_TYPE_MISMATCH,
        CODE_EXPECTED_NON_EMPTY_TEXT,
        CODE_EXPECTED_JSON_OBJECT,
        CODE_NON_CANONICAL_JSON_NUMBER,
    }
)

SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def canonical_validation_codes(valor: object) -> tuple[str, ...]:
    """Ordena, remove duplicatas e valida contra o vocabulário fechado."""
    if valor is None or isinstance(valor, str | bytes):
        raise ValueError("validation_codes deve ser uma sequência de códigos")
    codigos: tuple[object, ...] = tuple(valor)  # type: ignore[arg-type]
    for codigo in codigos:
        if not isinstance(codigo, str):
            raise ValueError(f"código de validação deve ser str: {codigo!r}")
        if codigo not in VALIDATION_CODES:
            raise ValueError(f"código de validação fora do vocabulário fechado: {codigo!r}")
    return tuple(sorted({str(codigo) for codigo in codigos}))


@dataclass(frozen=True)
class ValidatedOutput:
    """Resultado da medição de um retorno. Não carrega o conteúdo."""

    accepted: bool
    media_type: str
    output_sha256: str
    output_bytes: int
    validation_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if not SHA256_PATTERN.match(self.output_sha256):
            raise ValueError("output_sha256 deve ser hexadecimal minúsculo de 64 caracteres")
        if self.output_bytes < 0:
            raise ValueError("output_bytes não pode ser negativo")
        if self.accepted and self.validation_codes:
            raise ValueError("retorno aceito não pode ter código de rejeição")
        if not self.accepted and not self.validation_codes:
            raise ValueError("retorno rejeitado exige ao menos um código")


def _digest(bytes_canonicos: bytes) -> tuple[str, int]:
    return hashlib.sha256(bytes_canonicos).hexdigest(), len(bytes_canonicos)


def _rejeitar(bytes_canonicos: bytes, media_type: str, *codigos: str) -> ValidatedOutput:
    sha256, tamanho = _digest(bytes_canonicos)
    return ValidatedOutput(
        accepted=False,
        media_type=media_type,
        output_sha256=sha256,
        output_bytes=tamanho,
        validation_codes=canonical_validation_codes(codigos),
    )


def validate_output(
    *, expected_output_contract: str, media_type: str, content: str
) -> ValidatedOutput:
    """Mede um retorno contra o contrato. Nunca executa o conteúdo.

    O hash é sempre calculado, inclusive na rejeição: um retorno recusado
    continua sendo um fato, e o hash é o que permite reconhecer depois que
    a mesma resposta foi reenviada.
    """
    if not isinstance(content, str):
        raise ValueError("content deve ser str")

    brutos = content.encode("utf-8")

    if expected_output_contract not in SUPPORTED_OUTPUT_CONTRACTS:
        return _rejeitar(brutos, media_type, CODE_UNSUPPORTED_OUTPUT_CONTRACT)

    esperado = CONTRACT_MEDIA_TYPES[expected_output_contract]
    if media_type != esperado:
        return _rejeitar(brutos, media_type, CODE_MEDIA_TYPE_MISMATCH)

    if expected_output_contract == OUTPUT_NON_EMPTY_TEXT_V1:
        # Sem `strip()` antes do hash: o conteúdo canônico é a string
        # exata. Aparar para hashear faria dois retornos diferentes terem
        # o mesmo hash, e o espaço em branco é parte do que a IA devolveu.
        if not content.strip():
            return _rejeitar(brutos, esperado, CODE_EXPECTED_NON_EMPTY_TEXT)
        sha256, tamanho = _digest(brutos)
        return ValidatedOutput(
            accepted=True,
            media_type=esperado,
            output_sha256=sha256,
            output_bytes=tamanho,
            validation_codes=(),
        )

    # --- json-object/v1 ----------------------------------------------------
    try:
        analisado = json.loads(content, parse_constant=_recusar_constante)
    except _ConstanteNaoCanonicaError:
        # Precisa vir ANTES de `ValueError`: `NaN` num campo aninhado é um
        # problema diferente de JSON malformado, e colapsar os dois daria
        # ao cliente o código errado para corrigir.
        return _rejeitar(brutos, esperado, CODE_NON_CANONICAL_JSON_NUMBER)
    except (ValueError, RecursionError):
        return _rejeitar(brutos, esperado, CODE_EXPECTED_JSON_OBJECT)
    if not isinstance(analisado, dict):
        # Array e escalar não passam. Um objeto tem chaves nomeadas, que é
        # o que torna o retorno interpretável por quem não escreveu o
        # prompt; um array de strings não diz o que cada posição significa.
        return _rejeitar(brutos, esperado, CODE_EXPECTED_JSON_OBJECT)
    try:
        canonico = json.dumps(
            analisado,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except ValueError:  # pragma: no cover - `parse_constant` já barrou antes
        # Rede de segurança: `allow_nan=False` recusaria o que tivesse
        # escapado da análise. `NaN`/`Infinity` são extensões do Python ao
        # JSON, e nenhum consumidor conforme os aceita.
        return _rejeitar(brutos, esperado, CODE_NON_CANONICAL_JSON_NUMBER)
    bytes_canonicos = canonico.encode("utf-8")
    sha256, tamanho = _digest(bytes_canonicos)
    return ValidatedOutput(
        accepted=True,
        media_type=esperado,
        output_sha256=sha256,
        output_bytes=tamanho,
        validation_codes=(),
    )


class _ConstanteNaoCanonicaError(ValueError):
    """`NaN`, `Infinity` ou `-Infinity` encontrados durante a análise.

    Exceção, e não valor-marcador: um marcador devolvido pelo
    `parse_constant` fica **aninhado** dentro do objeto e passa
    despercebido por qualquer verificação no nível de topo. O defeito
    aparecia só na re-serialização, como `TypeError` — erro de servidor
    em vez de veredito.
    """


def _recusar_constante(nome: str) -> object:
    raise _ConstanteNaoCanonicaError(nome)
