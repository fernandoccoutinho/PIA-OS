import logging

from app.logging import events


def test_event_constants_are_snake_case_strings():
    for name in (
        events.APPLICATION_STARTED,
        events.APPLICATION_STOPPED,
        events.CONFIGURATION_LOADED,
        events.REQUEST_RECEIVED,
        events.REQUEST_COMPLETED,
        events.INTERNAL_ERROR,
        events.UNHANDLED_EXCEPTION,
        events.DATABASE_UNAVAILABLE,
        events.DATABASE_RECONNECTED,
    ):
        assert isinstance(name, str)
        assert name == name.lower()
        assert " " not in name


def test_log_event_includes_event_field_and_extra_fields(caplog):
    logger = logging.getLogger("test.events")
    with caplog.at_level(logging.INFO, logger="test.events"):
        events.log_event(logger, events.REQUEST_COMPLETED, status_code=200, duration_ms=1.5)

    record = caplog.records[0]
    assert record.event == events.REQUEST_COMPLETED
    assert record.status_code == 200
    assert record.duration_ms == 1.5
    assert record.getMessage() == events.REQUEST_COMPLETED


def test_log_event_respects_custom_level(caplog):
    logger = logging.getLogger("test.events.level")
    with caplog.at_level(logging.DEBUG, logger="test.events.level"):
        events.log_event(logger, events.DATABASE_UNAVAILABLE, level=logging.WARNING)
    assert caplog.records[0].levelno == logging.WARNING


def test_log_event_with_exc_info_attaches_exception(caplog):
    logger = logging.getLogger("test.events.exc")
    try:
        raise RuntimeError("falha simulada")
    except RuntimeError as exc:
        with caplog.at_level(logging.ERROR, logger="test.events.exc"):
            events.log_event(logger, events.UNHANDLED_EXCEPTION, level=logging.ERROR, exc_info=exc)

    record = caplog.records[0]
    assert record.exc_info is not None


def test_log_event_without_exc_info_has_no_exception_attached(caplog):
    logger = logging.getLogger("test.events.noexc")
    with caplog.at_level(logging.INFO, logger="test.events.noexc"):
        events.log_event(logger, events.CONFIGURATION_LOADED)
    assert caplog.records[0].exc_info is None
