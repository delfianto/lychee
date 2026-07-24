"""TokenBucket rate limiter (fake clock — no real sleeping)."""

import pytest
from src.providers.ratelimit import TokenBucket


def test_burst_up_to_capacity_is_free_then_throttles() -> None:
    now = [0.0]
    bucket = TokenBucket(rate=5.0, capacity=5.0, monotonic=lambda: now[0])

    assert [bucket.take() for _ in range(5)] == [0.0] * 5  # capacity absorbs the burst
    assert bucket.take() == pytest.approx(0.2)  # 6th must wait 1/5s for a refill


def test_refills_over_time() -> None:
    now = [0.0]
    bucket = TokenBucket(rate=5.0, capacity=5.0, monotonic=lambda: now[0])
    for _ in range(5):
        _ = bucket.take()

    now[0] = 1.0  # one second → five tokens back
    assert bucket.take() == 0.0


def test_rate_must_be_positive() -> None:
    with pytest.raises(ValueError):
        _ = TokenBucket(rate=0)
