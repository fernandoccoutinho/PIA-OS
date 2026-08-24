#!/usr/bin/env python3
"""
Arnês dos oito mutantes novos da E7.4-1.

```text
GUARD_WITHOUT_MUTANT = UNVERIFIED_GUARD
ALVO AUSENTE, AMBÍGUO OU ABSORVIDO POR OUTRA GUARDA -> ABORTA A CONTAGEM
```

Cada mutante altera **produção** (nunca o teste), roda os testes que
deveriam morrer, e exige `FAILED`. Um mutante cujo alvo não é encontrado
aborta a contagem em vez de contar como matado — lição da E6.3 (mS2) e
da E7.1 (M-s3): mutante com alvo ausente é pior que mutante ausente,
porque aparece na lista e parece medido.

O mutante M-a, que altera a própria migration, roda contra um banco
DEDICADO: rodá-lo no banco da suíte deixaria o schema adulterado de pé
para os testes seguintes, e o mutante contaminaria a medição em vez de
ser medido.
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Mutante:
    nome: str
    arquivo: str
    alvo: str
    troca: str
    testes: tuple[str, ...]
    descricao: str
    banco_dedicado: bool = False


MUTANTES: tuple[Mutante, ...] = (
    Mutante(
        nome="M-AVAILABLE",
        arquivo="app/connections/models/enums.py",
        alvo=(
            "ConnectionMethod.PROVIDER_NATIVE_MCP_INBOUND: " "ConnectionState.PREFLIGHT_REQUIRED,"
        ),
        troca="ConnectionMethod.PROVIDER_NATIVE_MCP_INBOUND: ConnectionState.AVAILABLE,",
        testes=(
            "tests/static/test_e741_connection_boundary.py"
            "::test_e741s14_apenas_o_manual_pode_estar_available",
        ),
        descricao="método nasce AVAILABLE",
    ),
    Mutante(
        nome="M-SUPERSEDE",
        arquivo="app/connections/repositories/connection_repository.py",
        alvo=(
            "            .values(state=EntitlementState.SUPERSEDED, "
            "superseded_by_id=successor_id)"
        ),
        troca=(
            "            .values(\n"
            "                state=EntitlementState.SUPERSEDED,\n"
            "                superseded_by_id=successor_id,\n"
            "                origin=EntitlementOrigin.OFFICIALLY_DISCOVERED,\n"
            "            )"
        ),
        testes=(
            "tests/integration/connections/test_connection_catalog_and_entitlement.py"
            "::test_e741c18_oficial_supersede_o_declarado_preservando_origem_e_instante",
        ),
        descricao="USER_DECLARED é sobrescrito em vez de superseditado",
    ),
    Mutante(
        nome="M-COLLAPSE",
        arquivo="app/connections/models/catalog.py",
        alvo='    __tablename__ = "connection_model_releases"',
        troca='    __tablename__ = "connection_model_families"',
        testes=(
            "tests/static/test_e741_connection_boundary.py"
            "::test_e741s15_familia_release_provedor_e_conexao_nao_colapsam",
        ),
        descricao="família e release são fundidas na mesma tabela",
    ),
    Mutante(
        nome="M-STALE",
        arquivo="app/connections/schemas/projection.py",
        alvo="        if self.valid_until <= self.observed_at:",
        troca="        if False:",
        testes=(
            "tests/integration/connections/test_connection_catalog_and_entitlement.py"
            "::test_e741c24_snapshot_vencido_e_lido_como_stale_e_nao_e_apagado",
            "tests/unit/connections/test_connection_projection.py",
        ),
        descricao="TTL inválido deixa de ser recusado, cache vencido vira válido",
    ),
    Mutante(
        nome="M-SCAN",
        arquivo="app/connections/services/connection_profile_service.py",
        alvo="import uuid",
        troca="import os  # noqa: F401\nimport uuid",
        testes=(
            "tests/static/test_e741_connection_boundary.py"
            "::test_e741s04_nenhuma_varredura_local",
        ),
        descricao="descoberta faz varredura local",
    ),
    Mutante(
        nome="M-FK",
        arquivo="alembic/versions/b47e9c05d3fa_create_connection_kernel_e7_4_1.py",
        alvo=(
            '            ["connection_id", "control_principal_ref"],\n'
            '            [f"{_PROFILES}.id", f"{_PROFILES}.control_principal_ref"],\n'
            '            name="fk_connection_execution_receipts_connection_within_principal",'
        ),
        troca=(
            '            ["connection_id"],\n'
            '            [f"{_PROFILES}.id"],\n'
            '            name="fk_connection_execution_receipts_connection_within_principal",'
        ),
        testes=(
            "tests/integration/connections/test_connection_execution_receipt.py"
            "::test_e741p08_recibo_de_a_nao_liga_a_conexao_de_b_por_sql_bruto",
        ),
        descricao="FK bilateral volta a simples",
        banco_dedicado=True,
    ),
    Mutante(
        nome="M-RECEIPT",
        arquivo="app/orchestration/services/manual_handoff_export_service.py",
        alvo="        self._connection_receipts.record_execution(",
        troca="        _ = self._connection_receipts and None or (lambda **k: None)(",
        testes=(
            "tests/integration/connections/test_connection_execution_receipt.py"
            "::test_e741p01_attempt_manual_cria_exatamente_um_recibo",
        ),
        descricao="handoff manual não produz recibo",
    ),
    Mutante(
        nome="M-DUPLICATE",
        arquivo="app/connections/repositories/connection_repository.py",
        alvo="        return self._session.begin_nested()",
        troca='        return __import__("contextlib").nullcontext()',
        testes=(
            "tests/integration/connections/test_connection_advisory_lock.py"
            "::test_e741l03_perder_a_corrida_nao_invalida_a_transacao_externa",
        ),
        descricao="perdedor da corrida invalida a transação (savepoint removido)",
    ),
    Mutante(
        nome="M-LOCK",
        arquivo="app/connections/repositories/connection_repository.py",
        alvo=(
            "        if self._session.get_bind().dialect.name "
            '!= "postgresql":\n'
            "            return"
        ),
        troca="        return",
        testes=("tests/integration/connections/test_connection_advisory_lock.py",),
        descricao="lock consultivo removido — serialização deixa de existir",
    ),
)


def _reconstruir_schema(env: dict[str, str]) -> None:
    """Derruba e reergue o schema a partir da migration EM DISCO.

    ACHADO, registrado: a primeira versão deste arnês rodava o mutante da
    migration contra um banco JÁ migrado com a versão original. O arquivo
    mudava e o schema não — e o mutante sobrevivia por construção.

    ```text
    MUTATED_FILE != MUTATED_SCHEMA
    ```
    """
    # `downgrade base` percorre migrations que recusam com linhas e que
    # dependem umas das outras; para um banco DEDICADO de mutação, o
    # caminho honesto é derrubar o schema inteiro e reergê-lo.
    from sqlalchemy import create_engine, text

    url = env["DATABASE_URL"]
    motor = create_engine(url)
    with motor.begin() as conexao:
        conexao.execute(text("DROP SCHEMA public CASCADE"))
        conexao.execute(text("CREATE SCHEMA public"))
    motor.dispose()
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )


def _rodar(testes: tuple[str, ...], env: dict[str, str]) -> bool:
    """Devolve True se ALGUM teste falhou (isto é, se o mutante morreu)."""
    processo = subprocess.run(
        [sys.executable, "-m", "pytest", *testes, "-q", "--no-cov", "-p", "no:cacheprovider"],
        cwd=BACKEND,
        env=env,
        capture_output=True,
        text=True,
    )
    return processo.returncode != 0


def main() -> int:
    base_env = dict(os.environ)
    dedicado = dict(base_env)
    dedicado["DATABASE_URL"] = base_env.get(
        "MUTANT_DATABASE_URL",
        "postgresql+psycopg://piaos:piaos@127.0.0.1:5432/pia_os_mutant_test",
    )

    mortos = 0
    abortado = False
    print("MUTANTES NOVOS E7.4-1")
    for mutante in MUTANTES:
        caminho = BACKEND / mutante.arquivo
        original = caminho.read_text(encoding="utf-8")
        ocorrencias = original.count(mutante.alvo)
        if ocorrencias != 1:
            print(f"  {mutante.nome:<14} ALVO_{'AUSENTE' if not ocorrencias else 'AMBÍGUO'}")
            abortado = True
            continue
        env = dedicado if mutante.banco_dedicado else base_env
        try:
            caminho.write_text(original.replace(mutante.alvo, mutante.troca), encoding="utf-8")
            if mutante.banco_dedicado:
                _reconstruir_schema(env)
            morreu = _rodar(mutante.testes, env)
        finally:
            caminho.write_text(original, encoding="utf-8")
            if mutante.banco_dedicado:
                # O schema adulterado NÃO pode sobreviver ao mutante.
                _reconstruir_schema(env)
        estado = "KILLED" if morreu else "SURVIVED"
        mortos += int(morreu)
        print(f"  {mutante.nome:<14} {estado:<9} {mutante.descricao}")

    total = len(MUTANTES)
    if abortado:
        print(f"\nCONTAGEM ABORTADA — alvo ausente ou ambíguo ({mortos}/{total} medidos)")
        return 2
    print(f"\nNOVOS = {mortos}/{total} KILLED")
    return 0 if mortos == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
