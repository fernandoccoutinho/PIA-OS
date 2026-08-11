"""
Raiz da hierarquia oficial de exceções do PIA-OS.

Todo erro estruturado da plataforma herda de `PIAOSException`, direta ou
indiretamente. Nenhuma exceção desta hierarquia deve escapar sem
tratamento — o handler global (`app/exceptions/handlers.py`) captura
`PIAOSException` e converte para a resposta padronizada.
"""

from app.core.error_codes import PIA_0001_UNKNOWN_ERROR, ErrorCode


class PIAOSException(Exception):
    """Base de toda exceção estruturada do PIA-OS.

    Cada subclasse concreta define `error_code` como atributo de classe
    (um `ErrorCode` do catálogo oficial — `app/core/error_codes.py`).
    Uma instância pode sobrescrever `message`/`detail`/`error_code`
    pontualmente, sem precisar de uma nova subclasse para cada variação
    de mensagem.
    """

    error_code: ErrorCode = PIA_0001_UNKNOWN_ERROR

    def __init__(
        self,
        message: str | None = None,
        detail: object = None,
        error_code: ErrorCode | None = None,
    ) -> None:
        self.error_code = error_code or type(self).error_code
        self.message = message or self.error_code.default_message
        self.detail = detail
        super().__init__(self.message)

    @property
    def code(self) -> str:
        return self.error_code.code

    @property
    def category(self) -> str:
        return self.error_code.category.value

    @property
    def severity(self) -> str:
        return self.error_code.severity.value

    @property
    def status_code(self) -> int:
        return self.error_code.http_status
