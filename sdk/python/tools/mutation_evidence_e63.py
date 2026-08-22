"""
Arnês de mutação real do `pia-os-sdk` — `baseline PASS -> mutante FAIL`.

```text
TEXT_REPLACE_PLUS_STRING_ASSERT != MUTANT_DEATH
MUTANT_DEATH = TARGET_TEST_FAILS_ON_MUTATED_CODE
```

Mesmo instrumento adotado na E6.2 R1 depois do achado M2 da auditoria:
cada mutante é aplicado no FONTE, em cópia isolada da árvore, e o
teste-alvo é executado de verdade. Uma alteração de string em memória
seguida de asserção textual não prova guarda alguma.

Casos que só podem ser verificados por ausência de símbolo são rotulados
`CHARACTERIZATION` e ficam fora da contagem de mortes.

Uso:

    python -m tools.mutation_evidence_e63
    python -m tools.mutation_evidence_e63 --only mS1
"""

from __future__ import annotations

import argparse
import dataclasses
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

SDK = Path(__file__).resolve().parents[1]
REPO = SDK.parents[1]
BACKEND = REPO / "backend"
PYTEST = BACKEND / ".venv" / "bin" / "pytest"

_IGNORAR = shutil.ignore_patterns(
    ".venv", "__pycache__", "htmlcov", ".pytest_cache", "*.pyc", ".coverage*", ".git"
)


@dataclasses.dataclass(frozen=True)
class Mutante:
    ident: str
    descricao: str
    arquivo: str  # relativo à raiz do repositório
    de: str
    para: str
    alvo: tuple[str, ...]  # relativo ao cwd de execução
    cwd: str  # "sdk/python" ou "backend"


@dataclasses.dataclass(frozen=True)
class Caracterizacao:
    ident: str
    descricao: str
    alvo: str
    motivo: str


MUTANTES: tuple[Mutante, ...] = (
    Mutante(
        "mS1",
        "alterar a rota de avaliação",
        "sdk/python/pia_os_sdk/client.py",
        '_PATH_EVALUATE = "/api/v1/predictive-evaluations"',
        '_PATH_EVALUATE = "/api/v1/predictive-evaluation"',
        ("tests/test_client.py",),
        "sdk/python",
    ),
    Mutante(
        "mS2",
        "omitir o header Bearer também na operação autenticada",
        "sdk/python/pia_os_sdk/client.py",
        '            cabecalhos["Authorization"] = f"Bearer {self.__credential}"\n',
        "            pass\n",
        ("tests/test_client.py",),
        "sdk/python",
    ),
    Mutante(
        "mS3",
        "importar o backend (app) no runtime do SDK",
        "sdk/python/pia_os_sdk/errors.py",
        "from typing import Any",
        "from typing import Any\n\nimport app  # noqa: F401",
        ("tests/static/test_e6_sdk_boundary.py",),
        "backend",
    ),
    Mutante(
        "mS4",
        "importar SQLAlchemy no runtime do SDK",
        "sdk/python/pia_os_sdk/errors.py",
        "from typing import Any",
        "from typing import Any\n\nimport sqlalchemy  # noqa: F401",
        ("tests/static/test_e6_sdk_boundary.py",),
        "backend",
    ),
    Mutante(
        "mS5",
        "introduzir cálculo de rota científica no cliente",
        "sdk/python/pia_os_sdk/client.py",
        '        corpo = request.model_dump(mode="json")',
        (
            "        from pia_os_sdk.models import PublicRoute\n\n"
            "        _rota_local = PublicRoute\n"
            '        corpo = request.model_dump(mode="json")\n'
            "        predictive_route_batch = _rota_local"
        ),
        ("tests/static/test_e6_sdk_boundary.py",),
        "backend",
    ),
    Mutante(
        "mS6",
        "reinterpretar 503 como 429",
        "sdk/python/pia_os_sdk/errors.py",
        "        self.status_code = status_code",
        "        self.status_code = 429 if status_code == 503 else status_code",
        ("tests/test_client.py",),
        "sdk/python",
    ),
    Mutante(
        "mS7",
        "retirar a checagem de regeneração do gerador",
        "sdk/python/tools/generate_models.py",
        "    if not iguais:",
        "    if False:",
        ("tests/test_generator.py",),
        "sdk/python",
    ),
    Mutante(
        "mS8",
        "editar à mão um modelo gerado (delta de regeneração)",
        "sdk/python/pia_os_sdk/models.py",
        "class PiaModel(BaseModel):",
        "class PiaModel(BaseModel):\n    # edicao manual proibida\n",
        ("tests/test_generator.py",),
        "sdk/python",
    ),
    Mutante(
        "mS9",
        "aceitar campo desconhecido na resposta (extra permissivo)",
        "sdk/python/pia_os_sdk/models.py",
        'model_config = ConfigDict(extra="forbid", frozen=True)',
        'model_config = ConfigDict(extra="allow", frozen=True)',
        ("tests/test_client.py",),
        "sdk/python",
    ),
    Mutante(
        "mS10",
        "expor a credencial no repr do cliente",
        "sdk/python/pia_os_sdk/client.py",
        'return f"PiaClient(base_url={self._base_url!r}, timeout={self._timeout!r})"',
        (
            'return (\n            f"PiaClient(base_url={self._base_url!r}, "\n'
            '            f"credential={self.__credential!r})"\n        )'
        ),
        ("tests/test_client.py",),
        "sdk/python",
    ),
    Mutante(
        "mS12",
        "restaurar o Bearer nas operações públicas de observabilidade",
        "sdk/python/pia_os_sdk/client.py",
        '        cabecalhos = {"Accept": "application/json"}\n        if authenticated:\n',
        '        cabecalhos = {"Accept": "application/json"}\n        if True:\n',
        ("tests/test_client.py",),
        "sdk/python",
    ),
    Mutante(
        "mS11",
        "inventar rota fora do OpenAPI autorizado",
        "sdk/python/pia_os_sdk/client.py",
        '_PATH_VERSION = "/api/v1/version"',
        '_PATH_VERSION = "/api/v1/version"\n_PATH_CAPACITY = "/api/v1/capacity-limits"',
        ("tests/static/test_e6_sdk_boundary.py",),
        "backend",
    ),
)

CARACTERIZACOES: tuple[Caracterizacao, ...] = (
    Caracterizacao(
        "cS1",
        "o backend não importa o SDK",
        "tests/static/test_e6_sdk_boundary.py::test_e63s04",
        "guarda de ausência de import em app/**; introduzir o import seria escrever "
        "código novo no backend, não mutar uma linha existente do SDK",
    ),
    Caracterizacao(
        "cS2",
        "o runtime do SDK não lê disco nem abre processo",
        "tests/static/test_e6_sdk_boundary.py::test_e63s10",
        "guarda de ausência de import",
    ),
)


def _rodar(raiz: Path, cwd: str, alvo: tuple[str, ...]) -> int:
    ambiente = dict(os.environ)
    diretorio = raiz / cwd
    caminhos = [str(diretorio)]
    if cwd == "backend":
        caminhos.append(str(raiz / "sdk" / "python"))
    ambiente["PYTHONPATH"] = ":".join(caminhos)
    ambiente.setdefault("ENVIRONMENT", "testing")
    resultado = subprocess.run(
        [str(PYTEST), "-o", "addopts=", "-q", "-p", "no:cacheprovider", *alvo],
        cwd=diretorio,
        env=ambiente,
        capture_output=True,
        text=True,
    )
    return resultado.returncode


def _copia(destino: Path) -> Path:
    raiz = destino / "repo"
    raiz.mkdir()
    shutil.copytree(BACKEND, raiz / "backend", ignore=_IGNORAR, symlinks=True)
    shutil.copytree(SDK, raiz / "sdk" / "python", ignore=_IGNORAR, symlinks=True)
    return raiz


def executar(selecionados: set[str] | None) -> int:
    falhas: list[str] = []
    mortos = 0
    print("=== MUTANTES REAIS DO SDK — baseline PASS -> mutante FAIL ===\n")
    for mutante in MUTANTES:
        if selecionados and mutante.ident not in selecionados:
            continue
        with tempfile.TemporaryDirectory(prefix=f"mut63-{mutante.ident}-") as temporario:
            raiz = _copia(Path(temporario))
            base = _rodar(raiz, mutante.cwd, mutante.alvo)

            arquivo = raiz / mutante.arquivo
            texto = arquivo.read_text(encoding="utf-8")
            if mutante.de not in texto:
                print(f"[{mutante.ident}] ERRO: alvo não encontrado em {mutante.arquivo}")
                falhas.append(f"{mutante.ident}: alvo ausente")
                continue
            arquivo.write_text(texto.replace(mutante.de, mutante.para, 1), encoding="utf-8")

            mutado = _rodar(raiz, mutante.cwd, mutante.alvo)

        veredito = "KILLED" if base == 0 and mutado != 0 else "SURVIVED"
        if veredito == "KILLED":
            mortos += 1
        else:
            falhas.append(f"{mutante.ident}: baseline={base} mutante={mutado}")
        print(f"[{mutante.ident}] {mutante.descricao}")
        print(f"        arquivo  : {mutante.arquivo}")
        print(f"        alvo     : {mutante.cwd} :: {' '.join(mutante.alvo)}")
        print(f"        baseline : exit {base}")
        print(f"        mutante  : exit {mutado}")
        print(f"        veredito : {veredito}\n")

    print("=== CARACTERIZAÇÕES — verificadas, NÃO contadas como morte ===\n")
    for caso in CARACTERIZACOES:
        print(f"[{caso.ident}] CHARACTERIZATION — {caso.descricao}")
        print(f"        teste  : {caso.alvo}")
        print(f"        motivo : {caso.motivo}\n")

    total = len([m for m in MUTANTES if not selecionados or m.ident in selecionados])
    print(f"KILLED           = {mortos}/{total}")
    print(f"CHARACTERIZATION = {len(CARACTERIZACOES)} (fora da contagem de mortes)")
    if falhas:
        print("\nFALHAS:")
        for falha in falhas:
            print(f"  - {falha}")
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mutation_evidence_e63")
    parser.add_argument("--only", action="append", default=None)
    args = parser.parse_args(argv)
    return executar(set(args.only) if args.only else None)


if __name__ == "__main__":  # pragma: no cover - entrypoint
    raise SystemExit(main())
