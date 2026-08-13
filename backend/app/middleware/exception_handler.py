"""
Compatibilidade com o Módulo 2.5.

A implementação canônica dos handlers globais agora vive em
`app.exceptions.handlers` + `app.exceptions.registry` (Módulo 2.7).
`register_exception_handlers` aqui é um reexport direto — `main.py`
continua chamando esta função sem qualquer alteração.
"""

from app.exceptions.handlers import register_exception_handlers

__all__ = ["register_exception_handlers"]
