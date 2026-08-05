import json
import logging

from app.logging.formatters import JsonFormatter, TextFormatter


def _make_record(msg: str = "hello", **extra) -> logging.LogRecord:
    record = logging.LogRecord("app.test", logging.INFO, __file__, 10, msg, (), None)
    record.funcName = "some_function"
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_json_formatter_produces_valid_json_with_base_fields():
    record = _make_record()
    output = JsonFormatter().format(record)
    payload = json.loads(output)

    assert payload["level"] == "INFO"
    assert payload["logger"] == "app.test"
    assert payload["message"] == "hello"
    assert payload["function"] == "some_function"
    assert "timestamp" in payload


def test_json_formatter_includes_extra_fields():
    record = _make_record(request_id="req-1", duration_ms=12.3)
    payload = json.loads(JsonFormatter().format(record))
    assert payload["request_id"] == "req-1"
    assert payload["duration_ms"] == 12.3


def test_json_formatter_omits_fields_that_were_never_set():
    record = _make_record()
    payload = json.loads(JsonFormatter().format(record))
    assert "session_id" not in payload


def test_json_formatter_includes_exception_when_present():
    try:
        raise ValueError("boom")
    except ValueError:
        import sys

        record = _make_record()
        record.exc_info = sys.exc_info()
    payload = json.loads(JsonFormatter().format(record))
    assert "exception" in payload
    assert "boom" in payload["exception"]


def test_json_formatter_handles_non_serializable_extra_values():
    class _Weird:
        def __str__(self) -> str:
            return "weird-repr"

    record = _make_record(odd=_Weird())
    payload = json.loads(JsonFormatter().format(record))
    assert payload["odd"] == "weird-repr"


def test_text_formatter_includes_level_logger_and_message():
    record = _make_record()
    output = TextFormatter().format(record)
    assert "INFO" in output
    assert "app.test" in output
    assert "hello" in output


def test_text_formatter_includes_structured_fields_in_brackets():
    record = _make_record(request_id="req-1", duration_ms=5.0)
    output = TextFormatter().format(record)
    assert "request_id=req-1" in output
    assert "duration_ms=5.0" in output
    assert "[" in output and "]" in output


def test_text_formatter_omits_bracket_section_when_no_extra_fields():
    record = _make_record()
    output = TextFormatter().format(record)
    assert "[" not in output
