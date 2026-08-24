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


#: `M-FK` foi RETIRADO no corretivo R1, e a razão é declarada em vez de
#: silenciada.
#:
#: ```text
#: ALVO ABSORVIDO POR OUTRA GUARDA -> NÃO CONTA COMO MATADO
#: ```
#:
#: Ele mutava a FK **binária** de `b47e9c05d3fa` para uma FK simples. A
#: migration corretiva `c58d1e0a94f7` derruba aquela FK e cria a
#: **ternária** em seu lugar, de modo que a mutação passou a ser
#: sobrescrita pela migration seguinte: o mutante sobrevivia por
#: construção, não por lacuna de prova.
#:
#: A propriedade que ele media — coerência de dono — é IMPLICADA pela
#: coerência de rota, e é `M-METHOD` que a mede agora. Mantê-lo na lista
#: seria exibir um mutante cujo alvo não existe mais no schema entregue,
#: que é o defeito de contagem que este programa já pagou duas vezes
#: (E6.3 mS2, E7.1 M-s3).
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
    Mutante(
        nome="M-METHOD",
        arquivo="alembic/versions/c58d1e0a94f7_receipt_route_coherence_e7_4_1_r1.py",
        alvo=(
            '        ["connection_id", "control_principal_ref", "connection_method"],\n'
            '        ["id", "control_principal_ref", "method"],'
        ),
        troca=(
            '        ["connection_id", "control_principal_ref"],\n'
            '        ["id", "control_principal_ref"],'
        ),
        testes=(
            "tests/integration/connections/test_connection_execution_receipt.py"
            "::test_e741p12_recibo_nao_declara_metodo_diferente_do_perfil",
        ),
        descricao="FK da rota volta a ser de dono — recibo falsifica o método",
        banco_dedicado=True,
    ),
    Mutante(
        nome="M-MANUAL-MODEL",
        arquivo="alembic/versions/c58d1e0a94f7_receipt_route_coherence_e7_4_1_r1.py",
        alvo="    op.create_check_constraint(_CHECK_MANUAL, _RECEIPTS, sa.text(_MANUAL_TRUTH_SQL))",
        troca="    pass  # CHECK da verdade do manual removido",
        testes=(
            "tests/integration/connections/test_connection_execution_receipt.py"
            "::test_e741p13_manual_nao_admite_operador_nem_modelo_por_sql_bruto",
            "tests/integration/connections/test_connection_execution_receipt.py"
            "::test_e741p14_manual_nao_admite_atestacao_diferente_de_unknown",
        ),
        descricao="manual aceita operador, modelo fabricado e atestação inventada",
        banco_dedicado=True,
    ),
    Mutante(
        nome="M-VO-MANUAL",
        arquivo="app/connections/services/connection_execution_receipt_service.py",
        alvo="        if self.connection_method is ConnectionMethod.MANUAL_HANDOFF and any(",
        troca="        if False and any(",
        testes=(
            "tests/integration/connections/test_connection_execution_receipt.py"
            "::test_e741p15_os_value_objects_recusam_manual_com_modelo_fabricado",
        ),
        descricao="value object deixa de recusar manual com modelo fabricado",
    ),
    Mutante(
        nome="M-SILENCE",
        arquivo="app/orchestration/services/orchestration_query_service.py",
        alvo="def _projetar_resultado(resultado: HandoffResult) -> ResultProjection:",
        troca="def _projetar_resultado(resultado: object) -> ResultProjection:",
        testes=(
            "tests/static/test_e741_connection_boundary.py"
            "::test_e741s17_os_helpers_do_servico_de_consulta_recebem_tipo_concreto",
        ),
        descricao="fronteira volta a receber `object` e pode ser silenciada",
    ),
    Mutante(
        nome="M-BYPASS",
        arquivo="app/routers/orchestration.py",
        alvo="    governanca = OrchestrationQueryService(repositorio).read_governance(",
        troca=(
            "    repositorio.list_delegations(\n"
            "        control_principal_ref=principal_ref, schedule_id=schedule_id\n"
            "    )\n"
            "    governanca = OrchestrationQueryService(repositorio).read_governance("
        ),
        testes=(
            "tests/static/test_e741_connection_boundary.py"
            "::test_e741s12_nenhuma_consulta_de_superficie_mcp_alcanca_o_repositorio",
        ),
        descricao="consulta de superfície MCP volta a alcançar o repositório",
    ),
    Mutante(
        nome="M-VIEW-MANUAL",
        arquivo="app/connections/schemas/projection.py",
        alvo=(
            "        if self.connection_method is ConnectionMethod.MANUAL_HANDOFF and any(\n"
            "            (\n"
            "                self.access_provider is not None,\n"
            "                self.requested_model is not None,\n"
            "                self.observed_model is not None,\n"
            "                self.model_attestation_level is not ModelAttestationLevel.UNKNOWN,\n"
            "            )\n"
            "        ):"
        ),
        troca="        if False:",
        testes=("tests/unit/connections/test_connection_projection.py",),
        descricao="a view do recibo volta a aceitar manual falso",
    ),
    Mutante(
        nome="M-ROUTER-OBJECT",
        arquivo="app/routers/orchestration.py",
        alvo="def _control_event_da_projecao(e: ControlEventProjection) -> dto.ControlEventView:",
        troca="def _control_event_da_projecao(e: object) -> dto.ControlEventView:",
        testes=(
            "tests/static/test_e741_connection_boundary.py"
            "::test_e741s18_os_mapeadores_do_router_tem_tipo_concreto_exato",
        ),
        descricao="mapeador do router rebaixado para `object`",
    ),
    Mutante(
        nome="M-CRASE",
        arquivo="app/routers/orchestration.py",
        alvo="def _control_event_da_projecao(e: ControlEventProjection) -> dto.ControlEventView:",
        troca=(
            "def _fronteira_adversarial(x: object) -> str:\n"
            "    return x.campo_inexistente  # type: ignore[attr-defined]  "
            "# `silencio novo`\n"
            "\n"
            "\n"
            "def _control_event_da_projecao(e: ControlEventProjection) -> dto.ControlEventView:"
        ),
        testes=(
            "tests/static/test_e741_connection_boundary.py"
            "::test_e741s20_o_router_conserva_apenas_os_ignores_historicos",
        ),
        descricao="ignore novo com crase — a heurística de linha era contornável",
    ),
    Mutante(
        nome="M-BROAD-IGNORE",
        arquivo="app/orchestration/services/orchestration_query_service.py",
        alvo="def _projetar_selo(selo: SealReceipt) -> SealReceiptProjection:",
        troca=(
            "def _fronteira_ampla(x: object) -> str:\n"
            "    return x.campo_inexistente  # type: ignore\n"
            "\n"
            "\n"
            "def _projetar_selo(selo: SealReceipt) -> SealReceiptProjection:"
        ),
        testes=(
            "tests/static/test_e741_connection_boundary.py"
            "::test_e741s16_fronteiras_novas_nao_silenciam_acesso_a_campo",
        ),
        descricao="`# type: ignore` amplo numa fronteira tipada",
    ),
    Mutante(
        nome="M-SWAP-IGNORE",
        arquivo="app/routers/orchestration.py",
        alvo=("        issued_at=parecer.issued_at,  # type: ignore[attr-defined]\n" "    )\n"),
        troca=(
            "        issued_at=parecer.issued_at,\n"
            "    )\n"
            "\n"
            "\n"
            "def _funcao_nao_autorizada(x: object) -> str:\n"
            "    return x.campo  # type: ignore[attr-defined]\n"
        ),
        testes=(
            "tests/static/test_e741_connection_boundary.py"
            "::test_e741s20_o_router_conserva_apenas_os_ignores_historicos",
        ),
        descricao=(
            "TRANSFERÊNCIA: -1 attr-defined em _audit_view, +1 em função "
            "não autorizada; total 48 preservado"
        ),
    ),
    Mutante(
        nome="M-DOC-FK",
        arquivo="docs/entregas/entrega-7/E7_4_1_CONNECTION_KERNEL.md",
        alvo="FK (connection_id, control_principal_ref, connection_method)",
        troca="FK (connection_id, control_principal_ref, wrong_method)",
        testes=(
            "tests/static/test_e741_connection_boundary.py"
            "::test_e741s21_a_documentacao_do_recibo_descreve_a_fk_real",
        ),
        descricao="documento descreve coluna incorreta com a palavra certa noutro parágrafo",
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
