"""
Contexto de logging — transporta identificadores entre chamadas sem
depender de regra de negócio nem de passagem manual de parâmetros.

Baseado em `contextvars` (não thread-locals): funciona corretamente com
código assíncrono (cada task asyncio tem sua própria cópia), o que
`threading.local` não garante. O valor setado no início de uma
requisição fica visível a qualquer `get_logger(...)` chamado durante o
processamento dela — inclusive em código de camadas mais profundas
(repositório, ORM) que nunca recebem `request_id` como parâmetro.
"""

from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass, fields

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
_correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)
_trace_id: ContextVar[str | None] = ContextVar("trace_id", default=None)
_session_id: ContextVar[str | None] = ContextVar("session_id", default=None)
_user_id: ContextVar[str | None] = ContextVar("user_id", default=None)

_ALL_VARS: dict[str, ContextVar[str | None]] = {
    "request_id": _request_id,
    "correlation_id": _correlation_id,
    "trace_id": _trace_id,
    "session_id": _session_id,
    "user_id": _user_id,
}


@dataclass(frozen=True)
class ContextSnapshot:
    """Valores de contexto no momento da leitura — só os campos setados."""

    request_id: str | None = None
    correlation_id: str | None = None
    trace_id: str | None = None
    session_id: str | None = None
    user_id: str | None = None

    def as_dict(self) -> dict[str, str]:
        """Apenas os campos não-nulos — campos ausentes ficam de fora do
        payload de log (campos inexistentes permanecem opcionais), em vez
        de aparecerem como `null`."""
        return {f.name: v for f in fields(self) if (v := getattr(self, f.name)) is not None}


class LoggingContext:
    """API estática para ler/escrever o contexto de logging atual."""

    @staticmethod
    def set(
        *,
        request_id: str | None = None,
        correlation_id: str | None = None,
        trace_id: str | None = None,
        session_id: str | None = None,
        user_id: str | None = None,
    ) -> dict[str, Token[str | None]]:
        """Define os valores informados (ignora os que ficarem `None`).
        Retorna os tokens necessários para `reset()` — sempre reverta o
        contexto ao sair do escopo (ver `logging_context`)."""
        tokens: dict[str, Token[str | None]] = {}
        values = {
            "request_id": request_id,
            "correlation_id": correlation_id,
            "trace_id": trace_id,
            "session_id": session_id,
            "user_id": user_id,
        }
        for name, value in values.items():
            if value is not None:
                tokens[name] = _ALL_VARS[name].set(value)
        return tokens

    @staticmethod
    def reset(tokens: dict[str, Token[str | None]]) -> None:
        for name, token in tokens.items():
            _ALL_VARS[name].reset(token)

    @staticmethod
    def get() -> ContextSnapshot:
        return ContextSnapshot(
            request_id=_request_id.get(),
            correlation_id=_correlation_id.get(),
            trace_id=_trace_id.get(),
            session_id=_session_id.get(),
            user_id=_user_id.get(),
        )

    @staticmethod
    def clear() -> None:
        """Reseta todas as variáveis para `None` — uso típico em testes."""
        for var in _ALL_VARS.values():
            var.set(None)


@contextmanager
def logging_context(
    *,
    request_id: str | None = None,
    correlation_id: str | None = None,
    trace_id: str | None = None,
    session_id: str | None = None,
    user_id: str | None = None,
) -> Generator[ContextSnapshot, None, None]:
    """Context manager: define o contexto, garante reversão ao sair.

    with logging_context(request_id="abc"):
        logger.info("algo aconteceu")  # inclui request_id automaticamente
    """
    tokens = LoggingContext.set(
        request_id=request_id,
        correlation_id=correlation_id,
        trace_id=trace_id,
        session_id=session_id,
        user_id=user_id,
    )
    try:
        yield LoggingContext.get()
    finally:
        LoggingContext.reset(tokens)
