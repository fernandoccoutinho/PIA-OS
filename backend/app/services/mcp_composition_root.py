"""
Composition root do runtime MCP (`E7.4-2`).

Mora em `app/services/`, e não em `app/mcp/`, pela mesma razão de
`human_protection_composition.py`: fiação precisa alcançar repositório e
sessão, e o boundary MCP não pode. A guarda `test_mcp03` mede essa
separação, e ela vale — um boundary que constrói o próprio repositório é
um boundary com acesso direto a persistência, por mais indireto que
pareça o caminho.

```text
WIRING_REACHES_PERSISTENCE · THE_BOUNDARY_MUST_NOT
COMPOSITION_ROOT != BOUNDARY_SURFACE
```

```text
REAL_SERVICES · NO_DOUBLES · NOT_MOUNTED_IN_PRODUCTION
```

Constrói o runtime completo com instâncias reais — `ScheduleService`,
`OrchestrationQueryService`, `CommandReceiptService`,
`ReturnValidationService`, a composição da E7.4-1 e o servidor MCP — e
**não** o monta no aplicativo principal.

A factory é chamada explicitamente. Nenhum módulo fora de `app/mcp` a
referencia, e a guarda `test_mcp10` mede isso.

```text
NO_MOUNT_POINT > FLAG_SET_TO_FALSE
```

## Sessão por chamada

Cada chamada MCP recebe a **sua** sessão e a sua transação. Sessão
compartilhada entre requisições faria o rollback de um G3 bloqueado
arrastar junto o trabalho de outra chamada em voo — e o
`CLAIM_BEFORE_ALLOWED_EFFECT` deixaria de valer por chamada para valer
por processo.

```text
ONE_CALL = ONE_SESSION = ONE_TRANSACTION
```

## Modo de exportação

O `CommandReceiptService` desta composição recebe o
`SupervisedAutomaticHandoffExportService` — nunca o manual. A composição
HTTP existente continua recebendo `ManualHandoffExportService`, e
nenhuma das duas conhece a outra: é para isso que
`ExportServicePort` existe.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.mcp import TOOL_NAMES
from app.mcp.auth import PrincipalAutenticado
from app.mcp.tools import McpToolsPort


@dataclass(frozen=True)
class RuntimeDependencies:
    """O que a factory precisa e não constrói sozinha."""

    session_factory: Callable[[], Any]
    protecao_factory: Callable[[Any], Any]
    objetivo_por_step: Callable[..., str]
    operacao: Any
    resource_config: Any
    jwks: Any
    principal_resolver: Any
    quota: Any


class TransactionalMcpTools:
    """Abre, confirma/reverte e fecha uma sessão em cada chamada MCP."""

    def __init__(self, deps: RuntimeDependencies) -> None:
        self._deps = deps

    def nomes(self) -> tuple[str, ...]:
        return TOOL_NAMES

    def chamar(
        self,
        *,
        nome: str,
        argumentos: dict[str, Any],
        principal: PrincipalAutenticado,
    ) -> dict[str, Any]:
        with self._deps.session_factory() as sessao:
            try:
                ferramentas: McpToolsPort = construir_servicos(sessao, self._deps)
                resposta = ferramentas.chamar(
                    nome=nome,
                    argumentos=argumentos,
                    principal=principal,
                )
                sessao.commit()
                return resposta
            except Exception:
                sessao.rollback()
                raise


def construir_servicos(sessao: Any, deps: RuntimeDependencies) -> Any:
    """Monta os serviços reais sobre uma sessão.

    Nenhum dublê entra aqui. Se um serviço não puder ser construído, a
    composição falha na construção — e não em runtime, dentro de uma
    chamada já autenticada.

    ```text
    FAIL_AT_WIRING > FAIL_MID_REQUEST
    ```
    """
    from app.mcp.adapters import ReturnImportAdapter, SupervisedHandoffAdapter
    from app.mcp.supervised_export_service import (
        SupervisedAutomaticHandoffExportService,
    )
    from app.mcp.tools import McpTools, ServicosCompostos
    from app.orchestration.repositories.orchestration_repository import (
        OrchestrationRepository,
    )
    from app.orchestration.services.command_receipt_service import CommandReceiptService
    from app.orchestration.services.handoff_service import HandoffService
    from app.orchestration.services.orchestration_query_service import (
        OrchestrationQueryService,
    )
    from app.orchestration.services.return_validation_service import (
        ReturnValidationService,
    )
    from app.orchestration.services.schedule_service import ScheduleService

    repositorio = OrchestrationRepository(sessao)
    agendas = ScheduleService(repositorio)
    handoff = HandoffService(repositorio)
    consultas = OrchestrationQueryService(repositorio)
    validacao = ReturnValidationService(repositorio)

    protecao = deps.protecao_factory(sessao)

    exportacao = SupervisedAutomaticHandoffExportService(
        repositorio,
        handoff,
        protecao=protecao,
        operacao=deps.operacao,
        objetivo_por_step=deps.objetivo_por_step,
    )

    recibos = CommandReceiptService(
        repositorio,
        agendas,
        handoff,
        export_service=exportacao,
        return_validation_service=validacao,
    )

    return McpTools(
        ServicosCompostos(
            schedules=agendas,
            consultas=consultas,
            handoff_supervisionado=SupervisedHandoffAdapter(
                recibos=recibos,
                protecao=protecao,
                operacao=deps.operacao,
                objetivo_por_step=deps.objetivo_por_step,
            ),
            retorno=ReturnImportAdapter(recibos=recibos),
        )
    )


def criar_runtime(deps: RuntimeDependencies) -> Any:
    """Constrói a aplicação ASGI completa, com serviços reais.

    NÃO monta nada no aplicativo principal. Chamar isto é um ato
    explícito de quem sobe o runtime em desenvolvimento ou teste.
    """
    from app.mcp.auth import ResourceServerAuthenticator
    from app.mcp.runtime import criar_app

    autenticador = ResourceServerAuthenticator(
        config=deps.resource_config,
        jwks=deps.jwks,
        resolver=deps.principal_resolver,
        quota=deps.quota,
    )

    return criar_app(
        tools=TransactionalMcpTools(deps),
        autenticador=autenticador,
        config=deps.resource_config,
    )
