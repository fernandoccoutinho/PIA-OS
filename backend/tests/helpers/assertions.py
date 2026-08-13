"""
Assertions reutilizáveis — comparação de respostas da API.

Centraliza a verificação do envelope de sucesso/erro (Módulos 2.5/2.7)
para não repetir a mesma sequência de `assert` em cada teste de endpoint.
"""

from typing import Any


def assert_error_envelope(
    body: dict[str, Any],
    *,
    status_code: int,
    code: str | None = None,
) -> None:
    """Verifica que `body` é um envelope de erro válido (Módulo 2.7):
    `success=false`, `error.status_code` bate, e opcionalmente
    `error.code` bate com o código do catálogo esperado."""
    assert body.get("success") is False, f"esperava success=false, veio {body.get('success')!r}"
    assert "error" in body, "resposta de erro sem a chave 'error'"
    error = body["error"]
    assert (
        error["status_code"] == status_code
    ), f"esperava status_code={status_code}, veio {error.get('status_code')!r}"
    if code is not None:
        assert error["code"] == code, f"esperava code={code!r}, veio {error.get('code')!r}"
    for required_field in ("message", "category", "severity", "path", "timestamp"):
        assert required_field in error, f"campo '{required_field}' ausente no envelope de erro"


def assert_has_standard_headers(headers: Any) -> None:
    """Verifica que a resposta traz os headers padrão de toda requisição
    (Módulos 2.6/2.8): request id, tempo de resposta, e os cabeçalhos de
    segurança estáticos."""
    for header_name in (
        "X-Request-ID",
        "X-Response-Time-Ms",
        "X-Content-Type-Options",
        "X-Frame-Options",
    ):
        assert header_name in headers, f"header '{header_name}' ausente na resposta"


def assert_valid_component_status(component: dict[str, Any]) -> None:
    """Verifica que um item de `StatusResponse.components` tem a forma
    esperada (`ComponentStatus` — Módulo 2.5)."""
    assert "name" in component
    assert "healthy" in component
    assert isinstance(component["healthy"], bool)
