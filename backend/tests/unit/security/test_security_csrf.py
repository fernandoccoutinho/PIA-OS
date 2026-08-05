from starlette.requests import Request

from app.security.csrf import DEFAULT_CSRF_POLICY, CSRFPolicy, requires_csrf_check


def _make_request(method: str) -> Request:
    scope = {"type": "http", "method": method, "path": "/x", "headers": []}
    return Request(scope)


def test_default_policy_is_disabled():
    assert DEFAULT_CSRF_POLICY.enabled is False


def test_requires_csrf_check_always_false_when_disabled():
    assert requires_csrf_check(_make_request("POST"), DEFAULT_CSRF_POLICY) is False
    assert requires_csrf_check(_make_request("GET"), DEFAULT_CSRF_POLICY) is False


def test_requires_csrf_check_true_for_unsafe_method_when_enabled():
    policy = CSRFPolicy(enabled=True)
    assert requires_csrf_check(_make_request("POST"), policy) is True
    assert requires_csrf_check(_make_request("DELETE"), policy) is True


def test_requires_csrf_check_false_for_safe_method_when_enabled():
    policy = CSRFPolicy(enabled=True)
    assert requires_csrf_check(_make_request("GET"), policy) is False
    assert requires_csrf_check(_make_request("HEAD"), policy) is False


def test_policy_field_defaults():
    policy = CSRFPolicy()
    assert policy.cookie_name == "pia_csrf_token"
    assert policy.header_name == "X-CSRF-Token"
