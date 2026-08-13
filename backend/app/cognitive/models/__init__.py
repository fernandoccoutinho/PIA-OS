"""
Modelos ORM da Biblioteca Cognitiva.

Importar este pacote registra suas tabelas em `app.database.base.Base`
— necessário para que `alembic revision --autogenerate` as veja (ver
`alembic/env.py`).
"""

from app.cognitive.models.cognitive_object import CognitiveObject
from app.cognitive.models.enums import AccessibilityState

__all__ = ["AccessibilityState", "CognitiveObject"]
