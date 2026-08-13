"""
Testes diretos dos listeners de evento do engine.

São funções puras de logging — chamáveis diretamente com argumentos
simulados, sem precisar de uma conexão real do PostgreSQL (que não está
disponível neste ambiente de sandbox/CI).
"""

import logging
import time
from types import SimpleNamespace

from app.database.engine import (
    _after_cursor_execute,
    _before_cursor_execute,
    _on_checkin,
    _on_close,
    _on_connect,
    _on_handle_error,
)


def test_on_connect_logs(caplog):
    with caplog.at_level(logging.INFO, logger="app.database"):
        _on_connect(None, None)
    assert any(r.getMessage() == "database_connection_opened" for r in caplog.records)


def test_on_checkin_logs(caplog):
    with caplog.at_level(logging.DEBUG, logger="app.database"):
        _on_checkin(None, None)
    assert any(r.getMessage() == "database_connection_returned_to_pool" for r in caplog.records)


def test_on_close_logs(caplog):
    with caplog.at_level(logging.INFO, logger="app.database"):
        _on_close(None, None)
    assert any(r.getMessage() == "database_connection_closed" for r in caplog.records)


def test_before_and_after_cursor_execute_logs_fast_query(caplog):
    context = SimpleNamespace()
    with caplog.at_level(logging.DEBUG, logger="app.database"):
        _before_cursor_execute(None, None, "SELECT 1", (), context, False)
        assert hasattr(context, "_pia_os_query_start_time")
        _after_cursor_execute(None, None, "SELECT 1", (), context, False)

    record = next(r for r in caplog.records if r.getMessage() == "database_query_executed")
    assert record.statement_kind == "SELECT"


def test_after_cursor_execute_without_start_time_does_nothing(caplog):
    context = SimpleNamespace()  # sem _pia_os_query_start_time
    with caplog.at_level(logging.DEBUG, logger="app.database"):
        _after_cursor_execute(None, None, "SELECT 1", (), context, False)
    assert not any(r.getMessage() == "database_query_executed" for r in caplog.records)


def test_after_cursor_execute_logs_slow_query_as_warning(caplog, monkeypatch):
    import app.database.engine as engine_module

    context = SimpleNamespace(_pia_os_query_start_time=0.0)
    # Força um tempo decorrido grande sem precisar de um sleep real.
    monkeypatch.setattr(
        engine_module.time, "perf_counter", lambda: 1.0
    )  # 1000ms decorridos desde 0.0

    with caplog.at_level(logging.DEBUG, logger="app.database"):
        _after_cursor_execute(None, None, "UPDATE x SET y=1", (), context, False)

    record = next(r for r in caplog.records if r.getMessage() == "database_slow_query")
    assert record.levelname == "WARNING"
    assert record.statement_kind == "UPDATE"


def test_after_cursor_execute_with_empty_statement(caplog):
    context = SimpleNamespace(_pia_os_query_start_time=time.perf_counter())
    with caplog.at_level(logging.DEBUG, logger="app.database"):
        _after_cursor_execute(None, None, "   ", (), context, False)
    record = next(r for r in caplog.records if r.getMessage() == "database_query_executed")
    assert record.statement_kind == ""


def test_on_handle_error_logs_exception_type(caplog):
    exception_context = SimpleNamespace(original_exception=ValueError("boom"))
    with caplog.at_level(logging.ERROR, logger="app.database"):
        _on_handle_error(exception_context)
    record = next(r for r in caplog.records if r.getMessage() == "database_error")
    assert record.error_type == "ValueError"
