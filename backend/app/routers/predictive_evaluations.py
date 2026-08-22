"""
`POST /api/v1/predictive-evaluations` — primeiro endpoint de negócio (E6.2).

```text
ROUTE_AND_AUTH_SAME_COMMIT = TRUE
MODE = EVALUATE_AND_ROUTE_ONLY
BUSINESS_ROUTE_WITHOUT_FAIL_CLOSED_AUTH = UNIMPORTABLE
```

O handler não contém ciência: recebe o DTO público, delega ao serviço de
aplicação e devolve o envelope. Toda a decisão científica pertence à E5.

A guarda `_assert_every_route_is_protected()` roda no import do módulo.
Remover a dependency de acesso não produz um endpoint aberto — produz um
`ImportError` que derruba a aplicação inteira. Uma guarda que só reprova
em teste ainda permite que a versão insegura exista e rode.
"""

import inspect
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.api.dependencies import require_predictive_evaluate_access
from app.api.responses import SuccessResponse
from app.docs.responses import (
    response_401,
    response_403,
    response_422,
    response_500,
)
from app.docs.tags import TAG_PREDICTIVE_EVALUATIONS
from app.schemas import predictive_evaluation as dto
from app.schemas.error import ErrorResponse
from app.security.programmatic_access import ProgrammaticPrincipal
from app.services.predictive_evaluation_service import evaluate_and_route

router = APIRouter(tags=[TAG_PREDICTIVE_EVALUATIONS.name])

GuardedPrincipal = Annotated[ProgrammaticPrincipal, Depends(require_predictive_evaluate_access)]
"""Único portão da rota: autenticação, escopo e cota compostos.

`Annotated` em vez de default de chamada: o idioma removeu as supressões
`B008` do delta e mantém a dependency verificável por identidade de
objeto, que é o que `_assert_every_route_is_protected` exige.
"""

_RESPONSE_429: dict[int | str, dict[str, object]] = {
    429: {
        "model": ErrorResponse,
        "description": "Cota do principal técnico esgotada nesta janela (PIA-1008).",
    }
}

_RESPONSE_503: dict[int | str, dict[str, object]] = {
    503: {
        "model": ErrorResponse,
        "description": (
            "Autoridade de cota indisponível (PIA-3002). A chamada é recusada sem "
            "avaliar; não é cota excedida e o cliente não a resolve esperando a "
            "janela virar."
        ),
    }
}


@router.post(
    "/predictive-evaluations",
    response_model=SuccessResponse[dto.PublicEvaluationResponse],
    summary="Avaliar e rotear um lote preditivo governado",
    description=(
        "Executa a avaliação científica e o roteamento governado de um lote, "
        "sem promover, reconfigurar, escolher provedor ou executar ação externa. "
        "Exige credencial de serviço `Bearer pia_<key_id>.<secret>` com o escopo "
        "`predictive:evaluate`. A credencial de serviço não representa usuário "
        "humano e nunca satisfaz aprovação PIAP."
    ),
    responses={
        **response_401("Credencial de serviço ausente ou inválida (PIA-7001)."),
        **response_403("Principal sem o escopo `predictive:evaluate` (PIA-7002)."),
        **response_422("Contrato público inválido (PIA-2001)."),
        **_RESPONSE_429,
        **_RESPONSE_503,
        **response_500(),
    },
)
def create_predictive_evaluation(
    request: Request,
    payload: dto.PublicEvaluationRequest,
    principal: GuardedPrincipal,
) -> SuccessResponse[dto.PublicEvaluationResponse]:
    """Avalia e roteia. Não promove, não reconfigura, não executa fora."""
    resposta = evaluate_and_route(payload)
    return SuccessResponse[dto.PublicEvaluationResponse](data=resposta)


def _dependency_callables(endpoint: object) -> set[object]:
    """Dependencies declaradas pelo endpoint, por objeto — nunca por nome.

    Cobre as duas formas: `Annotated[T, Depends(f)]` (a usada aqui, que
    dispensa `# noqa: B008`) e o default de chamada legado. Comparar por
    identidade impede que uma função homônima satisfaça a guarda.
    """
    encontrados: set[object] = set()
    for parametro in inspect.signature(endpoint).parameters.values():  # type: ignore[arg-type]
        alvo = getattr(parametro.default, "dependency", None)
        if alvo is not None:
            encontrados.add(alvo)
        for metadado in getattr(parametro.annotation, "__metadata__", ()):
            alvo = getattr(metadado, "dependency", None)
            if alvo is not None:
                encontrados.add(alvo)
    return encontrados


def _assert_every_route_is_protected() -> None:
    """Nenhuma rota deste módulo é registrável sem auth + escopo + cota.

    A verificação roda no IMPORT: remover a dependency não produz um
    endpoint aberto, produz um `ImportError` que derruba a aplicação.

    ```text
    BUSINESS_ROUTE_WITHOUT_FAIL_CLOSED_AUTH = UNIMPORTABLE
    ```
    """
    for rota in router.routes:
        endpoint = getattr(rota, "endpoint", None)
        if endpoint is None:  # pragma: no cover - APIRouter só guarda APIRoute
            continue
        if require_predictive_evaluate_access not in _dependency_callables(endpoint):
            raise ImportError(
                f"rota de negócio '{getattr(rota, 'path', endpoint)}' sem "
                "require_predictive_evaluate_access: "
                "BUSINESS_ROUTE_WITHOUT_FAIL_CLOSED_AUTH = FORBIDDEN"
            )


_assert_every_route_is_protected()
