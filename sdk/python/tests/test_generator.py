"""
Gerador e snapshot — determinismo e checagem de regeneração.

```text
REGENERATION_DIFF = ZERO
HAND_EDIT_GENERATED_MODELS = FORBIDDEN
STRIP_VOLATILE != STRIP_CONTRACT
```

Estes testes não sobem o backend: operam sobre o snapshot já congelado.
A correspondência entre snapshot e `app.openapi()` vivo é medida do lado
do backend, em `tests/static/test_e6_sdk_boundary.py`.
"""

from __future__ import annotations

import hashlib
import json
import pathlib

import pytest

from tools import generate_models, snapshot_openapi

RAIZ = pathlib.Path(__file__).resolve().parents[1]
SNAPSHOT = RAIZ / "schema" / "openapi_chain107_r1.json"
MODELOS = RAIZ / "pia_os_sdk" / "models.py"


def test_gen01_check_passa_na_arvore_entregue() -> None:
    assert generate_models.main(["--check"]) == 0


def test_gen02_geracao_e_deterministica() -> None:
    """Duas execuções sobre o mesmo snapshot produzem bytes idênticos."""
    texto = SNAPSHOT.read_text(encoding="utf-8")
    assert generate_models.gerar(texto) == generate_models.gerar(texto)


def test_gen03_o_arquivo_gerado_bate_com_o_gerador() -> None:
    esperado = generate_models.gerar(SNAPSHOT.read_text(encoding="utf-8"))
    assert MODELOS.read_text(encoding="utf-8") == esperado


def test_gen04_edicao_manual_e_detectada(tmp_path: pathlib.Path) -> None:
    """`--check` precisa reprovar uma edição, não apenas existir."""
    original = MODELOS.read_text(encoding="utf-8")
    MODELOS.write_text(original + "\n# edicao manual\n", encoding="utf-8")
    try:
        assert generate_models.main(["--check"]) == 1
    finally:
        MODELOS.write_text(original, encoding="utf-8")
    assert generate_models.main(["--check"]) == 0


def test_gen05_o_sha_declarado_e_o_do_snapshot() -> None:
    digest = hashlib.sha256(SNAPSHOT.read_bytes()).hexdigest()
    assert f'OPENAPI_SNAPSHOT_SHA256 = "{digest}"' in MODELOS.read_text(encoding="utf-8")


def test_gen06_o_snapshot_e_canonico() -> None:
    """UTF-8, chaves ordenadas, separadores compactos, newline final."""
    texto = SNAPSHOT.read_text(encoding="utf-8")
    assert texto.endswith("\n")
    documento = json.loads(texto)
    recanonizado = (
        json.dumps(documento, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    )
    assert texto == recanonizado


def test_gen07_o_snapshot_nao_contem_campo_volatil() -> None:
    """`generated_at` mudaria a cada processo e quebraria o delta zero."""
    documento = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    assert "generated_at" not in documento["info"].get("x-metadata", {})


def test_gen08_a_remocao_de_volateis_e_enumerada_e_nao_toca_contrato() -> None:
    documento = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    sujo = json.loads(json.dumps(documento))
    sujo["info"].setdefault("x-metadata", {})["generated_at"] = "2020-01-01T00:00:00+00:00"
    limpo = snapshot_openapi.strip_volatile(sujo)
    assert limpo == documento
    assert snapshot_openapi.VOLATILE_POINTERS == (("info", "x-metadata", "generated_at"),)


def test_gen09_strip_volatile_nao_remove_schema_nem_path() -> None:
    documento = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    limpo = snapshot_openapi.strip_volatile(documento)
    assert set(limpo["paths"]) == set(documento["paths"])
    assert set(limpo["components"]["schemas"]) == set(documento["components"]["schemas"])


def test_gen10_tipo_desconhecido_falha_em_vez_de_virar_any() -> None:
    """Silenciar aqui produziria um SDK que aceita o que o servidor recusa."""
    with pytest.raises(ValueError):
        generate_models._tipo({"type": "quaternion"})


def test_gen11_default_de_array_vira_tupla() -> None:
    """Default mutável em campo `tuple` gera aviso de serialização."""
    assert generate_models._default_literal("tuple[str, ...]", []) == "()"
    assert generate_models._default_literal("tuple[str, ...]", ["a"]) == "('a',)"
    assert generate_models._default_literal("str", "x") == "'x'"


def test_gen12_o_snapshot_publica_o_esquema_bearer_da_e6_2() -> None:
    """O SDK só pode representar Bearer porque o servidor o declara."""
    documento = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    esquema = documento["components"]["securitySchemes"]["PIAServiceBearer"]
    assert esquema["type"] == "http"
    assert esquema["scheme"] == "bearer"
    operacao = documento["paths"]["/api/v1/predictive-evaluations"]["post"]
    assert operacao["security"] == [{"PIAServiceBearer": []}]


def test_gen13_nenhum_default_gerado_e_mutavel_compartilhado() -> None:
    """Default mutável é estado global disfarçado de campo.

    Duas instâncias que não recebem o campo passariam a compartilhar a
    MESMA lista; mutar uma alteraria a outra. Pydantic copia defaults, o
    que esconde o problema — a prova é sobre o CÓDIGO GERADO, não sobre o
    comportamento do runtime que hoje o mascara.

    ```text
    MUTABLE_DEFAULT = SHARED_STATE
    ```
    """
    import ast

    arvore = ast.parse(MODELOS.read_text(encoding="utf-8"))
    for no in ast.walk(arvore):
        if isinstance(no, ast.AnnAssign) and no.value is not None:
            assert not isinstance(no.value, ast.List | ast.Dict | ast.Set), ast.unparse(no)


def test_gen14_instancias_nao_compartilham_o_default_de_colecao() -> None:
    """A prova de comportamento, complementar à do código gerado."""
    from pia_os_sdk import models as m

    a = m.PublicComparabilityKey.model_construct()
    b = m.PublicComparabilityKey.model_construct()
    primeira = m.StatusResponse.model_construct()
    segunda = m.StatusResponse.model_construct()
    assert primeira.components == () == segunda.components
    assert primeira.components is segunda.components  # tupla vazia é imutável
    assert a is not b


def test_gen15_o_gerador_usa_o_line_length_do_projeto() -> None:
    """Literal duplicado se descolaria do `pyproject` no primeiro ajuste."""
    import tomllib

    configuracao = tomllib.loads((RAIZ / "pyproject.toml").read_text(encoding="utf-8"))
    black_length = configuracao["tool"]["black"]["line-length"]
    ruff_length = configuracao["tool"]["ruff"]["line-length"]
    assert black_length == generate_models.LIMITE_LINHA
    assert ruff_length == black_length


def test_gen16_nenhuma_linha_gerada_excede_o_limite() -> None:
    for numero, linha in enumerate(MODELOS.read_text(encoding="utf-8").splitlines(), 1):
        assert len(linha) <= generate_models.LIMITE_LINHA, (numero, len(linha))


def test_gen17_black_nao_e_dependencia_de_runtime_do_sdk() -> None:
    """`black` é ferramenta de geração, não do pacote instalado.

    O import vive dentro de `_formatar`, então instalar o SDK não arrasta
    um formatador para produção.
    """
    import tomllib

    configuracao = tomllib.loads((RAIZ / "pyproject.toml").read_text(encoding="utf-8"))
    runtime = configuracao["project"]["dependencies"]
    assert not [d for d in runtime if d.lower().startswith("black")], runtime
    dev = configuracao["project"]["optional-dependencies"]["dev"]
    assert [d for d in dev if d.startswith("black==")], dev
    for caminho in sorted((RAIZ / "pia_os_sdk").glob("*.py")):
        assert "black" not in caminho.read_text(encoding="utf-8"), caminho.name
