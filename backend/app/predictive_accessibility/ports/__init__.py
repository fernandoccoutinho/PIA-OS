"""Portas estruturais da camada Predictive Accessibility (`E5.a`)."""

from app.predictive_accessibility.ports.governed_read import (
    GovernedReadPort,
    RetrievalResultView,
)

__all__ = [
    "GovernedReadPort",
    "RetrievalResultView",
]
