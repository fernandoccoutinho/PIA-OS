import logging
import time

from app.logging.context import LoggingContext
from app.logging.filters import ContextFilter, DuplicateFilter, MinLevelFilter, SensitiveDataFilter


def _make_record(**extra) -> logging.LogRecord:
    record = logging.LogRecord("test", logging.INFO, __file__, 1, "msg", (), None)
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def teardown_function() -> None:
    LoggingContext.clear()


def test_context_filter_injects_set_fields():
    LoggingContext.set(request_id="req-1", correlation_id="corr-1")
    record = _make_record()
    assert ContextFilter().filter(record) is True
    assert record.request_id == "req-1"
    assert record.correlation_id == "corr-1"


def test_context_filter_does_not_inject_unset_fields():
    record = _make_record()
    ContextFilter().filter(record)
    assert not hasattr(record, "session_id")


def test_context_filter_never_overwrites_explicit_field():
    LoggingContext.set(request_id="from-context")
    record = _make_record(request_id="from-caller")
    ContextFilter().filter(record)
    assert record.request_id == "from-caller"


def test_sensitive_data_filter_redacts_known_keys():
    record = _make_record(password="hunter2", secret_key="abc123", safe_field="ok")
    assert SensitiveDataFilter().filter(record) is True
    assert record.password == SensitiveDataFilter.REDACTED_VALUE
    assert record.secret_key == SensitiveDataFilter.REDACTED_VALUE
    assert record.safe_field == "ok"


def test_sensitive_data_filter_accepts_custom_key_set():
    custom_filter = SensitiveDataFilter(sensitive_keys=frozenset({"my_secret"}))
    record = _make_record(my_secret="x", password="not-redacted-by-this-instance")
    custom_filter.filter(record)
    assert record.my_secret == SensitiveDataFilter.REDACTED_VALUE
    assert record.password == "not-redacted-by-this-instance"


def test_duplicate_filter_suppresses_immediate_repeat():
    dup_filter = DuplicateFilter(window_seconds=10)
    record1 = _make_record()
    record1.msg = "same message"
    record2 = _make_record()
    record2.msg = "same message"

    assert dup_filter.filter(record1) is True
    assert dup_filter.filter(record2) is False


def test_duplicate_filter_allows_after_window_expires():
    dup_filter = DuplicateFilter(window_seconds=0.05)
    record1 = _make_record()
    record1.msg = "same message"
    record2 = _make_record()
    record2.msg = "same message"

    assert dup_filter.filter(record1) is True
    time.sleep(0.1)
    assert dup_filter.filter(record2) is True


def test_duplicate_filter_allows_different_messages():
    dup_filter = DuplicateFilter(window_seconds=10)
    record1 = _make_record()
    record1.msg = "message A"
    record2 = _make_record()
    record2.msg = "message B"

    assert dup_filter.filter(record1) is True
    assert dup_filter.filter(record2) is True


def test_min_level_filter_blocks_below_threshold():
    level_filter = MinLevelFilter(logging.WARNING)
    info_record = _make_record()
    info_record.levelno = logging.INFO
    warning_record = _make_record()
    warning_record.levelno = logging.WARNING

    assert level_filter.filter(info_record) is False
    assert level_filter.filter(warning_record) is True
