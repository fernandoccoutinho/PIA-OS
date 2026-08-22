"""
Gerador determinístico dos modelos públicos do `pia-os-sdk`.

```text
LIVE_OPENAPI -> CANONICAL_JSON_SNAPSHOT -> DETERMINISTIC_GENERATOR -> SDK
HAND_EDIT_GENERATED_MODELS = FORBIDDEN
REGENERATION_DIFF = ZERO
```

O snapshot é a fonte da verdade, não o SDK. Editar `models.py` à mão
faria o cliente divergir do contrato sem que nada acusasse: por isso o
arquivo gerado carrega o SHA-256 do snapshot e `--check` regenera em
diretório temporário exigindo igualdade byte a byte.

Determinismo vem de ordenação total: nomes de schema, propriedades e
membros de enum são todos emitidos em ordem alfabética. Nada depende da
ordem de iteração de um dicionário nem do sistema de arquivos.

Uso:

    python -m tools.generate_models            # regenera models.py
    python -m tools.generate_models --check    # falha se houver delta
"""

from __future__ import annotations

import argparse
import hashlib
import json
import keyword
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parents[1]
SNAPSHOT = RAIZ / "schema" / "openapi_chain107_r1.json"
DESTINO = RAIZ / "pia_os_sdk" / "models.py"

# Envelope de sucesso da avaliação. O nome vem do OpenAPI com o parâmetro
# genérico embutido; o SDK o expõe com um alias legível.
ENVELOPE_OPENAPI = "SuccessResponse_PublicEvaluationResponse_"
ENVELOPE_PUBLICO = "SuccessResponsePublicEvaluationResponse"

_NAO_IDENTIFICADOR = re.compile(r"[^0-9a-zA-Z_]")


def _sha256(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def _nome_classe(nome: str) -> str:
    return ENVELOPE_PUBLICO if nome == ENVELOPE_OPENAPI else nome


def _nome_membro(valor: str) -> str:
    bruto = _NAO_IDENTIFICADOR.sub("_", valor).upper().strip("_")
    if not bruto or bruto[0].isdigit():
        bruto = f"V_{bruto}"
    if keyword.iskeyword(bruto.lower()):
        bruto = f"{bruto}_"
    return bruto


def _literal(valor: Any) -> str:
    """Literal Python, não JSON.

    `json.dumps` emitiria `false`/`true`/`null`, que não são identificadores
    válidos em Python — o arquivo gerado nem importaria.
    """
    return repr(valor)


def _tipo(esquema: dict[str, Any]) -> str:
    """Traduz um sub-schema para anotação Python. Total e sem heurística.

    Um tipo desconhecido levanta em vez de virar `Any`: silenciar aqui
    produziria um SDK que aceita o que o servidor recusa.
    """
    if "$ref" in esquema:
        # Sem aspas: `from __future__ import annotations` já torna toda
        # anotação uma string, e `"A" | "B"` seria um `TypeError` real na
        # avaliação. As referências para frente são resolvidas pelo
        # `model_rebuild()` no fim do arquivo.
        return _nome_classe(esquema["$ref"].rsplit("/", 1)[1])
    if "const" in esquema:
        return f"Literal[{_literal(esquema['const'])}]"
    if "oneOf" in esquema or "anyOf" in esquema:
        variantes = esquema.get("oneOf") or esquema["anyOf"]
        partes = [_tipo(v) for v in variantes]
        discriminador = esquema.get("discriminator", {}).get("propertyName")
        uniao = " | ".join(dict.fromkeys(partes))
        if discriminador:
            return f'Annotated[{uniao}, Field(discriminator="{discriminador}")]'
        return uniao
    tipo = esquema.get("type")
    if tipo is None:
        # Campo deliberadamente livre no contrato público (ex.: `detail` de
        # erro, cuja forma varia por tipo). `object` preserva o valor sem
        # que o cliente invente estrutura que o servidor não prometeu.
        return "object"
    if tipo == "null":
        return "None"
    if tipo == "string":
        return "datetime" if esquema.get("format") == "date-time" else "str"
    if tipo == "integer":
        return "int"
    if tipo == "number":
        return "float"
    if tipo == "boolean":
        return "bool"
    if tipo == "array":
        if "prefixItems" in esquema:
            fixos = ", ".join(_tipo(item) for item in esquema["prefixItems"])
            return f"tuple[{fixos}]"
        interno = _tipo(esquema.get("items", {"type": "string"}))
        return f"tuple[{interno}, ...]"
    if tipo == "object":
        return "dict[str, object]"
    raise ValueError(f"tipo não mapeado no snapshot: {esquema!r}")


def _default_literal(anotacao: str, valor: Any) -> str:
    """Coage o default do schema ao tipo anotado.

    JSON só tem array; a anotação pode ser `tuple`. Emitir `= []` num campo
    `tuple[str, ...]` cria default MUTÁVEL e faz o serializador do pydantic
    avisar que o valor "pode não ser o esperado" — aviso que, deixado no
    lugar, ensina a ignorar avisos.
    """
    if isinstance(valor, list) and anotacao.startswith("tuple["):
        return "()" if not valor else "(" + ", ".join(repr(v) for v in valor) + ",)"
    return _literal(valor)


def _line_length() -> int:
    """Lê o `line-length` do `pyproject.toml` — nunca um número solto aqui.

    Um literal duplicado se descola do arquivo de configuração no primeiro
    ajuste e reintroduz a divergência de idempotência: o gerador emite num
    comprimento, o Black da linha de comando reformata noutro, e o
    `REGENERATION_DIFF = ZERO` passa a falhar sem que nada tenha mudado no
    contrato.

    ```text
    GENERATOR_LINE_LENGTH == PROJECT_LINE_LENGTH
    ```
    """
    import tomllib

    configuracao = tomllib.loads(
        (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(encoding="utf-8")
    )
    valor = configuracao.get("tool", {}).get("black", {}).get("line-length")
    if not isinstance(valor, int):
        raise RuntimeError("pyproject.toml não declara [tool.black] line-length")
    return valor


LIMITE_LINHA = _line_length()


def _quebrar(anotacao: str, recuo: int) -> list[str]:
    """Formata a anotação em várias linhas quando não cabe no limite.

    O arquivo é gerado, mas continua sujeito ao mesmo `ruff` do resto do
    repositório: um gerador que emite linha longa obrigaria a excluir o
    arquivo do lint, e arquivo fora do lint deixa de ser verificado.

    Trata as duas formas longas que o snapshot produz — `tuple[X, ...]` e
    `Annotated[A | B, Field(...)]` — e devolve a anotação inteira quando
    não reconhece a forma, em vez de cortar no meio de um token.
    """
    espaco = " " * recuo
    if len(espaco) + len(anotacao) <= LIMITE_LINHA:
        return [anotacao]
    if anotacao.startswith("tuple[") and anotacao.endswith(", ...]"):
        interno = anotacao[len("tuple[") : -len(", ...]")]
        linhas = ["tuple["]
        linhas += [f"    {linha}" for linha in _quebrar(interno, recuo + 4)]
        linhas[-1] += ","
        linhas.append("    ...,")
        linhas.append("]")
        return linhas
    if anotacao.startswith("Annotated[") and anotacao.endswith("]"):
        interno = anotacao[len("Annotated[") : -1]
        separador = interno.rfind(", Field(")
        if separador != -1:
            uniao = interno[:separador]
            campo = interno[separador + 2 :]
            linhas = ["Annotated["]
            partes = uniao.split(" | ")
            for indice, parte in enumerate(partes):
                sufixo = "" if indice == len(partes) - 1 else " |"
                linhas.append(f"    {parte}{sufixo}")
            linhas[-1] += ","
            linhas.append(f"    {campo},")
            linhas.append("]")
            return linhas
    return [anotacao]


def _linha_campo(nome: str, anotacao: str, sufixo: str = "") -> str:
    linha = f"    {nome}: {anotacao}{sufixo}"
    if len(linha) <= LIMITE_LINHA:
        return linha
    partes = _quebrar(anotacao, 8)
    if len(partes) == 1:
        return linha
    corpo = "\n".join(f"        {parte}" for parte in partes)
    return f"    {nome}: (\n{corpo}\n    ){sufixo}"


def _campo(nome: str, esquema: dict[str, Any], obrigatorio: bool) -> str:
    anotacao = _tipo(esquema)
    if not obrigatorio and "default" not in esquema:
        if "None" not in anotacao.split(" | "):
            anotacao = f"{anotacao} | None"
        return _linha_campo(nome, anotacao, " = None")
    if "default" in esquema:
        padrao = _default_literal(anotacao, esquema["default"])
        return _linha_campo(nome, anotacao, f" = {padrao}")
    return _linha_campo(nome, anotacao)


def _enum(nome: str, esquema: dict[str, Any]) -> list[str]:
    linhas = [f"class {nome}(StrEnum):"]
    descricao = esquema.get("description")
    if descricao:
        linhas.append(f'    """{descricao.splitlines()[0].strip()}"""')
        linhas.append("")
    for valor in sorted(esquema["enum"]):
        linhas.append(f"    {_nome_membro(valor)} = {_literal(valor)}")
    linhas.append("")
    linhas.append("")
    return linhas


def _modelo(nome: str, esquema: dict[str, Any]) -> list[str]:
    linhas = [f"class {_nome_classe(nome)}(PiaModel):"]
    descricao = esquema.get("description")
    if descricao:
        linhas.append(f'    """{descricao.splitlines()[0].strip()}"""')
        linhas.append("")
    propriedades = esquema.get("properties", {})
    obrigatorios = set(esquema.get("required", ()))
    if not propriedades:
        linhas.append("    pass")
    else:
        # Obrigatórios antes dos opcionais: exigência da própria linguagem
        # para defaults, e ordem alfabética dentro de cada grupo garante
        # que o arquivo gerado não dependa da ordem do dicionário.
        nomes = sorted(propriedades)
        for campo in [n for n in nomes if n in obrigatorios]:
            linhas.append(_campo(campo, propriedades[campo], True))
        for campo in [n for n in nomes if n not in obrigatorios]:
            linhas.append(_campo(campo, propriedades[campo], False))
    linhas.append("")
    linhas.append("")
    return linhas


def _formatar(codigo: str) -> str:
    """Passa o resultado pelo Black, com o mesmo `line-length` do projeto.

    Sem isso, `black` reformataria `models.py` depois da geração e o
    `--check` do gerador passaria a acusar delta — o repositório teria
    dois donos do mesmo arquivo e um deles sempre perderia.

    ```text
    GENERATOR_OUTPUT == FORMATTER_OUTPUT
    ```
    """
    import black

    return str(black.format_str(codigo, mode=black.Mode(line_length=LIMITE_LINHA)))


def gerar(snapshot_texto: str) -> str:
    documento = json.loads(snapshot_texto)
    schemas = documento["components"]["schemas"]
    digest = _sha256(snapshot_texto)

    cabecalho = [
        '"""',
        "Modelos públicos do `pia-os-sdk` — ARQUIVO GERADO, não editar à mão.",
        "",
        "```text",
        f"OPENAPI_SNAPSHOT_SHA256 = {digest}",
        "GENERATOR = tools/generate_models.py",
        "HAND_EDIT = FORBIDDEN",
        "```",
        "",
        "Regenere com `python -m tools.generate_models` e verifique com",
        "`--check`, que exige delta zero. Uma edição manual sobrevive até a",
        "próxima regeneração e, nesse intervalo, o cliente aceita o que o",
        "servidor recusa.",
        '"""',
        "",
        "from __future__ import annotations",
        "",
        "from datetime import datetime",
        "from enum import StrEnum",
        "from typing import Annotated, Literal",
        "",
        "from pydantic import BaseModel, ConfigDict, Field",
        "",
        f'OPENAPI_SNAPSHOT_SHA256 = "{digest}"',
        "",
        "",
        "class PiaModel(BaseModel):",
        '    """Base dos modelos públicos.',
        "",
        '    `extra="forbid"` espelha o servidor: um campo desconhecido é erro',
        "    do cliente, e aceitá-lo em silêncio esconderia divergência de",
        "    contrato até o servidor recusar a requisição.",
        '    """',
        "",
        '    model_config = ConfigDict(extra="forbid", frozen=True)',
        "",
        "",
    ]

    corpo: list[str] = []
    for nome in sorted(schemas):
        esquema = schemas[nome]
        if "enum" in esquema:
            corpo.extend(_enum(nome, esquema))
        else:
            corpo.extend(_modelo(nome, esquema))

    nomes_modelo = sorted(_nome_classe(n) for n, e in schemas.items() if "enum" not in e)
    rodape = [
        "# Referências para frente: os schemas são emitidos em ordem",
        "# alfabética, então um modelo pode citar outro definido depois.",
        "# `model_rebuild()` resolve todas de uma vez, na ordem em que foram",
        "# emitidas — sem isso, pydantic deixaria modelos incompletos e a",
        "# falha só apareceria na primeira validação.",
        "for _modelo in (",
    ]
    for nome in nomes_modelo:
        rodape.append(f"    {nome},")
    rodape.extend(
        [
            "):",
            "    _modelo.model_rebuild()",
            "",
            "del _modelo",
            "",
            "",
            "__all__ = [",
            '    "OPENAPI_SNAPSHOT_SHA256",',
            '    "PiaModel",',
        ]
    )
    for nome in sorted(_nome_classe(n) for n in schemas):
        rodape.append(f'    "{nome}",')
    rodape.append("]")
    rodape.append("")

    bruto = "\n".join(cabecalho + corpo + rodape)
    return _formatar(bruto)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="generate_models")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Regenera em diretório temporário e exige igualdade byte a byte.",
    )
    args = parser.parse_args(argv)

    snapshot_texto = SNAPSHOT.read_text(encoding="utf-8")
    gerado = gerar(snapshot_texto)

    if not args.check:
        DESTINO.write_text(gerado, encoding="utf-8")
        print(f"gerado   : {DESTINO}")
        print(f"snapshot : {_sha256(snapshot_texto)}")
        return 0

    if not DESTINO.exists():
        print("FAIL: models.py não existe; execute o gerador", file=sys.stderr)
        return 1
    atual = DESTINO.read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory() as temporario:
        referencia = Path(temporario) / "models.py"
        referencia.write_text(gerado, encoding="utf-8")
        iguais = referencia.read_bytes() == atual.encode("utf-8")
    if not iguais:
        print(
            "FAIL: models.py diverge do snapshot (REGENERATION_DIFF != 0)",
            file=sys.stderr,
        )
        return 1
    print("OK: REGENERATION_DIFF = 0")
    print(f"snapshot sha256 = {_sha256(snapshot_texto)}")
    return 0


if __name__ == "__main__":  # pragma: no cover - entrypoint
    raise SystemExit(main())
