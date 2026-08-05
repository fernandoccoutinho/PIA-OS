from app.logging.context import ContextSnapshot, LoggingContext, logging_context


def teardown_function() -> None:
    LoggingContext.clear()


def test_get_returns_all_none_when_nothing_set():
    snapshot = LoggingContext.get()
    assert snapshot == ContextSnapshot()
    assert snapshot.as_dict() == {}


def test_set_and_get_roundtrip():
    tokens = LoggingContext.set(request_id="req-1", correlation_id="corr-1")
    try:
        snapshot = LoggingContext.get()
        assert snapshot.request_id == "req-1"
        assert snapshot.correlation_id == "corr-1"
        assert snapshot.trace_id is None
    finally:
        LoggingContext.reset(tokens)


def test_reset_restores_previous_value():
    tokens = LoggingContext.set(request_id="req-1")
    LoggingContext.reset(tokens)
    assert LoggingContext.get().request_id is None


def test_as_dict_omits_none_fields():
    snapshot = ContextSnapshot(request_id="req-1")
    assert snapshot.as_dict() == {"request_id": "req-1"}


def test_logging_context_manager_sets_and_reverts():
    assert LoggingContext.get().request_id is None
    with logging_context(request_id="req-2") as snapshot:
        assert snapshot.request_id == "req-2"
        assert LoggingContext.get().request_id == "req-2"
    assert LoggingContext.get().request_id is None


def test_logging_context_manager_reverts_even_on_exception():
    class _Boom(Exception):
        pass

    try:
        with logging_context(request_id="req-3"):
            raise _Boom
    except _Boom:
        pass
    assert LoggingContext.get().request_id is None


def test_nested_logging_context():
    with logging_context(request_id="outer"):
        assert LoggingContext.get().request_id == "outer"
        with logging_context(request_id="inner"):
            assert LoggingContext.get().request_id == "inner"
        assert LoggingContext.get().request_id == "outer"


def test_clear_resets_everything():
    LoggingContext.set(request_id="x", correlation_id="y", trace_id="z", session_id="w")
    LoggingContext.clear()
    assert LoggingContext.get() == ContextSnapshot()
