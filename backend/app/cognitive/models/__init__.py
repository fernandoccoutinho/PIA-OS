"""
Modelos ORM da Biblioteca Cognitiva.

Importar este pacote registra suas tabelas em `app.database.base.Base`
— necessário para que `alembic revision --autogenerate` as veja (ver
`alembic/env.py`).
"""

from app.cognitive.models.cognitive_object import CognitiveObject
from app.cognitive.models.enums import (
    AccessibilityState,
    LineageRelation,
    ProvenanceActorType,
    ProvenanceSourceType,
    RelationshipType,
    RevisionStatus,
    TransformationKind,
)
from app.cognitive.models.lineage_edge import LineageEdge
from app.cognitive.models.provenance_record import ProvenanceRecord
from app.cognitive.models.relationship import Relationship
from app.cognitive.models.transformation_record import TransformationRecord

__all__ = [
    "AccessibilityState",
    "CognitiveObject",
    "LineageEdge",
    "LineageRelation",
    "ProvenanceActorType",
    "ProvenanceRecord",
    "ProvenanceSourceType",
    "Relationship",
    "RelationshipType",
    "RevisionStatus",
    "TransformationKind",
    "TransformationRecord",
]
