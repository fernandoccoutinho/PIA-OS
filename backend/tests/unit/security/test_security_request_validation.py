from starlette.requests import Request

from app.config.settings import Settings
from app.security.request_validation import (
    validate_content_type,
    validate_request,
    validate_request_size,
)


def _make_request(
    method: str = "POST", content_length: str | None = None, content_type: str | None = None
) -> Request:
    headers = []
    if content_length is not None:
        headers.append((b"content-length", content_length.encode()))
    if content_type is not None:
        headers.append((b"content-type", content_type.encode()))
    scope = {"type": "http", "method": method, "path": "/x", "headers": headers}
    return Request(scope)


def test_request_within_size_limit_passes():
    settings = Settings(max_request_size_bytes=1000)
    assert validate_request_size(_make_request(content_length="500"), settings) is None


def test_request_over_size_limit_is_flagged():
    settings = Settings(max_request_size_bytes=1000)
    violation = validate_request_size(_make_request(content_length="5000"), settings)
    assert violation is not None
    assert violation.reason == "payload_too_large"
    assert violation.error_code.http_status == 413


def test_request_without_content_length_is_not_flagged():
    settings = Settings(max_request_size_bytes=1000)
    assert validate_request_size(_make_request(content_length=None), settings) is None


def test_invalid_content_length_header_is_ignored_not_crashed():
    settings = Settings(max_request_size_bytes=1000)
    assert validate_request_size(_make_request(content_length="not-a-number"), settings) is None


def test_allowed_content_type_passes():
    settings = Settings(allowed_content_types="application/json")
    request = _make_request(content_type="application/json")
    assert validate_content_type(request, settings) is None


def test_content_type_with_charset_suffix_is_matched_by_base_type():
    settings = Settings(allowed_content_types="application/json")
    request = _make_request(content_type="application/json; charset=utf-8")
    assert validate_content_type(request, settings) is None


def test_disallowed_content_type_is_flagged():
    settings = Settings(allowed_content_types="application/json")
    request = _make_request(content_type="text/xml")
    violation = validate_content_type(request, settings)
    assert violation is not None
    assert violation.reason == "unsupported_media_type"
    assert violation.error_code.http_status == 415


def test_get_requests_skip_content_type_validation():
    settings = Settings(allowed_content_types="application/json")
    request = _make_request(method="GET", content_type="text/xml")
    assert validate_content_type(request, settings) is None


def test_request_without_content_type_is_not_flagged():
    settings = Settings(allowed_content_types="application/json")
    request = _make_request(content_type=None)
    assert validate_content_type(request, settings) is None


def test_validate_request_combines_both_checks():
    settings = Settings(max_request_size_bytes=1000, allowed_content_types="application/json")
    ok_request = _make_request(content_length="10", content_type="application/json")
    assert validate_request(ok_request, settings) is None

    bad_request = _make_request(content_length="10", content_type="text/xml")
    assert validate_request(bad_request, settings) is not None
