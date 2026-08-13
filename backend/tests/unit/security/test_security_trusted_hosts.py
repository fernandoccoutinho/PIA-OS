from starlette.requests import Request

from app.config.settings import Settings
from app.security.trusted_hosts import is_trusted_host


def _make_request(host: str | None) -> Request:
    headers = [(b"host", host.encode())] if host else []
    scope = {"type": "http", "method": "GET", "path": "/", "headers": headers}
    return Request(scope)


def test_wildcard_accepts_any_host():
    settings = Settings(trusted_hosts="*")
    assert is_trusted_host(_make_request("anything.example.com"), settings) is True


def test_explicit_list_accepts_matching_host():
    settings = Settings(trusted_hosts="api.pia-os.com,localhost")
    assert is_trusted_host(_make_request("localhost"), settings) is True


def test_explicit_list_rejects_unmatched_host():
    settings = Settings(trusted_hosts="api.pia-os.com")
    assert is_trusted_host(_make_request("evil.com"), settings) is False


def test_host_with_port_is_matched_without_port():
    settings = Settings(trusted_hosts="localhost")
    assert is_trusted_host(_make_request("localhost:8000"), settings) is True


def test_case_insensitive_match():
    settings = Settings(trusted_hosts="API.PIA-OS.com")
    assert is_trusted_host(_make_request("api.pia-os.com"), settings) is True


def test_missing_host_header_rejected_when_not_wildcard():
    settings = Settings(trusted_hosts="api.pia-os.com")
    assert is_trusted_host(_make_request(None), settings) is False
