"""Persistência append-only e concorrente dos eventos de E5.l."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.predictive_accessibility.errors.exceptions import (
    PredictiveReconfigurationEventIdentityMismatchError,
    PredictiveReconfigurationEventImmutableError,
)
from app.predictive_accessibility.reconfiguration import (
    PredictiveReconfigurationAppendResult,
    PredictiveReconfigurationDecision,
    PredictiveReconfigurationEvent,
)

_IDENTITY_CONSTRAINT = "predictive_reconfiguration_events_pkey"
_VERSION_CONSTRAINT = "uq_predictive_reconfiguration_subject_version"
_CANONICAL_FIELDS = (
    "subject_key",
    "event_kind",
    "from_version",
    "to_version",
    "active_candidate_ref",
    "candidate_payload_sha256",
    "model_ref",
    "hypothesis_refs",
    "validation_ref",
    "cost_ref",
    "responsible_ref",
    "rollback_plan_ref",
    "approval_reference",
    "approval_version",
    "approval_scope",
    "approval_jurisdiction",
    "approval_bound_kind",
    "approval_bound_ref",
    "rollback_of_event_id",
    "recorded_at",
)


def _constraint_name(error: IntegrityError) -> str | None:
    original = getattr(error, "orig", None)
    if getattr(original, "sqlstate", None) != "23505":
        return None
    return getattr(getattr(original, "diag", None), "constraint_name", None)


class PredictiveReconfigurationRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, event_id: uuid.UUID) -> PredictiveReconfigurationEvent | None:
        if not isinstance(event_id, uuid.UUID):
            raise TypeError("event_id deve ser UUID")
        return self._session.get(PredictiveReconfigurationEvent, event_id)

    def current(self, subject_key: str) -> PredictiveReconfigurationEvent | None:
        command = (
            select(PredictiveReconfigurationEvent)
            .where(PredictiveReconfigurationEvent.subject_key == subject_key)
            .order_by(PredictiveReconfigurationEvent.to_version.desc())
            .limit(1)
        )
        return self._session.execute(command).scalar_one_or_none()

    def append(
        self, event: PredictiveReconfigurationEvent
    ) -> PredictiveReconfigurationAppendResult:
        if not isinstance(event, PredictiveReconfigurationEvent):
            raise TypeError("append exige PredictiveReconfigurationEvent")
        existing = self.get(event.event_id)
        if existing is not None:
            return PredictiveReconfigurationAppendResult(
                PredictiveReconfigurationDecision.REPLAYED,
                self._reconcile(existing, event),
            )
        try:
            with self._session.begin_nested():
                self._session.add(event)
                self._session.flush()
        except IntegrityError as exc:
            constraint = _constraint_name(exc)
            if constraint == _IDENTITY_CONSTRAINT:
                concurrent = self.get(event.event_id)
                if concurrent is None:
                    raise
                return PredictiveReconfigurationAppendResult(
                    PredictiveReconfigurationDecision.REPLAYED,
                    self._reconcile(concurrent, event),
                )
            if constraint == _VERSION_CONSTRAINT:
                return PredictiveReconfigurationAppendResult(
                    PredictiveReconfigurationDecision.LOST_CONCURRENT_RACE,
                    self.current(event.subject_key),
                )
            raise
        return PredictiveReconfigurationAppendResult(
            PredictiveReconfigurationDecision.PROMOTED, event
        )

    @staticmethod
    def _reconcile(
        existing: PredictiveReconfigurationEvent,
        candidate: PredictiveReconfigurationEvent,
    ) -> PredictiveReconfigurationEvent:
        diverging = tuple(
            field
            for field in _CANONICAL_FIELDS
            if getattr(existing, field) != getattr(candidate, field)
        )
        if diverging:
            raise PredictiveReconfigurationEventIdentityMismatchError(candidate.event_id, diverging)
        return existing

    def update(self, event: PredictiveReconfigurationEvent) -> PredictiveReconfigurationEvent:
        raise PredictiveReconfigurationEventImmutableError("update")

    def delete(self, event: PredictiveReconfigurationEvent) -> None:
        raise PredictiveReconfigurationEventImmutableError("delete")
