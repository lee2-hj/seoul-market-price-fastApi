"""region_apt_compare_service.compare_region_apts()의 독립 2-엔티티(단지1/단지2) base_date
폴백 회귀 테스트. 한쪽 단지만 소급되고 다른 쪽은 매칭 자체가 없어 빈 객체({})로 남는 케이스를
포함한다(명세서 5항, Phase 5 세 번째 테스트 항목)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.core import cache as cache_module
from app.services import region_apt_compare_service as svc


@pytest.fixture(autouse=True)
def _clear_silver_fallback_cache():
    """실버 Fallback 캐시(cache.py의 전역 dict)는 프로세스 전역 상태이므로, 각 테스트 전후로
    비워 테스트 간 캐시 오염(이전 테스트의 monkeypatch된 fake 값이 남아 있는 것)을 막는다."""
    cache_module.clear(svc.CACHE_NAMESPACE)
    yield
    cache_module.clear(svc.CACHE_NAMESPACE)


def test_compare_region_apts_one_falls_back_other_has_no_match(monkeypatch):
    def fake_resolve_for_filter(con, mart_table, where_sql, params, **kwargs):
        if params.get("apt_nm") == "아파트1":
            return "2026-08-27"  # 단지1: 과거로 소급되어 매칭됨
        return None  # 단지2: max_lookback 안에서 매칭 자체가 없음

    monkeypatch.setattr(svc.duckdb_client, "get_connection", lambda: MagicMock())
    monkeypatch.setattr(svc.duckdb_client, "resolve_base_date_for_filter", fake_resolve_for_filter)
    monkeypatch.setattr(svc.duckdb_client, "resolve_base_date", lambda *a, **k: "2026-08-30")

    def fake_fetch_apt_row(con, base_date, cgg_cd, bjd_cd, apt_nm, mno, sno):
        if apt_nm == "아파트1":
            return {
                "apt_name": "아파트1",
                "trade_count": 3,
                "total_trade_amount": 30000,
                "total_price_per_pyeong": 9000,
                "total_pyeong": 90,
                "latest_trade_pyeong": 30.0,
                "household_count": 200,
                "build_year": 2010,
                "use_approval_date": "2010-05-01",
            }
        return None  # 단지2: 최근 90일 실거래 매칭 row 자체가 없음

    monkeypatch.setattr(svc, "_fetch_apt_row", fake_fetch_apt_row)

    group_1, group_2 = svc.compare_region_apts(
        cgg_cd_1="11500",
        bjd_cd_1="10300",
        apt_nm_1="아파트1",
        mno_1="1",
        sno_1="0",
        cgg_cd_2="11500",
        bjd_cd_2="10300",
        apt_nm_2="아파트2",
        mno_2="2",
        sno_2="0",
    )

    assert group_1["apt_name"] == "아파트1"
    assert group_1["base_date"] == "2026-08-27"
    # 단지2는 매칭되는 row가 없으므로 base_date를 포함하지 않는 빈 객체여야 한다.
    assert group_2 == {}


def test_compare_region_apts_matched_but_zero_trade_count_omits_base_date(monkeypatch):
    """단지를 찾긴 했지만(row 존재) 최근 90일 거래가 0건이면 기존 관례대로 빈 객체({})를 유지한다."""
    monkeypatch.setattr(svc.duckdb_client, "get_connection", lambda: MagicMock())
    monkeypatch.setattr(svc.duckdb_client, "resolve_base_date_for_filter", lambda *a, **k: "2026-08-30")
    monkeypatch.setattr(svc.duckdb_client, "resolve_base_date", lambda *a, **k: "2026-08-30")
    monkeypatch.setattr(
        svc, "_fetch_apt_row", lambda *a, **k: {"apt_name": "아파트1", "trade_count": 0}
    )

    group_1, group_2 = svc.compare_region_apts(
        cgg_cd_1="11500", bjd_cd_1="10300", apt_nm_1="아파트1", mno_1="1", sno_1="0",
        cgg_cd_2="11500", bjd_cd_2="10300", apt_nm_2="아파트1", mno_2="1", sno_2="0",
    )

    assert group_1 == {}
    assert group_2 == {}


# ---------------------------------------------------------------------------
# 실버(fact_apt_transactions) 레이어 Fallback: 골드에 최근 90일 거래가 없는 단지 보정
# ---------------------------------------------------------------------------


def _fake_silver_row(apt_nm: str) -> dict:
    """dm_apt_recent_trade 실제 운영 데이터와 fact_apt_transactions를 교차 검증해 확인한
    실제 값(익성씨티하임, 2026-05-29 기준)을 그대로 사용한 실버 집계 결과 fixture."""
    return {
        "apt_name": apt_nm,
        "anchor_date": "2026-05-29",
        "trade_count": 2,
        "total_trade_amount": 21600,
        "total_price_per_pyeong": 3562,
        "total_pyeong": 12.13,
        "latest_trade_amount": 10800,
        "latest_trade_pyeong": 6.06,
        "household_count": None,
        "build_year": None,
        "use_approval_date": None,
    }


def test_silver_fallback_not_invoked_when_gold_already_has_trade_count(monkeypatch):
    """골드에 데이터가 정상적으로 존재하는 단지는 실버 스캔을 전혀 호출하지 않고 기존대로
    즉시 응답해야 한다(검증 항목 1)."""
    monkeypatch.setattr(svc.duckdb_client, "get_connection", lambda: MagicMock())
    monkeypatch.setattr(svc.duckdb_client, "resolve_base_date_for_filter", lambda *a, **k: "2026-09-07")
    monkeypatch.setattr(svc.duckdb_client, "resolve_base_date", lambda *a, **k: "2026-09-07")
    monkeypatch.setattr(
        svc,
        "_fetch_apt_row",
        lambda *a, **k: {
            "apt_name": "아파트1",
            "trade_count": 3,
            "total_trade_amount": 30000,
            "total_price_per_pyeong": 9000,
            "total_pyeong": 90,
            "latest_trade_pyeong": 30.0,
            "household_count": 200,
            "build_year": 2010,
            "use_approval_date": "2010-05-01",
        },
    )
    silver_calls: list[int] = []
    monkeypatch.setattr(
        svc, "_fetch_silver_aggregate", lambda *a, **k: silver_calls.append(1) or None
    )

    group_1, group_2 = svc.compare_region_apts(
        cgg_cd_1="11500", bjd_cd_1="10300", apt_nm_1="아파트1", mno_1="1", sno_1="0",
        cgg_cd_2="11500", bjd_cd_2="10300", apt_nm_2="아파트1", mno_2="1", sno_2="0",
    )

    assert group_1["base_date"] == "2026-09-07"
    assert group_1["deal_count"] == 3
    assert group_2["deal_count"] == 3
    assert silver_calls == []  # 골드 히트 시 실버 폴백은 호출조차 되지 않아야 한다.


def test_silver_fallback_used_when_gold_has_no_row(monkeypatch):
    """골드에 매칭 row 자체가 없는(최근 90일 거래 0건) 단지는 실버에서 [마지막 거래일 - 89일 ~
    마지막 거래일] 구간을 집계해, 기존 DTO 규격(_build_group 계산식)을 그대로 만족해야 한다
    (검증 항목 2)."""
    monkeypatch.setattr(svc.duckdb_client, "get_connection", lambda: MagicMock())
    monkeypatch.setattr(svc.duckdb_client, "resolve_base_date_for_filter", lambda *a, **k: None)
    monkeypatch.setattr(svc.duckdb_client, "resolve_base_date", lambda *a, **k: "2026-09-07")
    monkeypatch.setattr(svc, "_fetch_apt_row", lambda *a, **k: None)

    def fake_silver(con, cgg_cd, bjd_cd, apt_nm, mno, sno):
        assert (cgg_cd, bjd_cd, apt_nm, mno, sno) == ("11110", "17500", "익성씨티하임", "1392", "0000")
        return _fake_silver_row(apt_nm)

    monkeypatch.setattr(svc, "_fetch_silver_aggregate", fake_silver)

    group_1, group_2 = svc.compare_region_apts(
        cgg_cd_1="11110", bjd_cd_1="17500", apt_nm_1="익성씨티하임", mno_1="1392", sno_1="0000",
        cgg_cd_2="11110", bjd_cd_2="17500", apt_nm_2="익성씨티하임", mno_2="1392", sno_2="0000",
    )

    for group in (group_1, group_2):
        assert group["apt_name"] == "익성씨티하임"
        assert group["base_date"] == "2026-05-29"  # 골드 base_date가 아니라 실버 anchor_date.
        assert group["deal_count"] == 2
        assert group["avg_deal_price"] == 10800  # round(21600 / 2)
        assert group["avg_pyeong_price"] == 1781  # round(3562 / 2)
        assert group["avg_pyeong"] == 6  # round(12.13 / 2)
        assert group["latest_trade_pyeong"] == 6  # round(6.06)
        # 원시 거래 팩트 테이블에는 없는 단지 메타데이터는 스키마상 선택 필드인 None으로 유지된다.
        assert group["total_households"] is None
        assert group["build_year"] is None
        assert group["use_approval_date"] is None


def test_silver_fallback_returns_empty_when_no_history_anywhere(monkeypatch):
    """골드에도 없고 실버(fact_apt_transactions)에도 거래 이력이 전혀 없는 단지는 기존 관례대로
    빈 객체({})를 유지해야 한다."""
    monkeypatch.setattr(svc.duckdb_client, "get_connection", lambda: MagicMock())
    monkeypatch.setattr(svc.duckdb_client, "resolve_base_date_for_filter", lambda *a, **k: None)
    monkeypatch.setattr(svc.duckdb_client, "resolve_base_date", lambda *a, **k: "2026-09-07")
    monkeypatch.setattr(svc, "_fetch_apt_row", lambda *a, **k: None)
    monkeypatch.setattr(svc, "_fetch_silver_aggregate", lambda *a, **k: None)

    group_1, group_2 = svc.compare_region_apts(
        cgg_cd_1="11500", bjd_cd_1="10300", apt_nm_1="유령단지", mno_1="1", sno_1="0",
        cgg_cd_2="11500", bjd_cd_2="10300", apt_nm_2="유령단지", mno_2="1", sno_2="0",
    )

    assert group_1 == {}
    assert group_2 == {}


def test_silver_fallback_result_is_cached_across_repeated_calls(monkeypatch):
    """동일 단지를 연속 2회 조회하면 두 번째 호출은 캐시 히트로 처리되어 실버 스캔
    (_fetch_silver_aggregate)이 다시 실행되지 않아야 한다(검증 항목 3)."""
    calls: list[int] = []

    def fake_silver(con, cgg_cd, bjd_cd, apt_nm, mno, sno):
        calls.append(1)
        return _fake_silver_row(apt_nm)

    monkeypatch.setattr(svc, "_fetch_silver_aggregate", fake_silver)

    con = MagicMock()
    results = [
        svc._resolve_with_silver_fallback(
            con, None, "2026-09-07", "11110", "17500", "익성씨티하임", "1392", "0000"
        )
        for _ in range(2)
    ]

    for row, base_date in results:
        assert base_date == "2026-05-29"
        assert row["trade_count"] == 2

    assert len(calls) == 1  # 두 번째 호출은 캐시 히트라 실버 스캔이 다시 실행되지 않는다.
