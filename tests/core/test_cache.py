"""app/core/cache.py의 namespace별 TTLCache 래퍼(cached_call) 회귀 테스트.

실제 cachetools.TTLCache를 그대로 사용하되, settings.silver_fallback_cache_ttl_seconds를
monkeypatch로 짧게 줄여 TTL 만료 동작까지 검증한다. 각 테스트는 끝에 cache.clear()로 전역
캐시 상태를 정리해 테스트 간 오염을 막는다.
"""

from __future__ import annotations

import time

import pytest

from app.core import cache

NAMESPACE = "test:namespace"


@pytest.fixture(autouse=True)
def _clear_cache_before_and_after():
    cache.clear()
    yield
    cache.clear()


def test_cached_call_computes_once_and_reuses_cached_value():
    calls = []

    def compute():
        calls.append(1)
        return "value"

    first = cache.cached_call(NAMESPACE, ("k",), compute)
    second = cache.cached_call(NAMESPACE, ("k",), compute)

    assert first == "value"
    assert second == "value"
    assert len(calls) == 1  # 두 번째 호출은 캐시 히트라 compute()가 다시 실행되지 않는다.


def test_cached_call_caches_none_result_too():
    calls = []

    def compute():
        calls.append(1)
        return None

    assert cache.cached_call(NAMESPACE, ("miss",), compute) is None
    assert cache.cached_call(NAMESPACE, ("miss",), compute) is None
    assert len(calls) == 1  # None(실버에도 이력 없음)도 캐싱되어 재계산되지 않는다.


def test_cached_call_different_keys_are_independent():
    calls = []

    def compute():
        calls.append(1)
        return len(calls)

    result_a = cache.cached_call(NAMESPACE, ("a",), compute)
    result_b = cache.cached_call(NAMESPACE, ("b",), compute)

    assert result_a == 1
    assert result_b == 2
    assert len(calls) == 2


def test_cached_call_different_namespaces_are_independent():
    def compute_a():
        return "from-a"

    def compute_b():
        return "from-b"

    assert cache.cached_call("ns-a", ("k",), compute_a) == "from-a"
    assert cache.cached_call("ns-b", ("k",), compute_b) == "from-b"


def test_cached_call_respects_ttl_expiry(monkeypatch):
    monkeypatch.setattr(cache.settings, "silver_fallback_cache_ttl_seconds", 0.05)
    cache.clear()  # maxsize/ttl은 캐시 생성 시점에 고정되므로, 변경 후 재생성되도록 초기화한다.

    calls = []

    def compute():
        calls.append(1)
        return len(calls)

    assert cache.cached_call(NAMESPACE, ("k",), compute) == 1
    time.sleep(0.15)
    assert cache.cached_call(NAMESPACE, ("k",), compute) == 2  # TTL 만료 후 재계산됨.


def test_clear_with_namespace_only_clears_that_namespace():
    cache.cached_call("ns-a", ("k",), lambda: "a")
    cache.cached_call("ns-b", ("k",), lambda: "b")

    cache.clear("ns-a")

    assert cache.cached_call("ns-a", ("k",), lambda: "recomputed") == "recomputed"
    assert cache.cached_call("ns-b", ("k",), lambda: "should-not-run") == "b"
