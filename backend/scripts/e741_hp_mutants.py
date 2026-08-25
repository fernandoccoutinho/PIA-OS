#!/usr/bin/env python3
"""
Arnês dos mutantes novos da ponte de proteção humana (`E7.4-1 B1a`).

```text
GUARD_WITHOUT_MUTANT = UNVERIFIED_GUARD
ALVO AUSENTE, AMBÍGUO OU ABSORVIDO POR OUTRA GUARDA -> ABORTA A CONTAGEM
```

Cada mutante altera **produção** — nunca o teste — roda as provas que deveriam
morrer e exige `FAILED`. Alvo não encontrado aborta a contagem em vez de contar
como matado: mutante com alvo ausente é pior que mutante ausente, porque
aparece na lista e parece medido (E6.3 mS2, E7.1 M-s3).

Os mutantes de schema rodam contra um banco **DEDICADO**. Rodá-los no banco da
suíte deixaria o schema adulterado de pé para os testes seguintes.

```text
MUTATED_FILE != MUTATED_SCHEMA
```

Achado desta rodada, registrado porque a família volta sempre: `black`
juntou duas f-strings da migration DEPOIS de o mutante ter sido escrito, e
o alvo sumiu. O arnês abortou a contagem em vez de reportar 15/16 como se
nada houvesse — que é o serviço que ele existe para prestar.

```text
FORMATTER_MOVED_THE_TARGET = MUTANT_WITHOUT_A_TARGET
ALVO AUSENTE APARECE NA LISTA E PARECE MEDIDO
```

Cobertura por família, e cada uma existe porque um defeito real dela já foi
pago neste programa:

```text
fail-open           M-ABSENT-VIEW · M-OUTCOME-COERCE · M-EXPIRED
vínculo derivado    M-BINDING-SKIP · M-STALE-ATTEMPT
idempotência        M-WINNER-CAPS-ONLY · M-CONFLICT-SILENT
fronteira de pacote M-IMPORT-E4
efeito sem coerência M-BLOCK-NO-PAUSE
schema              M-CHECK-DROP · M-COHERENCE-IMMEDIATE · M-APPEND-ONLY
composição precoce  M-COMPOSE-EARLY
```
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]

UNITARIOS = "tests/unit/orchestration/test_human_protection_bridge.py"
INTEGRACAO = "tests/integration/orchestration/test_human_protection_schema.py"
ESTATICOS = "tests/static/test_e741_human_protection_boundary.py"
DRIFT = "tests/integration/orchestration/test_orchestration_core.py"


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
        nome="M-ABSENT-VIEW",
        arquivo="app/orchestration/protection/bridge.py",
        alvo="        if not isinstance(vista, GovernanceResolutionView):",
        troca="        if False:",
        testes=(UNITARIOS,),
        descricao="resposta ausente/errada da porta deixaria de ser recusada",
    ),
    Mutante(
        nome="M-OUTCOME-COERCE",
        arquivo="app/orchestration/ports/governance.py",
        alvo="        if self.outcome not in ACCEPTED_BOUNDARY_OUTCOMES:",
        troca="        if False:",
        testes=(UNITARIOS,),
        descricao="ADMISSIBLE/INADMISSIBLE seriam interpretados como decisão",
    ),
    Mutante(
        nome="M-EXPIRED",
        arquivo="app/orchestration/protection/bridge.py",
        alvo="        if agora > vista.valid_until:",
        troca="        if False:",
        testes=(UNITARIOS,),
        descricao="resolução vencida continuaria valendo",
    ),
    Mutante(
        nome="M-BINDING-SKIP",
        arquivo="app/orchestration/protection/bridge.py",
        alvo="        if vista.binding_sha256 != esperado:",
        troca="        if False:",
        testes=(UNITARIOS,),
        descricao="resolução de outra pergunta seria reutilizável",
    ),
    Mutante(
        nome="M-STALE-ATTEMPT",
        arquivo="app/orchestration/protection/binding.py",
        alvo='            raise ValueError("g3 exige attempt_id prealocado")',
        troca="            pass",
        testes=(UNITARIOS,),
        descricao="G3 sem tentativa prealocada geraria prova de tentativa velha",
    ),
    Mutante(
        nome="M-WINNER-CAPS-ONLY",
        arquivo="app/orchestration/repositories/human_protection_repository.py",
        alvo="            if getattr(vencedor, campo) != getattr(aplicacao, campo)",
        troca="            if False",
        testes=(INTEGRACAO,),
        descricao="vencedor divergente passaria por comparar só capacidades",
    ),
    Mutante(
        nome="M-CONFLICT-SILENT",
        arquivo="app/orchestration/protection/bridge.py",
        alvo=(
            "        if self._repository.inserir_se_ausente(aplicacao) is None:\n"
            "            self._repository.confirmar_vencedor(aplicacao)"
        ),
        troca="        self._repository.inserir_se_ausente(aplicacao)",
        testes=(UNITARIOS,),
        descricao="conflito seria dado por satisfeito sem verificar o vencedor",
    ),
    Mutante(
        nome="M-BLOCK-NO-PAUSE",
        arquivo="app/orchestration/protection/decision.py",
        alvo="            if self.gate_position is not GatePosition.G1 and not self.pause_applied:",
        troca="            if False:",
        testes=(UNITARIOS,),
        descricao="bloqueio fora de G1 sem pausa seria registrado como válido",
    ),
    Mutante(
        nome="M-ALLOWED-ENGAGEMENT",
        arquivo="app/orchestration/protection/decision.py",
        alvo="        if permitido and self.capability_engagement is not None:",
        troca="        if False:",
        testes=(UNITARIOS,),
        descricao="permissão carregaria categoria sem produtor",
    ),
    Mutante(
        nome="M-IMPORT-E4",
        arquivo="app/orchestration/protection/vocabulary.py",
        alvo="from enum import StrEnum",
        troca=(
            "from enum import StrEnum\n\n"
            "from app.memory.models.governance_enums import CriticalCapability"
        ),
        testes=(ESTATICOS,),
        descricao="import direto da E4 na E7 atravessaria a fronteira congelada",
    ),
    Mutante(
        nome="M-COMPOSE-EARLY",
        arquivo="app/routers/orchestration.py",
        alvo="from app.orchestration.errors.exceptions import (",
        troca=(
            "from app.orchestration.protection.bridge import HumanProtectionBridge\n"
            "from app.orchestration.errors.exceptions import ("
        ),
        testes=(ESTATICOS,),
        descricao="ponte composta no router antes da E8 passaria despercebida",
    ),
    Mutante(
        nome="M-VOCAB-DRIFT",
        arquivo="app/orchestration/ports/governance_vocabulary.py",
        alvo='    CATASTROPHIC_HARM_ENABLEMENT = "catastrophic_harm_enablement"',
        troca='    CATASTROPHIC_HARM_ENABLEMENT = "catastrophic_harm"',
        testes=(UNITARIOS,),
        descricao="divergência de vocabulário entre E7 e E4 passaria",
    ),
    Mutante(
        nome="M-CHECK-DROP",
        arquivo="alembic/versions/d7a4c1e93b28_human_protection_bridge_e7_4_1_b1a.py",
        alvo=(
            "f\"outcome <> 'blocked' OR capability_engagement IN \" "
            'f"{_ENGAGEMENTS_QUE_BLOQUEIAM_SQL}",'
        ),
        troca='        "true",',
        testes=(INTEGRACAO,),
        descricao="CHECK esvaziado deixaria bloqueio analítico entrar no schema real",
        banco_dedicado=True,
    ),
    Mutante(
        nome="M-COHERENCE-IMMEDIATE",
        arquivo="alembic/versions/d7a4c1e93b28_human_protection_bridge_e7_4_1_b1a.py",
        alvo=(
            'f"DEFERRABLE INITIALLY DEFERRED FOR EACH ROW "\n'
            '            f"EXECUTE FUNCTION {_FUNCAO_COERENCIA}()"\n'
            "        )\n    )\n    op.execute(\n        sa.text(\n"
            '            f"CREATE CONSTRAINT TRIGGER trg_hpec_coherence '
            'AFTER INSERT ON {_CAPACIDADES} "'
        ),
        troca=(
            'f"DEFERRABLE INITIALLY IMMEDIATE FOR EACH ROW "\n'
            '            f"EXECUTE FUNCTION {_FUNCAO_COERENCIA}()"\n'
            "        )\n    )\n    op.execute(\n        sa.text(\n"
            '            f"CREATE CONSTRAINT TRIGGER trg_hpec_coherence '
            'AFTER INSERT ON {_CAPACIDADES} "'
        ),
        testes=(INTEGRACAO,),
        descricao="coerência imediata quebraria a escrita pai/filha na mesma transação",
        banco_dedicado=True,
    ),
    Mutante(
        nome="M-APPEND-ONLY",
        arquivo="alembic/versions/d7a4c1e93b28_human_protection_bridge_e7_4_1_b1a.py",
        alvo='f"CREATE TRIGGER {gatilho_linha} BEFORE UPDATE OR DELETE ON {tabela} "',
        troca='f"CREATE TRIGGER {gatilho_linha} BEFORE DELETE ON {tabela} "',
        testes=(INTEGRACAO,),
        descricao="evento de proteção humana passaria a aceitar UPDATE",
        banco_dedicado=True,
    ),
    Mutante(
        nome="M-DRIFT",
        arquivo="app/orchestration/models/human_protection_event.py",
        alvo="    boundary_version: Mapped[int] = mapped_column(Integer, nullable=False)",
        troca="    boundary_version: Mapped[int] = mapped_column(Integer, nullable=True)",
        testes=(DRIFT, ESTATICOS),
        descricao="divergência ORM/schema deixaria de ser detectada",
    ),
)


def _reconstruir_schema(env: dict[str, str]) -> None:
    """Derruba e reergue o schema a partir da migration EM DISCO.

    ```text
    MUTATED_FILE != MUTATED_SCHEMA
    ```
    """
    from sqlalchemy import create_engine, text

    motor = create_engine(env["DATABASE_URL"])
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
    """Devolve True se ALGUM teste falhou — isto é, se o mutante morreu."""
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
    base_env.setdefault("ENVIRONMENT", "testing")
    dedicado = dict(base_env)
    dedicado["DATABASE_URL"] = base_env.get(
        "MUTANT_DATABASE_URL",
        "postgresql+psycopg://piaos:piaos@127.0.0.1:5432/pia_os_test_dedicado",
    )

    mortos = 0
    abortado = False
    print("MUTANTES NOVOS — E7.4-1 B1a (proteção humana)")
    for mutante in MUTANTES:
        caminho = BACKEND / mutante.arquivo
        original = caminho.read_text(encoding="utf-8")
        ocorrencias = original.count(mutante.alvo)
        if ocorrencias != 1:
            estado = "AUSENTE" if not ocorrencias else "AMBÍGUO"
            print(f"  {mutante.nome:<22} ALVO_{estado}")
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
        mortos += int(morreu)
        print(f"  {mutante.nome:<22} {'KILLED' if morreu else 'SURVIVED':<9} {mutante.descricao}")

    total = len(MUTANTES)
    if abortado:
        print(f"\nCONTAGEM ABORTADA — alvo ausente ou ambíguo ({mortos}/{total} medidos)")
        return 2
    print(f"\nNOVOS = {mortos}/{total} KILLED")
    return 0 if mortos == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
