"""
Prova NEGATIVA da guarda histórica `ii17` — refinamento não é afrouxamento.

```text
GUARD_REFINED_BY_IDENTITY != GUARD_WEAKENED
E4_8_WORKSPACE_SCHEDULE != E7_ORCHESTRATION_SCHEDULE
```

A E4.8 proibia uma tabela chamada `schedules` como proxy de "a memória
isolada materializou um espaço de trabalho persistente". A Chain110 criou
uma tabela `schedules` que é outra coisa — o trabalho governado da
orquestração multi-IA, autorizado pelo `MAI-001 R1`. O `ii17` deixou de
medir o NOME e passou a medir a IDENTIDADE da tabela.

Trocar o critério de uma guarda histórica é onde uma guarda morre em
silêncio. Este arnês existe para que a troca seja falsificável: ele
altera o SCHEMA (não o teste) de duas formas que a guarda antiga
reprovaria, e exige que a guarda nova continue reprovando.

```text
baseline autorizado (schedules com control_principal_ref)  -> exit 0
mutante A: schedules SEM control_principal_ref             -> exit != 0
mutante B: schedules COM coluna de isolamento de memória   -> exit != 0
```

Esta prova **não** integra os seis mutantes obrigatórios da E7.1 e não
entra naquela contagem: ela não mede uma guarda nova desta entrega, mede
que uma guarda antiga sobreviveu ao refinamento.

Uso:

    python -m scripts.ii17_guard_proof
"""

import dataclasses
import os
import subprocess
import sys

import psycopg

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ALVO = (
    "tests/integration/memory/test_memory_isolation_integration.py"
    "::test_ii17_no_new_table_was_introduced"
)

DATABASE_URL = os.environ.get(
    "PIA_II17_DATABASE_URL",
    "postgresql+psycopg://piaos:piaos@localhost:5432/pia_os_ii17",
)


@dataclasses.dataclass(frozen=True)
class Cenario:
    """Uma alteração mínima do SCHEMA e o veredito esperado da guarda."""

    ident: str
    descricao: str
    ddl: tuple[str, ...]
    espera_falha: bool


CENARIOS: tuple[Cenario, ...] = (
    Cenario(
        "baseline",
        "schedules da E7, com control_principal_ref e sem coluna de isolamento",
        (),
        False,
    ),
    Cenario(
        "ii17-A",
        "schedules SEM control_principal_ref — deixa de ser a tabela da E7",
        ("ALTER TABLE schedules DROP COLUMN control_principal_ref CASCADE",),
        True,
    ),
    Cenario(
        "ii17-B",
        "schedules COM coluna de isolamento de memória — vira o espaço de trabalho proibido",
        ("ALTER TABLE schedules ADD COLUMN memory_domain_id uuid",),
        True,
    ),
)


def _ambiente() -> dict[str, str]:
    ambiente = dict(os.environ)
    ambiente["PYTHONPATH"] = BACKEND
    ambiente["ENVIRONMENT"] = "testing"
    ambiente["DATABASE_URL"] = DATABASE_URL
    return ambiente


def _preparar_banco() -> None:
    url = DATABASE_URL.replace("postgresql+psycopg://", "postgresql://")
    with psycopg.connect(url, autocommit=True) as conexao:
        conexao.execute("DROP SCHEMA public CASCADE")
        conexao.execute("CREATE SCHEMA public")
    subprocess.run(
        ["python", "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND,
        env=_ambiente(),
        capture_output=True,
        text=True,
        check=True,
    )


def _aplicar(ddl: tuple[str, ...]) -> None:
    if not ddl:
        return
    url = DATABASE_URL.replace("postgresql+psycopg://", "postgresql://")
    with psycopg.connect(url, autocommit=True) as conexao:
        for instrucao in ddl:
            conexao.execute(instrucao)


def _rodar() -> int:
    resultado = subprocess.run(
        ["python", "-m", "pytest", "-o", "addopts=", "-q", "-p", "no:cacheprovider", ALVO],
        cwd=BACKEND,
        env=_ambiente(),
        capture_output=True,
        text=True,
    )
    return resultado.returncode


def executar() -> int:
    print("=== PROVA NEGATIVA ii17 — refinamento por identidade não afrouxa ===\n")
    print(f"alvo: {ALVO}\n")
    falhas: list[str] = []
    for cenario in CENARIOS:
        _preparar_banco()
        _aplicar(cenario.ddl)
        saida = _rodar()
        esperado = "exit != 0" if cenario.espera_falha else "exit 0"
        correto = (saida != 0) if cenario.espera_falha else (saida == 0)
        veredito = "OK" if correto else "GUARDA PERMISSIVA"
        if not correto:
            falhas.append(f"{cenario.ident}: esperado {esperado}, obtido exit {saida}")
        print(f"[{cenario.ident}] {cenario.descricao}")
        print(f"        ddl      : {'; '.join(cenario.ddl) or '(nenhuma)'}")
        print(f"        esperado : {esperado}")
        print(f"        obtido   : exit {saida}")
        print(f"        veredito : {veredito}\n")

    _preparar_banco()
    if falhas:
        print("FALHAS:")
        for falha in falhas:
            print(f"  - {falha}")
        return 1
    print("GUARDA_HISTORICA_ii17 = PRESERVED (2/2 cenários adversos reprovados)")
    print("NOTA: fora da contagem dos seis mutantes obrigatórios da E7.1.")
    return 0


if __name__ == "__main__":  # pragma: no cover - entrypoint
    sys.exit(executar())
