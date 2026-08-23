"""
Arnês de mutação da E7.2 — `baseline exit 0 -> mutante exit != 0`.

```text
TEXT_REPLACE_PLUS_STRING_ASSERT != MUTANT_DEATH
MUTANT_DEATH = TARGET_TEST_FAILS_ON_MUTATED_CODE
MISSING_TARGET != KILLED
```

Cada mutante roda em **cópia isolada** da árvore e em **banco dedicado**,
com o schema recriado antes do baseline e antes do mutante. Sem isso, um
mutante que altera a migration deixaria o banco adulterado para o
seguinte e contaminaria a medição em vez de ser medido.

O alvo de cada mutante é a guarda **nova correspondente**, não a suíte
inteira: morte causada por guarda histórica alheia não prova que a guarda
desta entrega funciona.

Uso:

    python -m scripts.mutation_evidence_e72
    python -m scripts.mutation_evidence_e72 --only M2
"""

import argparse
import dataclasses
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]

MUTATION_DATABASE_URL = os.environ.get(
    "PIA_MUTATION_DATABASE_URL",
    "postgresql+psycopg://piaos:piaos@localhost:5432/pia_os_mutation",
)

_IGNORAR = shutil.ignore_patterns(
    ".venv", "__pycache__", "htmlcov", ".pytest_cache", "*.pyc", ".coverage*"
)

_API = "tests/integration/api/test_orchestration_api.py"
_PERSISTENCIA = "tests/integration/orchestration/test_orchestration_return_persistence.py"
_ESTATICO = "tests/static/test_e72_orchestration_boundary.py"
_UNITARIO = "tests/unit/orchestration/test_return_validation.py"


@dataclasses.dataclass(frozen=True)
class Mutante:
    ident: str
    descricao: str
    arquivo: str
    de: str
    para: str
    alvo: tuple[str, ...]


MUTANTES: tuple[Mutante, ...] = (
    Mutante(
        "M2",
        "aceitar o retorno sem validar o contrato",
        "app/orchestration/services/return_validation_service.py",
        "        medido = validate_output(\n"
        "            expected_output_contract=etapa.expected_output_contract,\n"
        "            media_type=raw.media_type,\n"
        "            content=raw.content,\n"
        "        )",
        "        import hashlib as _h\n"
        "        from app.orchestration.schemas.output_contract import ValidatedOutput\n"
        "        medido = ValidatedOutput(\n"
        "            accepted=True,\n"
        "            media_type=raw.media_type,\n"
        "            output_sha256=_h.sha256(raw.content.encode()).hexdigest(),\n"
        "            output_bytes=len(raw.content.encode()),\n"
        "            validation_codes=(),\n"
        "        )",
        (_API, _PERSISTENCIA),
    ),
    Mutante(
        "M8",
        "descartar o resultado rejeitado em vez de persistí-lo",
        "app/orchestration/services/return_validation_service.py",
        "        resultado = self._repository.create_handoff_result(\n"
        "            control_principal_ref=control_principal_ref,",
        "        if not medido.accepted:\n"
        "            raise OrchestrationContractViolationError(\n"
        '                message="retorno invalido descartado"\n'
        "            )\n"
        "        resultado = self._repository.create_handoff_result(\n"
        "            control_principal_ref=control_principal_ref,",
        (_API, _PERSISTENCIA),
    ),
    Mutante(
        "M5",
        "reaproveitar a tentativa anterior no retry em vez de abrir uma nova",
        "app/orchestration/services/command_receipt_service.py",
        "        attempt_id = uuid.uuid4()\n" "        resultado: dict[str, ExportOutcome] = {}",
        "        attempt_id = uuid.UUID(int=7)\n"
        "        resultado: dict[str, ExportOutcome] = {}",
        (_API,),
    ),
    Mutante(
        "M-d",
        "aceitar o escopo preditivo nas rotas da E7",
        "app/api/dependencies.py",
        "    require_scope(principal, SCOPE_ORCHESTRATION_OPERATE)\n"
        "    repositorio = ProgrammaticAccessRepository(session)\n"
        "    try:\n"
        "        liberado = repositorio.consume_quota(\n"
        "            principal_id=principal.id,\n"
        "            operation=OPERATION_ORCHESTRATION_API,",
        "    require_scope(principal, SCOPE_PREDICTIVE_EVALUATE)\n"
        "    repositorio = ProgrammaticAccessRepository(session)\n"
        "    try:\n"
        "        liberado = repositorio.consume_quota(\n"
        "            principal_id=principal.id,\n"
        "            operation=OPERATION_PREDICTIVE_EVALUATE,",
        (_API, _ESTATICO),
    ),
    Mutante(
        "M10",
        "escrever proveniência a partir da atribuição da E7",
        "app/orchestration/repositories/orchestration_repository.py",
        "        atribuicao = HandoffAttribution(\n"
        "            attempt_id=attempt_id,\n"
        "            role=role,",
        "        atribuicao = HandoffAttribution(\n"
        "            provenance_record_ref=uuid.uuid4(),\n"
        "            attempt_id=attempt_id,\n"
        "            role=role,",
        (_API, _ESTATICO, _PERSISTENCIA),
    ),
)


def _ambiente(raiz: Path) -> dict[str, str]:
    ambiente = dict(os.environ)
    ambiente["PYTHONPATH"] = str(raiz)
    ambiente["ENVIRONMENT"] = "testing"
    ambiente["DATABASE_URL"] = MUTATION_DATABASE_URL
    return ambiente


def _preparar_banco(raiz: Path) -> None:
    import psycopg

    url = MUTATION_DATABASE_URL.replace("postgresql+psycopg://", "postgresql://")
    with psycopg.connect(url, autocommit=True) as conexao:
        conexao.execute("DROP SCHEMA public CASCADE")
        conexao.execute("CREATE SCHEMA public")
    subprocess.run(
        ["python", "-m", "alembic", "upgrade", "head"],
        cwd=raiz,
        env=_ambiente(raiz),
        capture_output=True,
        text=True,
        check=False,
    )


def _rodar(raiz: Path, alvo: tuple[str, ...]) -> int:
    _preparar_banco(raiz)
    resultado = subprocess.run(
        ["python", "-m", "pytest", "-o", "addopts=", "-q", "-p", "no:cacheprovider", *alvo],
        cwd=raiz,
        env=_ambiente(raiz),
        capture_output=True,
        text=True,
    )
    return resultado.returncode


def executar(selecionados: set[str] | None) -> int:
    falhas: list[str] = []
    mortos = 0
    print("=== MUTANTES REAIS E7.2 — baseline exit 0 -> mutante exit != 0 ===\n")
    for mutante in MUTANTES:
        if selecionados and mutante.ident not in selecionados:
            continue
        with tempfile.TemporaryDirectory(prefix=f"mut72-{mutante.ident}-") as temporario:
            raiz = Path(temporario) / "backend"
            shutil.copytree(BACKEND, raiz, ignore=_IGNORAR, symlinks=True)
            base = _rodar(raiz, mutante.alvo)
            arquivo = raiz / mutante.arquivo
            texto = arquivo.read_text(encoding="utf-8")
            ocorrencias = texto.count(mutante.de)
            if ocorrencias != 1:
                print(
                    f"[{mutante.ident}] ERRO: alvo ocorre {ocorrencias}x em {mutante.arquivo} "
                    "(exigido: exatamente 1)"
                )
                falhas.append(f"{mutante.ident}: alvo ausente ou ambíguo")
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

    total = len([m for m in MUTANTES if not selecionados or m.ident in selecionados])
    print(f"KILLED = {mortos}/{total}")
    if falhas:
        print("\nFALHAS:")
        for falha in falhas:
            print(f"  - {falha}")
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mutation_evidence_e72")
    parser.add_argument("--only", action="append", default=None)
    args = parser.parse_args(argv)
    return executar(set(args.only) if args.only else None)


if __name__ == "__main__":  # pragma: no cover - entrypoint
    raise SystemExit(main())
