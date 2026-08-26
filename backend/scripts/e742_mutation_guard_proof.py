#!/usr/bin/env python3
"""Prova NEGATIVA do guard de identidade de banco do arnês da E7.4-2.

Uma guarda que nunca foi vista recusar não foi provada:

```text
A GUARD NEVER SEEN REFUSING IS AN UNPROVEN GUARD
```

O guard compara a identidade REAL devolvida pelo servidor
(``current_database()``, ``inet_server_addr()``, ``inet_server_port()``),
não o texto da URL. Esta prova ataca exatamente essa diferença: aponta o
arnês para o banco de TESTE por uma URL textualmente diferente e exige que
ele recuse ANTES de qualquer ``DROP SCHEMA``.

A cada recusa a prova confere uma TABELA-SENTINELA criada no banco de
teste. Ela é o canário: se o guard tivesse falhado, o ``DROP SCHEMA public
CASCADE`` a teria levado junto.

```text
REFUSAL_REPORTED != DESTRUCTION_AVOIDED
```

Não toca em ``app/``, migrations, contratos ou testes do sistema.
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[1]
ARNES = ROOT / "scripts" / "e742_mcp_mutants.py"
SENTINELA = "_e742_guard_sentinel"
EXIT_RECUSA = 4


@dataclass(frozen=True)
class Caso:
    nome: str
    ambiente: dict[str, str]
    esperado: str


def _url_equivalente(url: str) -> str:
    """Mesma identidade real, texto diferente.

    ``localhost`` resolve para o mesmo servidor que ``127.0.0.1``, e um
    parâmetro de conexão inócuo muda a string sem mudar o destino.
    """
    partes = urlsplit(url)
    autoridade = (partes.netloc or "").replace("127.0.0.1", "localhost")
    consulta = "&".join(filter(None, [partes.query, "application_name=e742_guard_proof"]))
    return urlunsplit((partes.scheme, autoridade, partes.path, consulta, partes.fragment))


def _motor(url: str):
    from sqlalchemy import create_engine

    return create_engine(url)


def _criar_sentinela(url: str) -> None:
    from sqlalchemy import text

    motor = _motor(url)
    try:
        with motor.begin() as conexao:
            conexao.execute(text(f"DROP TABLE IF EXISTS {SENTINELA}"))
            conexao.execute(text(f"CREATE TABLE {SENTINELA} (marca text primary key)"))
            conexao.execute(text(f"INSERT INTO {SENTINELA} (marca) VALUES ('intacta')"))
    finally:
        motor.dispose()


def _remover_sentinela(url: str) -> None:
    from sqlalchemy import text

    motor = _motor(url)
    try:
        with motor.begin() as conexao:
            conexao.execute(text(f"DROP TABLE IF EXISTS {SENTINELA}"))
    finally:
        motor.dispose()


def _sentinela_intacta(url: str) -> bool:
    from sqlalchemy import text

    motor = _motor(url)
    try:
        with motor.connect() as conexao:
            existe = conexao.execute(
                text("select to_regclass(:nome) is not null"), {"nome": f"public.{SENTINELA}"}
            ).scalar_one()
            if not existe:
                return False
            marca = conexao.execute(text(f"select marca from {SENTINELA}")).scalar_one_or_none()
    finally:
        motor.dispose()
    return marca == "intacta"


def _executar_arnes(ambiente: dict[str, str]) -> tuple[int, str]:
    env = os.environ.copy()
    for chave in ("MUTANT_DATABASE_URL", "PIA_MUTATION_DATABASE_URL"):
        env.pop(chave, None)
    env.update(ambiente)
    processo = subprocess.run(
        [sys.executable, str(ARNES)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    return processo.returncode, (processo.stdout + processo.stderr).strip()


def _preparar_direto(ambiente: dict[str, str]) -> tuple[int, str]:
    """Chama só o guard, sem rodar mutante — controle de não vacuidade."""
    env = os.environ.copy()
    for chave in ("MUTANT_DATABASE_URL", "PIA_MUTATION_DATABASE_URL"):
        env.pop(chave, None)
    env.update(ambiente)
    codigo = (
        "import sys; sys.path.insert(0, 'scripts');"
        "import e742_mcp_mutants as m;"
        "r = m.preparar_banco_de_mutacao();"
        "print('ACEITO' if r is None else r);"
        "sys.exit(0 if r is None else 4)"
    )
    processo = subprocess.run(
        [sys.executable, "-c", codigo],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    return processo.returncode, (processo.stdout + processo.stderr).strip()


def main() -> int:
    teste = os.environ.get("DATABASE_URL")
    mutacao = os.environ.get("MUTANT_DATABASE_URL") or os.environ.get("PIA_MUTATION_DATABASE_URL")
    if not teste or not mutacao:
        print("GUARD_PROOF=NOT_CONFIGURED exporte DATABASE_URL e MUTANT_DATABASE_URL")
        return 2

    teste_disfarcado = _url_equivalente(teste)
    if teste_disfarcado == teste:
        print("GUARD_PROOF=URL_NAO_DISFARCAVEL a prova exige duas grafias do mesmo banco")
        return 2
    print(f"URL_TESTE            = {teste}")
    print(f"URL_TESTE_DISFARCADA = {teste_disfarcado}")

    casos = [
        Caso(
            "A_MESMO_BANCO_OUTRA_GRAFIA",
            {"MUTANT_DATABASE_URL": teste_disfarcado},
            "MUTATION_DB=SAME_REAL_DATABASE_AS_TEST",
        ),
        Caso(
            "B_DUAS_URLS_DE_MUTACAO_DISCORDAM",
            {
                "MUTANT_DATABASE_URL": mutacao,
                "PIA_MUTATION_DATABASE_URL": teste_disfarcado,
            },
            "MUTATION_DB=MUTATION_URLS_DISAGREE",
        ),
    ]
    socket_url = os.environ.get("PIA_GUARD_PROOF_SOCKET_URL")
    if socket_url:
        casos.append(
            Caso(
                "C_IDENTIDADE_AMBIGUA_POR_SOCKET",
                {"MUTANT_DATABASE_URL": socket_url},
                "MUTATION_DB=AMBIGUOUS_IDENTITY",
            )
        )

    falhas = 0
    _criar_sentinela(teste)
    try:
        for caso in casos:
            codigo, saida = _executar_arnes(caso.ambiente)
            primeira = saida.splitlines()[0] if saida else ""
            recusou = codigo == EXIT_RECUSA and primeira.startswith(caso.esperado)
            intacta = _sentinela_intacta(teste)
            estado = "PASS" if recusou and intacta else "FAIL"
            falhas += int(estado == "FAIL")
            print(
                f"{caso.nome} = {estado} exit={codigo} "
                f"sentinela={'INTACTA' if intacta else 'PERDIDA'} saida={primeira}"
            )
        if not socket_url:
            print(
                "C_IDENTIDADE_AMBIGUA_POR_SOCKET = SKIPPED "
                "sem PIA_GUARD_PROOF_SOCKET_URL; ramo implementado e NAO exercitado"
            )

        # Controle de nao vacuidade: o guard tem de ACEITAR o par legitimo,
        # inclusive com as duas variaveis escritas de formas diferentes.
        codigo, saida = _preparar_direto(
            {
                "MUTANT_DATABASE_URL": mutacao,
                "PIA_MUTATION_DATABASE_URL": _url_equivalente(mutacao),
            }
        )
        aceitou = codigo == 0 and "MUTATION_DB_REBUILT" in saida
        falhas += int(not aceitou)
        print(
            f"D_CONTROLE_PAR_LEGITIMO = {'PASS' if aceitou else 'FAIL'} "
            f"exit={codigo} saida={saida.splitlines()[0] if saida else ''}"
        )
    finally:
        _remover_sentinela(teste)

    if falhas:
        print(f"GUARD_PROOF=FAIL casos_com_falha={falhas}")
        return 1
    print("GUARD_PROOF=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
