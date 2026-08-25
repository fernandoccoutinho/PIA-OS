"""
As cinco tools MCP. Cada uma compõe fachada pública que já existe.

```text
TOOL_COMPOSES_SERVICE · TOOL_NEVER_TOUCHES_PERSISTENCE
```

Nenhuma tool fala com repositório, ORM ou banco. Elas recebem um
principal já autenticado, chamam um serviço público e projetam a
resposta por allowlist.

## Isolamento vem de baixo, não daqui

`ScheduleService.get_schedule` já levanta violação de escopo para
Schedule alheio, e `OrchestrationQueryService` já lê o Schedule **antes**
de listar qualquer coisa — sem isso, um `schedule_id` de outro principal
devolveria lista vazia e "vazio" seria indistinguível de "não é seu".

As tools herdam essa propriedade em vez de reimplementá-la. Uma
verificação de escopo duplicada aqui viraria uma segunda autoridade que
pode divergir da primeira.

```text
DUPLICATED_SCOPE_CHECK = SECOND_AUTHORITY_THAT_DRIFTS
```
"""

from dataclasses import dataclass
from typing import Any

from app.mcp import TOOL_NAMES
from app.mcp.auth import PrincipalAutenticado
from app.mcp.schemas import (
    ENTRADAS,
    SCHEMA_VERSION,
    AttemptsListInput,
    GovernanceReadInput,
    HandoffExportInput,
    ReturnImportInput,
    ScheduleReadInput,
    projetar_governanca,
    projetar_schedule,
    projetar_tentativa,
)


class ToolDesconhecidaError(Exception):
    """Nome fora das cinco. Recusa, nunca despacho dinâmico."""


@dataclass(frozen=True)
class ServicosCompostos:
    """As fachadas públicas que as tools compõem. Nada além delas."""

    schedules: Any
    consultas: Any
    handoff_supervisionado: Any
    retorno: Any


class McpTools:
    """Despacho fechado sobre as cinco autorizadas."""

    def __init__(self, servicos: ServicosCompostos) -> None:
        self._s = servicos

    def nomes(self) -> tuple[str, ...]:
        """Exatamente as cinco, na ordem canônica."""
        return TOOL_NAMES

    def chamar(
        self, *, nome: str, argumentos: dict[str, Any], principal: PrincipalAutenticado
    ) -> dict[str, Any]:
        """Valida a entrada no schema fechado e despacha.

        O despacho é por `if` explícito, não por `getattr(self, nome)`:
        resolução dinâmica de nome transforma a superfície fechada num
        alcance a qualquer método do objeto.

            GETATTR_DISPATCH = OPEN_SURFACE_WEARING_A_CLOSED_NAME
        """
        if nome not in TOOL_NAMES:
            raise ToolDesconhecidaError(f"tool não autorizada: {nome}")

        modelo = ENTRADAS[nome]
        entrada = modelo.model_validate(argumentos)
        ref = principal.principal_ref

        if nome == "schedule.read":
            assert isinstance(entrada, ScheduleReadInput)
            return projetar_schedule(
                self._s.schedules.get_schedule(
                    control_principal_ref=ref, schedule_id=entrada.schedule_id
                )
            )

        if nome == "attempts.list":
            assert isinstance(entrada, AttemptsListInput)
            tentativas = self._s.consultas.list_attempts(
                control_principal_ref=ref, schedule_id=entrada.schedule_id
            )
            return {
                "schedule_id": str(entrada.schedule_id),
                "attempts": [projetar_tentativa(t) for t in tentativas],
                "schema_version": SCHEMA_VERSION,
            }

        if nome == "governance.read":
            assert isinstance(entrada, GovernanceReadInput)
            return projetar_governanca(
                self._s.consultas.read_governance(
                    control_principal_ref=ref, schedule_id=entrada.schedule_id
                )
            )

        if nome == "handoff.export":
            assert isinstance(entrada, HandoffExportInput)
            resultado = self._s.handoff_supervisionado.exportar(
                control_principal_ref=ref,
                schedule_id=entrada.schedule_id,
                step_id=entrada.step_id,
                command_key=entrada.command_key,
                request_sha256=entrada.request_sha256,
            )
            return {
                "attempt_id": str(resultado.attempt_id),
                "handoff_mode": resultado.handoff_mode.value,
                "replayed": resultado.replayed,
                "schema_version": SCHEMA_VERSION,
            }

        assert isinstance(entrada, ReturnImportInput)
        veredito = self._s.retorno.importar(
            control_principal_ref=ref,
            schedule_id=entrada.schedule_id,
            attempt_id=entrada.attempt_id,
            payload=entrada.payload,
        )
        # Retorno da IA é dado NÃO CONFIÁVEL e transitório: sai o veredito,
        # nunca o conteúdo. Rejeitado continua resultado persistido, não
        # comando — o veredito é registrado, o payload não vira instrução.
        #
        #     REJECTED_RETURN = PERSISTED_RESULT · NEVER_A_COMMAND
        return {
            "attempt_id": str(entrada.attempt_id),
            "accepted": bool(veredito.accepted),
            "reason_code": veredito.reason_code,
            "schema_version": SCHEMA_VERSION,
        }
