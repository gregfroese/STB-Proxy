import time

from bff.security import LoginLimiter, valid_csrf


def test_valid_csrf_is_constant_time_match():
    assert valid_csrf("abc", "abc")
    assert not valid_csrf("abc", "abd")
    assert not valid_csrf("abc", None)
    assert not valid_csrf("", "")
    assert not valid_csrf("abc", "")


def test_limiter_starts_open_and_backs_off_after_failure():
    limiter = LoginLimiter(base=1.0, cap=60.0)
    assert limiter.retry_after("bob") == 0
    limiter.record_failure("bob")
    assert limiter.retry_after("bob") >= 1
    limiter.record_failure("bob")
    # Second failure doubles the wait.
    assert limiter.retry_after("bob") >= 2


def test_limiter_is_per_username():
    limiter = LoginLimiter(base=1.0, cap=60.0)
    limiter.record_failure("bob")
    assert limiter.retry_after("bob") >= 1
    assert limiter.retry_after("alice") == 0


def test_limiter_caps_and_clears_on_success():
    limiter = LoginLimiter(base=1.0, cap=4.0)
    for _ in range(20):
        limiter.record_failure("bob")
    assert limiter.retry_after("bob") <= 4
    limiter.record_success("bob")
    assert limiter.retry_after("bob") == 0
