"""단지별 실버 Fallback 집계 결과를 프로세스 메모리에 캐싱하는 공용 유틸리티.

Fallback(골드 마트 미스 시 실버/Iceberg 레이어를 온디맨드로 스캔해 집계)은 MinIO/GCS I/O 비용이
크므로, 계산 결과를 최소 settings.silver_fallback_cache_ttl_seconds(기본 3600초=1시간) 동안
캐싱해 동일 단지에 대한 반복 요청이 스토리지를 다시 스캔하지 않도록 한다.

cachetools.TTLCache는 스레드-세이프하지 않다(FastAPI의 동기 엔드포인트는 starlette가 threadpool에서
동시에 실행할 수 있으므로 여러 요청이 같은 캐시를 동시에 건드릴 수 있다). 그래서 캐시 조회/저장은
Lock으로 감싸되, 실제 계산(compute)은 Lock 밖에서 수행해 느린 스토리지 I/O 동안 다른 요청이 캐시를
쓰지 못하는 상황(hold lock during I/O)을 피한다. 이 때문에 서로 다른 요청이 같은 미스 키를 동시에
계산하는 드문 "cache stampede"가 가능하지만, 계산 자체는 멱등(동일 입력 -> 동일 출력)이므로 결과
정합성에는 영향이 없다.

namespace는 호출부(서비스/마트)별로 캐시를 분리하기 위한 식별자다(예:
"region_apt_compare:silver_fallback"). key는 보통 단지 식별자 튜플이다.
"""

from __future__ import annotations

import threading
from typing import Any, Callable

from cachetools import TTLCache

from app.core.config import settings

_lock = threading.Lock()
_caches: dict[str, TTLCache] = {}

_SENTINEL = object()


def get_cache(namespace: str) -> TTLCache:
    """namespace별로 독립된 TTLCache를 생성(최초 1회)하거나 재사용해 반환한다."""
    with _lock:
        cache = _caches.get(namespace)
        if cache is None:
            cache = TTLCache(
                maxsize=settings.silver_fallback_cache_maxsize,
                ttl=settings.silver_fallback_cache_ttl_seconds,
            )
            _caches[namespace] = cache
        return cache


def cached_call(namespace: str, key: Any, compute: Callable[[], Any]) -> Any:
    """namespace+key에 해당하는 캐시 값이 있으면 그대로 반환하고, 없으면 compute()를 호출해 그
    결과를 캐싱한 뒤 반환한다. compute()가 반환한 값(None 포함)도 그대로 캐싱한다 - "이 단지는
    실버 레이어에도 거래 이력이 없다"는 결과 자체도 반복 스캔을 막을 가치가 있는 정보이기 때문이다."""
    cache = get_cache(namespace)
    with _lock:
        cached = cache.get(key, _SENTINEL)
    if cached is not _SENTINEL:
        return cached

    value = compute()
    with _lock:
        cache[key] = value
    return value


def clear(namespace: str | None = None) -> None:
    """테스트 격리를 위한 캐시 초기화. namespace를 지정하면 그 캐시만, 생략하면 전체를 비운다."""
    with _lock:
        if namespace is None:
            _caches.clear()
        else:
            _caches.pop(namespace, None)
