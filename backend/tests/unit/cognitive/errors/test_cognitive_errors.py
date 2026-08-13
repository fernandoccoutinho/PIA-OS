"""Testes do catálogo de erros PIA-8xxx e das exceções de domínio."""

import uuid

from app.cognitive.errors.codes import (
    ALL_COGNITIVE_ERROR_CODES,
    COGNITIVE_ERROR_CODE_BY_CODE,
    PIA_8001_IDENTITY_IMMUTABLE,
    PIA_8002_CLID_ALREADY_SET,
)
from app.cognitive.errors.exceptions import (
    CognitiveObjectClidAlreadySetError,
    CognitiveObjectIdentityImmutableError,
)
from app.core.error_codes import ALL_ERROR_CODES, ErrorCategory
from app.exceptions.base import PIAOSException


def test_cognitive_error_codes_are_in_the_8xxx_range():
    for ec in ALL_COGNITIVE_ERROR_CODES:
        assert ec.code.startswith("PIA-8")


def test_cognitive_error_codes_do_not_collide_with_baseline_catalog():
    """Confirma que PIA-8xxx não foi incorporado a `ALL_ERROR_CODES` de
    E1/E2 — a decisão registrada foi Opção B (catálogo separado), não
    edição de `app/core/error_codes.py`."""
    baseline_codes = {ec.code for ec in ALL_ERROR_CODES}
    cognitive_codes = {ec.code for ec in ALL_COGNITIVE_ERROR_CODES}
    assert baseline_codes.isdisjoint(cognitive_codes)


def test_cognitive_error_code_by_code_lookup():
    assert COGNITIVE_ERROR_CODE_BY_CODE["PIA-8001"] is PIA_8001_IDENTITY_IMMUTABLE
    assert COGNITIVE_ERROR_CODE_BY_CODE["PIA-8002"] is PIA_8002_CLID_ALREADY_SET


def test_exceptions_are_piaos_exceptions():
    assert issubclass(CognitiveObjectIdentityImmutableError, PIAOSException)
    assert issubclass(CognitiveObjectClidAlreadySetError, PIAOSException)


def test_identity_immutable_error_carries_code_and_ids():
    old_id, new_id = uuid.uuid4(), uuid.uuid4()
    error = CognitiveObjectIdentityImmutableError(current_id=old_id, attempted_id=new_id)
    assert error.code == "PIA-8001"
    assert error.category == ErrorCategory.VALIDATION.value
    assert error.status_code == 409
    assert str(old_id) in error.message
    assert str(new_id) in error.message


def test_clid_already_set_error_carries_code_and_ids():
    coid, current, attempted = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    error = CognitiveObjectClidAlreadySetError(
        coid=coid, current_clid=current, attempted_clid=attempted
    )
    assert error.code == "PIA-8002"
    assert error.status_code == 409
