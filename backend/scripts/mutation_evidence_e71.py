"""
Arnês de mutação real da E7.1 — `baseline exit 0 -> mutante exit != 0`.

```text
TEXT_REPLACE_PLUS_STRING_ASSERT != MUTANT_DEATH
MUTANT_DEATH = TARGET_TEST_FAILS_ON_MUTATED_CODE
DEATH_BY_FOREIGN_GUARD != DEATH_BY_THE_NEW_GUARD
```

Regra herdada da E6.2/E6.3, com o reforço exigido pelo prompt ativo: cada
mutante é executado em **cópia isolada** da árvore, e o alvo é a guarda
**nova correspondente** — morte causada por guarda histórica alheia não
conta. Por isso cada mutante declara o teste específico que deve reprová-lo,
e não a suíte inteira.

Corretivo R1 (Chain111): os seis mutantes da Chain110 são **preservados**
sem alteração, e três novos medem as guardas que o corretivo criou —
binding na leitura de recibo, binding no escritor de tentativa e a
integridade Schedule<->Step no banco.

Corretivo R2 (Chain112): os nove anteriores seguem intactos, e M-s6 mede
o vínculo por Schedule DECLARADO no helper de escopo — o predicado cuja
ausência fazia `OWNER_BINDING` passar por `SCHEDULE_BINDING`.

Uso:

    python -m scripts.mutation_evidence_e71
    python -m scripts.mutation_evidence_e71 --only M7
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
"""Banco DEDICADO à mutação.

`M-a` muta a própria migration, e a prova de round trip reaplica o
`upgrade` a partir do fonte mutado. Rodar isso contra o banco da suíte
deixaria a trigger adulterada de pé para os testes seguintes — o mutante
contaminaria a medição em vez de ser medido. Cada execução recria o
schema do zero, para baseline e mutante em pé de igualdade.
"""

_IGNORAR = shutil.ignore_patterns(
    ".venv", "__pycache__", "htmlcov", ".pytest_cache", "*.pyc", ".coverage*"
)


@dataclasses.dataclass(frozen=True)
class Mutante:
    """Uma alteração mínima no fonte e a guarda nova que deve reprová-la."""

    ident: str
    descricao: str
    arquivo: str
    de: str
    para: str
    alvo: tuple[str, ...]


MUTANTES: tuple[Mutante, ...] = (
    Mutante(
        "M7",
        "incluir sealed_at no content hash",
        "app/orchestration/schemas/envelope.py",
        '            "constraints": constraints_as_mapping(self.constraints),\n        }',
        '            "constraints": constraints_as_mapping(self.constraints),\n'
        '            "sealed_at": __import__("datetime").datetime.now().isoformat(),\n        }',
        (
            "tests/unit/orchestration/test_envelope_content.py",
            "tests/static/test_e7_orchestration_boundary.py",
        ),
    ),
    Mutante(
        "M-a",
        "permitir mutação de seal_receipts (trigger de linha removida)",
        "alembic/versions/a7f31c05be24_create_orchestration_core_e7.py",
        "                CREATE TRIGGER {_ROW_TRIGGER}\n"
        "                BEFORE UPDATE OR DELETE ON {_RECEIPTS}",
        "                CREATE TRIGGER {_ROW_TRIGGER}\n"
        "                BEFORE INSERT ON {_RECEIPTS}",
        ("tests/integration/orchestration/test_orchestration_core.py",),
    ),
    Mutante(
        "M-b",
        "aceitar context_ref sem hash",
        "app/orchestration/schemas/envelope.py",
        "        if not isinstance(self.sha256, str) or not SHA256_PATTERN.match(self.sha256):",
        "        if False:",
        (
            "tests/unit/orchestration/test_envelope_content.py",
            "tests/integration/orchestration/test_orchestration_core.py",
        ),
    ),
    Mutante(
        "M-c",
        "usar content hash como chave de comando",
        "app/orchestration/services/command_receipt_service.py",
        "            command_key=command_key,\n"
        "            proposed_outcome_ref=proposed_outcome_ref,",
        "            command_key=proposed_outcome_ref,\n"
        "            proposed_outcome_ref=proposed_outcome_ref,",
        ("tests/integration/orchestration/test_orchestration_core.py",),
    ),
    Mutante(
        "M-s1",
        "remover control_principal_ref da consulta de Schedule",
        "app/orchestration/repositories/orchestration_repository.py",
        "        return self._session.scalars(\n"
        "            sa.select(Schedule).where(\n"
        "                Schedule.id == schedule_id,\n"
        "                Schedule.control_principal_ref == control_principal_ref,\n"
        "            )\n"
        "        ).one_or_none()",
        "        return self._session.scalars(\n"
        "            sa.select(Schedule).where(\n"
        "                Schedule.id == schedule_id,\n"
        "            )\n"
        "        ).one_or_none()",
        (
            "tests/integration/orchestration/test_orchestration_core.py",
            "tests/static/test_e7_orchestration_boundary.py",
        ),
    ),
    Mutante(
        "M-s2",
        "tornar command_key global (principal constante na reivindicação)",
        "app/orchestration/repositories/orchestration_repository.py",
        '                "technical_principal_ref": technical_principal_ref,',
        '                "technical_principal_ref": "global",',
        ("tests/integration/orchestration/test_orchestration_core.py",),
    ),
    Mutante(
        "M-s3",
        "remover o binding na leitura de recibo (get_seal_receipt_by_attempt)",
        # REAPONTADO NO R2: o corretivo acrescentou dois predicados a esta
        # cláusula, e o alvo original deixou de existir. Mutante com alvo
        # ausente é pior que mutante ausente — aparece na lista e parece
        # medido (lição da E6.3, mS2). A INTENÇÃO é preservada: continua
        # removendo o vínculo de dono da leitura de recibo.
        "app/orchestration/repositories/orchestration_repository.py",
        "            .where(\n"
        "                SealReceipt.attempt_id == attempt_id,\n"
        "                HandoffAttempt.schedule_id == schedule_id,\n"
        "                Schedule.id == schedule_id,\n"
        "                Schedule.control_principal_ref == control_principal_ref,\n"
        "            )",
        "            .where(\n"
        "                SealReceipt.attempt_id == attempt_id,\n"
        "                HandoffAttempt.schedule_id == schedule_id,\n"
        "                Schedule.id == schedule_id,\n"
        "            )",
        (
            "tests/integration/orchestration/test_orchestration_core.py",
            "tests/static/test_e7_orchestration_boundary.py",
        ),
    ),
    Mutante(
        "M-s4",
        "remover o binding no escritor de tentativa (create_attempt)",
        "app/orchestration/repositories/orchestration_repository.py",
        "        if (\n"
        "            self.get_step(\n"
        "                control_principal_ref=control_principal_ref,\n"
        "                schedule_id=schedule_id,\n"
        "                step_id=step_id,\n"
        "            )\n"
        "            is None\n"
        "        ):\n"
        "            raise OrchestrationScopeViolationError(\n"
        '                message="etapa inexistente neste Schedule sob este principal",\n'
        '                detail={"schedule_id": str(schedule_id), "step_id": str(step_id)},\n'
        "            )\n"
        "        tentativa = HandoffAttempt(",
        "        tentativa = HandoffAttempt(",
        (
            "tests/integration/orchestration/test_orchestration_core.py",
            "tests/static/test_e7_orchestration_boundary.py",
        ),
    ),
    Mutante(
        "M-s6",
        "remover HandoffAttempt.schedule_id == schedule_id do helper de escopo",
        "app/orchestration/repositories/orchestration_repository.py",
        "                HandoffAttempt.id == attempt_id,\n"
        "                HandoffAttempt.schedule_id == schedule_id,\n"
        "                Schedule.id == schedule_id,\n"
        "                Schedule.control_principal_ref == control_principal_ref,\n"
        "            )\n"
        "        ).one_or_none()\n"
        "\n"
        "    def get_attempt(",
        "                HandoffAttempt.id == attempt_id,\n"
        "                Schedule.control_principal_ref == control_principal_ref,\n"
        "            )\n"
        "        ).one_or_none()\n"
        "\n"
        "    def get_attempt(",
        (
            "tests/integration/orchestration/test_orchestration_core.py",
            "tests/static/test_e7_orchestration_boundary.py",
        ),
    ),
    Mutante(
        "M-s5",
        "remover a integridade Schedule<->Step do banco (FK composta)",
        "alembic/versions/b8c04e2fd137_enforce_schedule_step_integrity_e7_1_r1.py",
        "    op.create_foreign_key(\n"
        "        _FK_COMPOSTA,\n"
        "        _ATTEMPTS,\n"
        "        _STEPS,\n"
        '        ["step_id", "schedule_id"],\n'
        '        ["id", "schedule_id"],\n'
        "    )",
        "    pass",
        ("tests/integration/orchestration/test_orchestration_core.py",),
    ),
)


def _ambiente(raiz: Path) -> dict[str, str]:
    ambiente = dict(os.environ)
    ambiente["PYTHONPATH"] = str(raiz)
    ambiente["ENVIRONMENT"] = "testing"
    ambiente["DATABASE_URL"] = MUTATION_DATABASE_URL
    return ambiente


def _preparar_banco(raiz: Path) -> None:
    """Schema limpo + `alembic upgrade head` a partir do fonte desta cópia."""
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


def _copia(destino: Path) -> Path:
    raiz = destino / "backend"
    shutil.copytree(BACKEND, raiz, ignore=_IGNORAR, symlinks=True)
    return raiz


def executar(selecionados: set[str] | None) -> int:
    falhas: list[str] = []
    mortos = 0
    print("=== MUTANTES REAIS E7.1 — baseline exit 0 -> mutante exit != 0 ===\n")
    for mutante in MUTANTES:
        if selecionados and mutante.ident not in selecionados:
            continue
        with tempfile.TemporaryDirectory(prefix=f"mut-{mutante.ident}-") as temporario:
            raiz = _copia(Path(temporario))
            base = _rodar(raiz, mutante.alvo)

            arquivo = raiz / mutante.arquivo
            texto = arquivo.read_text(encoding="utf-8")
            if mutante.de not in texto:
                print(f"[{mutante.ident}] ERRO: alvo da mutação ausente em {mutante.arquivo}")
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

    total = len([m for m in MUTANTES if not selecionados or m.ident in selecionados])
    print(f"KILLED = {mortos}/{total}")
    if falhas:
        print("\nFALHAS:")
        for falha in falhas:
            print(f"  - {falha}")
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mutation_evidence_e71")
    parser.add_argument("--only", action="append", default=None)
    args = parser.parse_args(argv)
    return executar(set(args.only) if args.only else None)


if __name__ == "__main__":  # pragma: no cover - entrypoint
    raise SystemExit(main())
