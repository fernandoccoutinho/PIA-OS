"""
Logger Central — fábrica única de loggers da aplicação.

Proibido criar loggers isolados (`logging.getLogger(...)` direto) fora
deste módulo e de `app/logging/handlers.py` (que usa um logger stdlib
puro deliberadamente, para evitar dependência circular na própria
montagem do sistema de logging — ver docstring lá). Todo o resto do
código chama `get_logger(__name__)` daqui.
"""

import logging

__all__ = ["get_logger"]


def get_logger(name: str) -> logging.Logger:
    """Retorna um logger nomeado, herdando a configuração do logger raiz
    (formatters, handlers e filtros montados por `app.logging.config`)."""
    return logging.getLogger(name)
