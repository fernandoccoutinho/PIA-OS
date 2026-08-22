"""
Erros do `pia-os-sdk` — transporte, não decisão.

```text
CLIENT_TRANSLATES_STATUS = FALSE
CLIENT_RETRIES_AUTOMATICALLY = FALSE
CREDENTIAL_IN_ERROR = FORBIDDEN
```

O SDK preserva o que o servidor disse: status HTTP, código `PIA-####` e
detalhe público. Não converte `503` em `429`, não decide que `500` é
temporário, não tenta de novo. Traduzir status aqui criaria uma segunda
semântica de erro, e um cliente que reinterpreta o servidor mente para
quem o usa.

`RETRY != DUPLICATE_EFFECT`: repetir uma avaliação é decisão de quem
chama, com conhecimento do efeito pretendido, fora do SDK.
"""

from __future__ import annotations

from typing import Any

__all__ = ["PiaApiError", "PiaSdkError", "PiaTransportError"]


class PiaSdkError(Exception):
    """Raiz de todo erro do SDK."""


class PiaTransportError(PiaSdkError):
    """Falha antes de existir resposta HTTP: DNS, conexão, timeout.

    Separada de `PiaApiError` de propósito: não há status nem código PIA
    para preservar, e fingir um seria inventar uma decisão do servidor que
    nunca aconteceu.
    """


class PiaApiError(PiaSdkError):
    """Resposta de erro do servidor, preservada sem reinterpretação."""

    def __init__(
        self,
        *,
        status_code: int,
        code: str | None = None,
        message: str | None = None,
        detail: Any = None,
        request_id: str | None = None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.detail = detail
        self.request_id = request_id
        super().__init__(self._resumo())

    def _resumo(self) -> str:
        partes = [f"HTTP {self.status_code}"]
        if self.code:
            partes.append(self.code)
        if self.message:
            partes.append(str(self.message))
        return " | ".join(partes)

    def __repr__(self) -> str:
        return (
            f"PiaApiError(status_code={self.status_code!r}, code={self.code!r}, "
            f"message={self.message!r})"
        )

    @classmethod
    def from_response(cls, status_code: int, corpo: object) -> PiaApiError:
        """Extrai o envelope de erro do servidor sem exigir que ele exista.

        Um corpo que não seja o envelope esperado (proxy, gateway, HTML)
        não pode virar exceção do SDK: `detail` guarda o que veio e o
        chamador decide.
        """
        if isinstance(corpo, dict):
            erro = corpo.get("error")
            if isinstance(erro, dict):
                return cls(
                    status_code=status_code,
                    code=erro.get("code"),
                    message=erro.get("message"),
                    detail=erro.get("detail"),
                    request_id=corpo.get("request_id"),
                )
        return cls(status_code=status_code, detail=corpo)
