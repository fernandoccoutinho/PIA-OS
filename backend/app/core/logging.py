"""
Bootstrap de logging do PIA-OS — ponto de composição, não biblioteca.

Diferença de `app/logging/`: aquele pacote é infraestrutura genérica e
reutilizável (poderia, em tese, ser extraído para outro projeto). Este
módulo é a "cola" específica do PIA-OS que decide *quando* e *com que
configuração* o logging é inicializado — chamado uma única vez, no
startup da aplicação (`app.core.lifespan`).
"""

from app.config.settings import Settings, settings
from app.logging import events
from app.logging.config import configure_logging
from app.logging.logger import get_logger

_logger = get_logger("app.core.logging")


def setup_logging(config: Settings = settings) -> None:
    """Configura o logger raiz a partir da configuração central (2.2) e
    registra o evento `configuration_loaded`. Chamar uma única vez, no
    startup — chamadas repetidas reconfiguram o logger raiz do zero
    (idempotente, mas descarta handlers customizados adicionados fora
    deste fluxo)."""
    configure_logging(config)
    events.log_event(
        _logger,
        events.CONFIGURATION_LOADED,
        log_level=config.log_level,
        log_format=config.log_format,
        log_destinations=config.log_destinations,
    )
