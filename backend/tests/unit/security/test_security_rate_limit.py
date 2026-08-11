import time

from app.security.rate_limit import InMemoryRateLimiter, RateLimiter


def test_in_memory_rate_limiter_satisfies_protocol():
    limiter = InMemoryRateLimiter(max_requests=5, window_seconds=60)
    assert isinstance(limiter, RateLimiter)


def test_allows_requests_under_the_limit():
    limiter = InMemoryRateLimiter(max_requests=3, window_seconds=60)
    assert limiter.is_allowed("client-a") is True
    assert limiter.is_allowed("client-a") is True
    assert limiter.is_allowed("client-a") is True


def test_blocks_requests_over_the_limit():
    limiter = InMemoryRateLimiter(max_requests=2, window_seconds=60)
    assert limiter.is_allowed("client-b") is True
    assert limiter.is_allowed("client-b") is True
    assert limiter.is_allowed("client-b") is False


def test_different_keys_have_independent_limits():
    limiter = InMemoryRateLimiter(max_requests=1, window_seconds=60)
    assert limiter.is_allowed("client-x") is True
    assert limiter.is_allowed("client-y") is True  # não afetado por client-x
    assert limiter.is_allowed("client-x") is False


def test_allows_again_after_window_expires():
    limiter = InMemoryRateLimiter(max_requests=1, window_seconds=0.05)
    assert limiter.is_allowed("client-z") is True
    assert limiter.is_allowed("client-z") is False
    time.sleep(0.1)
    assert limiter.is_allowed("client-z") is True
