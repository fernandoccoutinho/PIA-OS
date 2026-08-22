"""
Arnês de mutação real da E6.2 — `baseline PASS -> mutante FAIL`.

```text
TEXT_REPLACE_PLUS_STRING_ASSERT != MUTANT_DEATH
MUTANT_DEATH = TARGET_TEST_FAILS_ON_MUTATED_CODE
```

O relatório da candidata rejeitada declarou `12/12 KILLED` contando testes
que apenas alteravam uma string em memória e conferiam que o texto mudou.
Isso não executa o código mutado e não demonstra guarda alguma. Este
script corrige a medição: para cada mutante **aplicável**, copia a árvore
para um diretório isolado, aplica a alteração no FONTE, roda o teste-alvo
com o mesmo interpretador e registra os dois códigos de saída.

Um caso que só pode ser verificado por ausência de símbolo — "este arquivo
não constrói autoridade PIAP" — não é mutante: não existe alteração
mínima que o código real pudesse sofrer e o teste flagrar em runtime.
Esses casos são rotulados `CHARACTERIZATION` e **não** entram na contagem
de mortes. Contagem honesta vale mais que contagem alta.

Uso:

    python -m scripts.mutation_evidence_e62            # todos
    python -m scripts.mutation_evidence_e62 --only m01
"""

import argparse
import dataclasses
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
PYTEST = BACKEND / ".venv" / "bin" / "pytest"

# Diretórios que não fazem sentido copiar para cada mutante.
_IGNORAR = shutil.ignore_patterns(
    ".venv", "__pycache__", "htmlcov", ".pytest_cache", "*.pyc", ".coverage*"
)


@dataclasses.dataclass(frozen=True)
class Mutante:
    """Uma alteração mínima no fonte e o teste que deve reprová-la."""

    ident: str
    descricao: str
    arquivo: str
    de: str
    para: str
    alvo: tuple[str, ...]


@dataclasses.dataclass(frozen=True)
class Caracterizacao:
    """Guarda de ausência: verificável, mas não é morte de mutante."""

    ident: str
    descricao: str
    alvo: str
    motivo: str


MUTANTES: tuple[Mutante, ...] = (
    Mutante(
        "m01",
        "aceitar digest desigual (comparação sempre verdadeira)",
        "app/security/programmatic_access.py",
        "    if not hmac.compare_digest(esperado, linha.secret_digest):",
        "    if False:",
        ("tests/unit/security/test_programmatic_access.py",),
    ),
    Mutante(
        "m02",
        "ignorar revogação e expiração",
        "app/security/programmatic_access.py",
        "    if not linha.is_active_at(agora):",
        "    if False:",
        ("tests/unit/security/test_programmatic_access.py",),
    ),
    Mutante(
        "m05",
        "omitir o roteamento governado da E5",
        "app/services/predictive_evaluation_service.py",
        "    roteamento = predictive_route_batch(coordenado, governadas, at=momento)",
        "    roteamento = coordenado.evaluation",
        ("tests/unit/services/test_predictive_evaluation_service.py",),
    ),
    Mutante(
        "m06",
        "aceitar `at` divergente entre itens ready",
        "app/services/predictive_evaluation_service.py",
        "        raise ValidationException(detail=MIXED_AT_DETAIL)",
        "        return sorted(instantes)[0]",
        ("tests/unit/services/test_predictive_evaluation_service.py",),
    ),
    Mutante(
        "m08",
        "retirar a dependency de acesso da rota de negócio",
        "app/routers/predictive_evaluations.py",
        "    principal: GuardedPrincipal,\n",
        "",
        (
            "tests/static/test_e6_programmatic_endpoint.py",
            "tests/integration/api/test_predictive_evaluations.py",
        ),
    ),
    Mutante(
        "m09",
        "substituir a dependency canônica por uma homônima local no-op",
        "app/routers/predictive_evaluations.py",
        "from app.api.dependencies import require_predictive_evaluate_access",
        (
            "from app.security.programmatic_access import ProgrammaticPrincipal as _P\n\n\n"
            "def require_predictive_evaluate_access() -> None:\n    return None"
        ),
        ("tests/integration/api/test_predictive_evaluations.py",),
    ),
    Mutante(
        "m10",
        "usar chave global em vez do principal na cota",
        "app/api/dependencies.py",
        "            principal_id=principal.id,",
        '            principal_id=__import__("uuid").UUID(int=0),',
        ("tests/integration/api/test_predictive_evaluations.py",),
    ),
    Mutante(
        "m11",
        "remover a condição atômica `used < limit` do upsert",
        "app/repositories/programmatic_access_repository.py",
        "            WHERE programmatic_quota_buckets.used < :quota_limit\n",
        "",
        (
            "tests/integration/api/test_predictive_evaluations.py",
            "tests/integration/security/test_programmatic_access_integration.py",
        ),
    ),
    Mutante(
        "m13",
        "não canonicalizar escopos no escritor central",
        "app/repositories/programmatic_access_repository.py",
        "        canonicos = canonical_scopes(scopes)",
        "        canonicos = tuple(scopes)",
        ("tests/integration/security/test_programmatic_access_integration.py",),
    ),
    Mutante(
        "m14",
        "publicar falha da autoridade de cota como cota excedida",
        "app/api/dependencies.py",
        "        raise DatabaseUnavailableException(detail=QUOTA_AUTHORITY_UNAVAILABLE_DETAIL)"
        " from exc",
        "        raise TooManyRequestsException(detail=QUOTA_EXCEEDED_DETAIL) from exc",
        ("tests/integration/api/test_predictive_evaluations.py",),
    ),
    Mutante(
        "m15",
        "deixar o framework gerar o erro automático do Bearer",
        "app/api/dependencies.py",
        "    auto_error=False,",
        "    auto_error=True,",
        ("tests/integration/api/test_predictive_evaluations.py",),
    ),
)

CARACTERIZACOES: tuple[Caracterizacao, ...] = (
    Caracterizacao(
        "m03",
        "o verificador não importa nem constrói envelope/autoridade PIAP",
        "tests/unit/security/test_programmatic_access.py::test_e62m03...",
        "guarda de ausência de símbolo — nenhuma alteração mínima do código real "
        "seria flagrada em runtime por um teste de comportamento",
    ),
    Caracterizacao(
        "m04",
        "o serviço não constrói instrução de reconfiguração",
        "tests/unit/services/test_predictive_evaluation_service.py::test_e62m04...",
        "instruções são sempre None; introduzir uma exigiria escrever código novo, "
        "não mutar uma linha existente",
    ),
    Caracterizacao(
        "m07",
        "o serviço não monta desfecho científico à mão",
        "tests/unit/services/test_predictive_evaluation_service.py::test_e62m07...",
        "guarda de ausência de construtor",
    ),
    Caracterizacao(
        "m12",
        "nenhum arquivo do delta cria autoridade ou aprovação PIAP",
        "tests/static/test_e6_programmatic_endpoint.py::test_e62m12...",
        "guarda de ausência de símbolo em cinco arquivos",
    ),
)


def _rodar(raiz: Path, alvo: tuple[str, ...]) -> int:
    ambiente = dict(os.environ)
    ambiente["PYTHONPATH"] = str(raiz)
    ambiente.setdefault("ENVIRONMENT", "testing")
    resultado = subprocess.run(
        [str(PYTEST), "-o", "addopts=", "-q", "-p", "no:cacheprovider", *alvo],
        cwd=raiz,
        env=ambiente,
        capture_output=True,
        text=True,
    )
    return resultado.returncode


def _copia(destino: Path) -> Path:
    raiz = destino / "backend"
    shutil.copytree(BACKEND, raiz, ignore=_IGNORAR, symlinks=True)
    return raiz


def executar(selecionados: set[str] | None) -> int:
    falhas: list[str] = []
    mortos = 0
    print("=== MUTANTES REAIS — baseline PASS -> mutante FAIL ===\n")
    for mutante in MUTANTES:
        if selecionados and mutante.ident not in selecionados:
            continue
        with tempfile.TemporaryDirectory(prefix=f"mut-{mutante.ident}-") as temporario:
            raiz = _copia(Path(temporario))
            base = _rodar(raiz, mutante.alvo)

            arquivo = raiz / mutante.arquivo
            texto = arquivo.read_text(encoding="utf-8")
            if mutante.de not in texto:
                print(
                    f"[{mutante.ident}] ERRO: alvo da mutação não encontrado "
                    f"em {mutante.arquivo}"
                )
                falhas.append(f"{mutante.ident}: alvo ausente")
                continue
            arquivo.write_text(texto.replace(mutante.de, mutante.para, 1), encoding="utf-8")

            mutado = _rodar(raiz, mutante.alvo)

        veredito = "KILLED" if base == 0 and mutado != 0 else "SURVIVED"
        if veredito == "KILLED":
            mortos += 1
        else:
            falhas.append(f"{mutante.ident}: baseline={base} mutante={mutado}")
        print(f"[{mutante.ident}] {mutante.descricao}")
        print(f"        arquivo  : {mutante.arquivo}")
        print(f"        alvo     : {' '.join(mutante.alvo)}")
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
    parser = argparse.ArgumentParser(prog="mutation_evidence_e62")
    parser.add_argument("--only", action="append", default=None)
    args = parser.parse_args(argv)
    return executar(set(args.only) if args.only else None)


if __name__ == "__main__":  # pragma: no cover - entrypoint
    raise SystemExit(main())
