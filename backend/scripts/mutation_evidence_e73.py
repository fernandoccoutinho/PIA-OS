"""
Arnês de mutação da E7.3 — `baseline exit 0 -> mutante exit != 0`.

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

Corretivo R1 (Chain114): os cinco mutantes originais são preservados e
cinco novos medem as guardas criadas pelos achados C1, C2 e C3 —
detecção de insert versus replay, vínculo requisição/comando, vínculo
Attempt<->Step na reconstrução, redação do conteúdo no 422/log e a
constraint canônica de `validation_codes`.

Corretivo R2 (Chain115): os dez anteriores seguem intactos, e três novos
medem o `sealer_ref` na impressão digital de selar e exportar, mais a
constraint hexadecimal de `request_sha256`.

Uso:

    python -m scripts.mutation_evidence_e73
    python -m scripts.mutation_evidence_e73 --only M2
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

_API = "tests/integration/api/test_e73_governance_api.py"
_PERSISTENCIA = "tests/integration/orchestration/test_e73_delegation_schema.py"
_ESTATICO = "tests/static/test_e72_orchestration_boundary.py"
_DTO_UNITARIO = "tests/unit/orchestration/test_e73_public_dtos.py"
_UNITARIO = "tests/unit/orchestration/test_return_validation.py"


@dataclasses.dataclass(frozen=True)
class Mutante:
    ident: str
    descricao: str
    arquivo: str
    de: str
    para: str
    alvo: tuple[str, ...]


_REGIAO_ESTADO = "".join(
    [
        "        if agenda.state in (ScheduleState.STOPPED, ScheduleState.CANCELLED):\n",
        "            # Terminal recusa SEM nova escrita: registrar de novo o que já\n",
        "            # está registrado inflaria o histórico a cada tentativa.\n",
        "            raise OrchestrationLifecycleViolationError(\n",
        '                message=f"Schedule {agenda.state.value} não despacha",\n',
        '                detail={"current_state": agenda.state.value},\n',
        "            )\n",
        "        if agenda.state is ScheduleState.PAUSED:\n",
        "            raise OrchestrationLifecycleViolationError(\n",
        '                message="Schedule PAUSED exige retomada explícita antes de exportar",\n',
        '                detail={"current_state": agenda.state.value},\n',
        "            )\n",
        "        if agenda.state is not ScheduleState.ACTIVE:\n",
        "            raise OrchestrationLifecycleViolationError(\n",
        '                message=f"exportação exige Schedule ACTIVE; '
        'estado atual {agenda.state.value}",\n',
        '                detail={"current_state": agenda.state.value},\n',
        "            )\n",
    ]
)
"""Região que governa o estado no preflight, alvo de `M-c` e `M-s`.

Mutar UMA linha dela sobrevivia: as checagens se compensam entre si, e
ainda há uma guarda congelada da E7.1 em `seal_step_for_export`. Mutante
que outra guarda absorve não mede nada, então o alvo é a região inteira
e o `para` deixa passar exatamente o estado que o nome do mutante diz.
"""
_SO_PAUSA = "".join(
    [
        "        if agenda.state is ScheduleState.PAUSED:\n",
        "            raise OrchestrationLifecycleViolationError(\n",
        '                message="Schedule PAUSED exige retomada explícita antes de exportar",\n',
        '                detail={"current_state": agenda.state.value},\n',
        "            )\n",
    ]
)

_SO_TERMINAL = "".join(
    [
        "        if agenda.state in (ScheduleState.STOPPED, ScheduleState.CANCELLED):\n",
        "            # Terminal recusa SEM nova escrita: registrar de novo o que já\n",
        "            # está registrado inflaria o histórico a cada tentativa.\n",
        "            raise OrchestrationLifecycleViolationError(\n",
        '                message=f"Schedule {agenda.state.value} não despacha",\n',
        '                detail={"current_state": agenda.state.value},\n',
        "            )\n",
    ]
)


MUTANTES: tuple[Mutante, ...] = (
    Mutante(
        "M-g1",
        "ignorar o gate tecnico declarado na etapa",
        "app/orchestration/services/manual_handoff_export_service.py",
        "        exigencia = gate_requirement(tuple(etapa.constraints))\n        "
        "if exigencia is None:",
        "        exigencia = gate_requirement(tuple(etapa.constraints))\n        if True:",
        (_API,),
    ),
    Mutante(
        "M-g2",
        "principal tecnico satisfazendo o gate humano",
        "app/orchestration/adapters/deny_all_human_gate.py",
        "        return GateDecision(granted=False, "
        "reason_code=GateReasonCode.HUMAN_AUTHORITY_UNAVAILABLE)",
        "        return GateDecision(granted=True, reason_code=GateReasonCode.AUTHORIZED)",
        (_API,),
    ),
    Mutante(
        "M-h",
        "remover content_sha256 do consumo da delegacao",
        "app/orchestration/repositories/orchestration_repository.py",
        # REAPONTADO: a revalidação de conteúdo no serviço (corretivo C1)
        # absorve este mutante pela API. A cláusula do UPDATE é a camada de
        # baixo e tem prova própria em `e73p15`.
        "AND content_sha256 = :h AND state = 'active' AND valid_until > now()",
        "AND state = 'active' AND valid_until > now()",
        (_PERSISTENCIA,),
    ),
    Mutante(
        "M-u",
        "remover state=active do UPDATE atomico de consumo",
        "app/orchestration/repositories/orchestration_repository.py",
        "SET state = 'consumed', consumed_at = now(), consumed_by_attempt_id = :a ",
        "SET consumed_at = now(), consumed_by_attempt_id = :a ",
        (_API,),
    ),
    Mutante(
        "M-x",
        "ignorar a expiracao sincrona da delegacao",
        "app/orchestration/repositories/orchestration_repository.py",
        "AND state = 'active' AND valid_until <= now()",
        "AND state = 'active' AND valid_until > now() + interval '99 years'",
        (_API,),
    ),
    Mutante(
        "M-r",
        "permitir reativar delegacao terminal",
        "alembic/versions/f2c60d8a41b9_create_delegation_control_audit_e7_3.py",
        "                IF OLD.state <> 'active' THEN",
        "                IF FALSE THEN",
        (_PERSISTENCIA,),
    ),
    Mutante(
        "M-c",
        "CANCELLED e STOPPED alcancam o transporte",
        "app/orchestration/services/manual_handoff_export_service.py",
        _REGIAO_ESTADO,
        _SO_PAUSA,
        (_API,),
    ),
    Mutante(
        "M-s",
        "PAUSED alcanca o transporte",
        "app/orchestration/services/manual_handoff_export_service.py",
        _REGIAO_ESTADO,
        _SO_TERMINAL,
        (_API,),
    ),
    Mutante(
        "M-a",
        "auditoria escrevendo no artefato auditado",
        "app/orchestration/services/audit_service.py",
        "        parecer = self._repository.create_audit_opinion(",
        "        resultado.output_bytes = 0\n        parecer = "
        "self._repository.create_audit_opinion(",
        (_API,),
    ),
    Mutante(
        "M-p",
        "PASS_FINAL entrando no vocabulario de parecer",
        "app/orchestration/models/enums.py",
        '    OUT_OF_SCOPE = "out_of_scope"',
        '    OUT_OF_SCOPE = "out_of_scope"\n    PASS_FINAL = "pass_final"',
        (_API,),
    ),
    Mutante(
        "M-o",
        "troca declarada de provedor nao gera observacao",
        "app/orchestration/services/return_validation_service.py",
        "        if anterior.declared_provider_id == provedor_atual:\n            return",
        "        if True:\n            return",
        (_API,),
    ),
    Mutante(
        "M-f",
        "Schedule completa antes de todas as Steps RETURNED",
        "app/orchestration/repositories/orchestration_repository.py",
        "        return int(pendentes) == 0",
        "        return True",
        (_API,),
    ),
    Mutante(
        "M-auth",
        "remover a dependency de uma rota E7.3",
        "app/routers/orchestration.py",
        "def ler_governanca(\n    schedule_id: uuid.UUID,\n    principal: GuardedPrincipal,",
        "def ler_governanca(\n    schedule_id: uuid.UUID,\n    principal: "
        "ProgrammaticPrincipal | None = None,",
        (_API, _ESTATICO),
    ),
    Mutante(
        "M-c1",
        "aceitar autorizacao fabricada pelo chamador (achado C1)",
        "app/orchestration/services/manual_handoff_export_service.py",
        "        self._consumir_autorizacao(autorizacao)",
        "        pass",
        (_API,),
    ),
    Mutante(
        "M-c1b",
        "nao revalidar o conteudo entre autorizacao e despacho",
        "app/orchestration/services/manual_handoff_export_service.py",
        "        if conteudo_agora.content_sha256() != autorizacao.content_sha256:",
        "        if False:",
        (_API,),
    ),
    Mutante(
        "M-c2",
        "replay devolve o evento mais recente e nao o original (achado C2)",
        "app/routers/orchestration.py",
        "            event_id=uuid.UUID(recibo.outcome_ref),",
        "            event_id=repositorio.list_control_events(\n"
        "                control_principal_ref=principal_ref, schedule_id=schedule_id\n"
        "            )[-1].id,",
        (_API,),
    ),
    Mutante(
        "M-c2b",
        "replay de parecer devolve o mais recente (achado C2)",
        "app/routers/orchestration.py",
        "            opinion_id=uuid.UUID(recibo.outcome_ref),",
        "            opinion_id=repositorio.list_audit_opinions(\n"
        "                control_principal_ref=principal_ref, schedule_id=schedule_id\n"
        "            )[-1].id,",
        (_API,),
    ),
    Mutante(
        "M-c4",
        "revogacao ignora a Step declarada no path (achado C4)",
        "app/orchestration/services/delegation_service.py",
        "        if delegacao.step_id != step_id:",
        "        if False:",
        (_API,),
    ),
    Mutante(
        "M-c5",
        "aceitar valid_until sem fuso horario (achado C5)",
        # O serviço tem guarda equivalente para chamada direta e absorveria
        # este mutante pela API; o alvo é a camada de ENTRADA, medida pelo
        # unitário do DTO.
        "app/schemas/orchestration_public.py",
        "        if valor.tzinfo is None or valor.tzinfo.utcoffset(valor) is None:",
        "        if False:",
        (_DTO_UNITARIO,),
    ),
    Mutante(
        "M-c6",
        "advance() deixa de exigir predecessoras RETURNED (achado C6)",
        "app/orchestration/services/schedule_service.py",
        "        return tuple(\n" "            self._repository.list_unreturned_predecessors(",
        "        return ()  # type: ignore[unreachable]\n"
        "        return tuple(\n"
        "            self._repository.list_unreturned_predecessors(",
        (_API,),
    ),
    Mutante(
        "M-c3",
        "remover os CHECK de vocabulario do banco (achado C3)",
        "alembic/versions/a91d3f7c26be_close_e73_vocabularies.py",
        "        op.create_check_constraint(nome, tabela, sa.text(regra))",
        "        pass",
        (_PERSISTENCIA,),
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
    parser = argparse.ArgumentParser(prog="mutation_evidence_e73")
    parser.add_argument("--only", action="append", default=None)
    args = parser.parse_args(argv)
    return executar(set(args.only) if args.only else None)


if __name__ == "__main__":  # pragma: no cover - entrypoint
    raise SystemExit(main())
