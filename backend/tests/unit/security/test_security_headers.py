from app.config.settings import Settings
from app.security.headers import build_security_headers


def test_default_headers_are_present():
    headers = build_security_headers(Settings(csp_policy=None))
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "DENY"
    assert headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert "Permissions-Policy" in headers
    assert headers["Cross-Origin-Resource-Policy"] == "same-origin"
    assert headers["Cross-Origin-Opener-Policy"] == "same-origin"


def test_csp_absent_by_default():
    headers = build_security_headers(Settings(csp_policy=None))
    assert "Content-Security-Policy" not in headers


def test_csp_included_when_configured():
    headers = build_security_headers(Settings(csp_policy="default-src 'self'"))
    assert headers["Content-Security-Policy"] == "default-src 'self'"
