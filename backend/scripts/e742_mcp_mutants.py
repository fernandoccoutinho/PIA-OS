#!/usr/bin/env python3
"""Dez mutantes materiais do runtime MCP E7.4-2.

Cada alvo altera produção, exige baseline verde e aborta quando o alvo não
é único. Os testes PostgreSQL usam o banco de mutação dedicado configurado
por ``MUTANT_DATABASE_URL``/``PIA_MUTATION_DATABASE_URL``.

O arnês é AUTOSSUFICIENTE quanto ao schema do banco de mutação: ele o
reconstrói e o migra antes de medir. Depender de outro arnês ter migrado
antes torna o veredito posicional — verde quando o banco vem sujo de uma
rodada anterior, vermelho em banco limpo::

    PRECONDITION_PRODUCED_BY_ANOTHER_HARNESS = ORDER_DEPENDENT_VERDICT
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
MIGRATION_LEAF = "f4c8b0d51e73"
UNIT = "tests/unit/mcp/test_mcp_boundary_functional.py"
CLIENT = "tests/integration/mcp/test_mcp_client_real.py"
STATIC = "tests/static/test_mcp_boundary.py"
PG = "tests/integration/mcp/test_mcp_productive_composition_pg.py"


@dataclass(frozen=True)
class Replacement:
    old: str
    new: str


@dataclass(frozen=True)
class Mutant:
    name: str
    path: str
    replacements: tuple[Replacement, ...]
    tests: tuple[str, ...]


MUTANTS = (
    Mutant(
        "M-AUDIENCE-NOT-VALIDATED",
        "app/mcp/auth.py",
        (
            Replacement(
                "                audience=self._config.audience,", "                audience=None,"
            ),
            Replacement(
                '                    "verify_exp": False,',
                '                    "verify_aud": False,\n'
                '                    "verify_exp": False,',
            ),
            Replacement(
                "        if self._config.audience not in audiencias:",
                "        if False:",
            ),
        ),
        (UNIT,),
    ),
    Mutant(
        "M-ISSUER-NOT-VALIDATED",
        "app/mcp/auth.py",
        (
            Replacement(
                "                issuer=self._config.issuer,", "                issuer=None,"
            ),
            Replacement(
                '                    "verify_exp": False,',
                '                    "verify_iss": False,\n'
                '                    "verify_exp": False,',
            ),
            Replacement(
                '        if reivindicacoes.get("iss") != self._config.issuer:',
                "        if False:",
            ),
        ),
        (UNIT,),
    ),
    Mutant(
        "M-PRINCIPAL-FROM-SUBJECT",
        "app/mcp/tools.py",
        (Replacement("        ref = principal.principal_ref", "        ref = principal.subject"),),
        (UNIT,),
    ),
    Mutant(
        "M-SCOPE-IGNORED",
        "app/mcp/token_verifier.py",
        (Replacement("        required_scopes=[escopo],", "        required_scopes=[],"),),
        (CLIENT,),
    ),
    Mutant(
        "M-GENERIC-TOOL",
        "app/mcp/tools.py",
        (Replacement("        if nome not in TOOL_NAMES:", "        if False:"),),
        (UNIT,),
    ),
    Mutant(
        "M-REPOSITORY-BYPASS",
        "app/mcp/tools.py",
        (
            Replacement(
                "from app.mcp import TOOL_NAMES",
                "from app.mcp import TOOL_NAMES\n"
                "from app.orchestration.repositories.orchestration_repository "
                "import OrchestrationRepository",
            ),
        ),
        (STATIC,),
    ),
    Mutant(
        "M-MCP-AS-MANUAL",
        "app/mcp/supervised_export_service.py",
        (
            Replacement(
                "            handoff_mode=HandoffMode.SUPERVISED_AUTOMATIC_HANDOFF,",
                "            handoff_mode=HandoffMode.MANUAL_HANDOFF,",
            ),
        ),
        (UNIT,),
    ),
    Mutant(
        "M-G3-AFTER-SEAL",
        "app/mcp/supervised_export_service.py",
        (
            Replacement(
                """        # G3 ANTES do selo. Depois dele existiria Attempt de um despacho
        # que a proteção recusou.
        decisao = self._protecao.aplicar(
            objective=self._objetivo(schedule_id=schedule_id, step_id=step_id),
            gate_position=GatePosition.G3,
            principal_ref=control_principal_ref,
            operation=self._operacao,
            schedule_id=schedule_id,
            step_id=step_id,
            attempt_id=attempt_id,
        )
        if decisao.outcome is not ProtectionOutcome.ALLOWED:
            raise HandoffBlockedError(
                gate_position=GatePosition.G3,
                fingerprint=decisao.decision_fingerprint,
            )

        selado = self._handoff_service.seal_step_for_export(
            attempt_id=attempt_id,
            control_principal_ref=control_principal_ref,
            schedule_id=schedule_id,
            step_id=step_id,
            sealer_ref=sealer_ref,
        )""",
                """        selado = self._handoff_service.seal_step_for_export(
            attempt_id=attempt_id,
            control_principal_ref=control_principal_ref,
            schedule_id=schedule_id,
            step_id=step_id,
            sealer_ref=sealer_ref,
        )

        decisao = self._protecao.aplicar(
            objective=self._objetivo(schedule_id=schedule_id, step_id=step_id),
            gate_position=GatePosition.G3,
            principal_ref=control_principal_ref,
            operation=self._operacao,
            schedule_id=schedule_id,
            step_id=step_id,
            attempt_id=attempt_id,
        )
        if decisao.outcome is not ProtectionOutcome.ALLOWED:
            raise HandoffBlockedError(
                gate_position=GatePosition.G3,
                fingerprint=decisao.decision_fingerprint,
            )""",
            ),
        ),
        (UNIT,),
    ),
    Mutant(
        "M-IDEMPOTENCY-WITHOUT-REQUEST",
        "app/orchestration/services/command_receipt_service.py",
        (
            Replacement(
                """            request_sha256=_impressao_digital(
                {
                    "operation": CommandOperation.EXPORT_HANDOFF.value,
                    "schedule_id": str(schedule_id),
                    "step_id": str(step_id),
                    "sealer_ref": sealer_ref,
                }
            ),""",
                '            request_sha256="0" * 64,',
            ),
        ),
        (PG,),
    ),
    Mutant(
        "M-TEST-AS-IN-PRODUCTION",
        "app/services/mcp_composition_root.py",
        (
            Replacement(
                "from app.mcp import TOOL_NAMES",
                "from app.mcp import TOOL_NAMES\n"
                "from tests.unit.mcp.test_mcp_boundary_functional import as_efemero",
            ),
        ),
        (STATIC,),
    ),
)


def _url_de_mutacao() -> str | None:
    return os.environ.get("MUTANT_DATABASE_URL") or os.environ.get("PIA_MUTATION_DATABASE_URL")


@dataclass(frozen=True)
class IdentidadeDeBanco:
    """Identidade REAL devolvida pelo servidor, não a que a URL declara.

    ```text
    URL_TEXT != DATABASE_IDENTITY
    ```

    Duas URLs textualmente diferentes podem abrir o MESMO banco: basta
    trocar ``localhost`` por ``127.0.0.1``, acrescentar parâmetro de
    conexão ou variar credencial. Comparar texto não protege nada.
    """

    database: str
    endereco: str | None
    porta: int | None

    @property
    def indistinguivel(self) -> bool:
        """Falta componente para decidir se dois bancos são o mesmo.

        Conexão por socket unix devolve ``inet_server_addr()`` e
        ``inet_server_port()`` nulos. Nesse caso o nome do banco sozinho não
        distingue servidores, e a recusa é a saída conservadora:

        ```text
        UNKNOWN_IDENTITY = NOT_A_DISTINCT_IDENTITY
        ```
        """
        return self.endereco is None or self.porta is None

    def __str__(self) -> str:
        return f"{self.database}@{self.endereco or 'DESCONHECIDO'}:{self.porta or 'DESCONHECIDA'}"


def _identidade(url: str) -> IdentidadeDeBanco | str:
    """Devolve a identidade real da conexão, ou a razão da recusa."""
    from sqlalchemy import create_engine, text
    from sqlalchemy.exc import SQLAlchemyError

    motor = create_engine(url)
    try:
        with motor.connect() as conexao:
            linha = conexao.execute(
                text("select current_database(), host(inet_server_addr()), inet_server_port()")
            ).one()
    except SQLAlchemyError as erro:
        return f"CONNECTION_FAILED {type(erro).__name__}"
    finally:
        motor.dispose()

    endereco = None if linha[1] is None else str(linha[1])
    porta = None if linha[2] is None else int(linha[2])
    return IdentidadeDeBanco(database=str(linha[0]), endereco=endereco, porta=porta)


def preparar_banco_de_mutacao() -> str | None:
    """Reconstrói e migra o banco de mutação. Devolve o motivo da recusa, ou None.

    Toda a verificação de identidade acontece ANTES de qualquer
    ``DROP SCHEMA``: o arnês conecta-se aos DOIS bancos, pergunta ao
    PostgreSQL quem ele é em cada conexão e só destrói o schema quando as
    identidades são distintas e ambas conhecidas.
    """
    from sqlalchemy import create_engine, text

    url = _url_de_mutacao()
    if not url:
        return "MUTATION_DB=NOT_CONFIGURED"
    url_teste = os.environ.get("DATABASE_URL")
    if not url_teste:
        return "MUTATION_DB=TEST_DATABASE_NOT_CONFIGURED"
    if url == url_teste:
        return "MUTATION_DB=SAME_AS_TEST_DATABASE"

    declarado = urlsplit(url).path.lstrip("/")
    if not declarado:
        return "MUTATION_DB=NO_DATABASE_IN_URL"

    identidade_teste = _identidade(url_teste)
    if isinstance(identidade_teste, str):
        return f"MUTATION_DB=TEST_DATABASE_UNREACHABLE {identidade_teste}"
    identidade_mutacao = _identidade(url)
    if isinstance(identidade_mutacao, str):
        return f"MUTATION_DB=UNREACHABLE {identidade_mutacao}"

    if identidade_teste.indistinguivel or identidade_mutacao.indistinguivel:
        return (
            "MUTATION_DB=AMBIGUOUS_IDENTITY "
            f"teste={identidade_teste} mutacao={identidade_mutacao}"
        )
    if identidade_teste == identidade_mutacao:
        return f"MUTATION_DB=SAME_REAL_DATABASE_AS_TEST identidade={identidade_mutacao}"
    if identidade_mutacao.database != declarado:
        return (
            "MUTATION_DB=UNEXPECTED_DATABASE "
            f"current={identidade_mutacao.database} declarado={declarado}"
        )

    alternativa = os.environ.get("PIA_MUTATION_DATABASE_URL")
    principal = os.environ.get("MUTANT_DATABASE_URL")
    if alternativa and principal and alternativa != principal:
        identidade_alternativa = _identidade(alternativa)
        if isinstance(identidade_alternativa, str):
            return f"MUTATION_DB=ALTERNATE_URL_UNREACHABLE {identidade_alternativa}"
        if identidade_alternativa.indistinguivel:
            return f"MUTATION_DB=AMBIGUOUS_IDENTITY alternativa={identidade_alternativa}"
        if identidade_alternativa != identidade_mutacao:
            return (
                "MUTATION_DB=MUTATION_URLS_DISAGREE "
                f"MUTANT_DATABASE_URL={identidade_mutacao} "
                f"PIA_MUTATION_DATABASE_URL={identidade_alternativa}"
            )

    motor = create_engine(url)
    try:
        with motor.begin() as conexao:
            atual = conexao.execute(text("select current_database()")).scalar_one()
            if atual != identidade_mutacao.database:
                return f"MUTATION_DB=IDENTITY_CHANGED current={atual}"
            conexao.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            conexao.execute(text("CREATE SCHEMA public"))
    finally:
        motor.dispose()

    env = os.environ.copy()
    env["DATABASE_URL"] = url
    upgrade = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if upgrade.returncode != 0:
        return f"MUTATION_DB=UPGRADE_FAILED exit={upgrade.returncode}"

    atual_alembic = subprocess.run(
        [sys.executable, "-m", "alembic", "current"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    linhas = [linha for linha in atual_alembic.stdout.splitlines() if linha.strip()]
    folha = linhas[-1].split()[0] if linhas else ""
    if folha != MIGRATION_LEAF:
        return f"MUTATION_DB=UNEXPECTED_LEAF folha={folha or 'AUSENTE'} esperada={MIGRATION_LEAF}"

    print(f"MUTATION_DB_REBUILT={identidade_mutacao} LEAF={folha}")
    print(f"TEST_DB_PRESERVED={identidade_teste}")
    return None


def run_tests(paths: tuple[str, ...]) -> int:
    env = os.environ.copy()
    mutation_url = env.get("MUTANT_DATABASE_URL") or env.get("PIA_MUTATION_DATABASE_URL")
    if PG in paths and mutation_url:
        env["DATABASE_URL"] = mutation_url
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--no-cov", "-p", "no:cacheprovider", *paths],
        cwd=ROOT,
        env=env,
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    ).returncode


def main() -> int:
    recusa = preparar_banco_de_mutacao()
    if recusa is not None:
        print(recusa)
        return 4

    baselines: dict[tuple[str, ...], int] = {}
    for mutant in MUTANTS:
        if mutant.tests not in baselines:
            baselines[mutant.tests] = run_tests(mutant.tests)
        if baselines[mutant.tests] != 0:
            print(f"{mutant.name}=INVALID_BASELINE exit={baselines[mutant.tests]}")
            return 2

    killed = 0
    for mutant in MUTANTS:
        path = ROOT / mutant.path
        original = path.read_text(encoding="utf-8")
        mutated = original
        for replacement in mutant.replacements:
            count = mutated.count(replacement.old)
            if count != 1:
                print(f"{mutant.name}=INVALID_TARGET count={count}")
                return 3
            mutated = mutated.replace(replacement.old, replacement.new)
        try:
            path.write_text(mutated, encoding="utf-8")
            code = run_tests(mutant.tests)
        finally:
            path.write_text(original, encoding="utf-8")
        status = "KILLED" if code != 0 else "SURVIVED"
        print(f"{mutant.name}={status}")
        killed += int(code != 0)

    print(f"E742_MUTANTS={killed}/{len(MUTANTS)} KILLED")
    return 0 if killed == len(MUTANTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
