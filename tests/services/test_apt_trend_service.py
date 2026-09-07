"""apt_trend_service 회귀 테스트.

1. get_apt_trend_summary()의 range-앵커형 base_date 폴백(90일 창 이동) + 실버(fact_apt_transactions)
   레이어 Fallback(apt_mkt_trends 보존 기간 밖 단지).
2. _build_count_change_rate()의 표본 부족 필터링(MIN_TRADE_COUNT) 제거 이후 동작
   (backend-apt-trend-count-change-rate-fix 계획서 Phase 4 테스트 케이스).
3. _build_count_change_rate()의 0건 구간 짝짓기 제외(있는 데이터끼리만 비교) 회귀 테스트 -
   중간에 0건 구간이 끼어 있을 때 인접 비교로 인해 -100%에 가깝게 왜곡되던 문제 수정.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from unittest.mock import MagicMock

import pytest

from app.core import cache as cache_module
from app.services import apt_trend_service


@pytest.fixture(autouse=True)
def _clear_anchor_fallback_cache():
    """apt_trend_service의 앵커 폴백 캐시(전역 dict)가 테스트 간에 남아있지 않도록 정리한다."""
    cache_module.clear(apt_trend_service.CACHE_NAMESPACE)
    yield
    cache_module.clear(apt_trend_service.CACHE_NAMESPACE)


# ---------------------------------------------------------------------------
# get_apt_trend_summary: range-앵커 폴백
# ---------------------------------------------------------------------------


def test_get_apt_trend_summary_shifts_window_when_naive_period_has_no_matching_trades(monkeypatch, caplog):
    monkeypatch.setattr(apt_trend_service.duckdb_client, "get_connection", lambda: MagicMock())

    call_count = {"n": 0}
    naive_start, _ = apt_trend_service._period_range(date.today())
    # naive 창보다 과거이면서도 max_base_date_lookback(30일) 상한 이내인 날짜.
    matched = naive_start - timedelta(days=15)

    def fake_fetch_rows(con, cgg_cd, stdg_cd, mno, sno, apt_name, start_date, end_date):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return []
        assert end_date == matched
        assert start_date == matched - timedelta(days=apt_trend_service.PERIOD_DAYS)
        return [
            {
                "cgg_cd": cgg_cd, "cgg_nm": "강서구", "stdg_cd": stdg_cd, "stdg_nm": "화곡동",
                "apt_name": "테스트아파트", "mno": mno, "sno": sno,
                "deal_date": matched.isoformat(), "floor": 5, "trade_amount": 50000,
                "pyeong": 25.0, "trade_count": 1,
            }
        ]

    monkeypatch.setattr(apt_trend_service, "_fetch_rows", fake_fetch_rows)
    monkeypatch.setattr(apt_trend_service.duckdb_client, "resolve_recent_match_date", lambda *a, **k: matched)

    with caplog.at_level(logging.INFO, logger="app.services.apt_trend_service"):
        result = apt_trend_service.get_apt_trend_summary(
            cgg_cd="11500", stdg_cd="10300", mno="661", sno="0", apt_name=None
        )

    assert result["search_period"]["end_date"] == matched
    assert result["count"] == 1
    assert any("Anchor fallback used" in r.message for r in caplog.records)


def test_get_apt_trend_summary_falls_back_to_silver_when_mart_retention_window_missed(monkeypatch, caplog):
    """apt_mkt_trends는 최근 ~100여 일만 보존하는 롤링 마트라, 단지의 마지막 실거래가 그보다
    오래되면 resolve_recent_match_date로도 영영 못 찾는다(실측으로 확인된 실제 케이스: 강남구
    개포동 '개포자이' 11680/10300/0012/0002 - apt_mkt_trends엔 없지만 fact_apt_transactions
    원본에는 7건의 실거래가 있음). 이 경우 실버(fact_apt_transactions) 원본까지 온디맨드로
    내려가 정상 집계해야 한다."""
    monkeypatch.setattr(apt_trend_service.duckdb_client, "get_connection", lambda: MagicMock())
    monkeypatch.setattr(apt_trend_service, "_fetch_rows", lambda *a, **k: [])
    # apt_mkt_trends 자체에는 매칭이 전혀 없다(보존 기간 밖).
    monkeypatch.setattr(apt_trend_service.duckdb_client, "resolve_recent_match_date", lambda *a, **k: None)

    silver_last_date = date(2026, 5, 15)
    silver_rows = [
        {
            "cgg_cd": "11680", "cgg_nm": "강남구", "stdg_cd": "10300", "stdg_nm": "개포동",
            "apt_name": "개포자이", "mno": "0012", "sno": "0002",
            "deal_date": "2026-03-11", "floor": 17, "pyeong": 40.63,
            "trade_amount": 186000, "trade_count": 1,
        },
        {
            "cgg_cd": "11680", "cgg_nm": "강남구", "stdg_cd": "10300", "stdg_nm": "개포동",
            "apt_name": "개포자이", "mno": "0012", "sno": "0002",
            "deal_date": silver_last_date.isoformat(), "floor": 19, "pyeong": 46.52,
            "trade_amount": 320000, "trade_count": 1,
        },
    ]

    def fake_fetch_silver_rows(con, cgg_cd, stdg_cd, mno, sno, apt_name):
        assert (cgg_cd, stdg_cd, mno, sno, apt_name) == ("11680", "10300", "0012", "0002", "개포자이")
        return silver_rows

    monkeypatch.setattr(apt_trend_service, "_fetch_silver_rows", fake_fetch_silver_rows)

    with caplog.at_level(logging.INFO, logger="app.services.apt_trend_service"):
        result = apt_trend_service.get_apt_trend_summary(
            cgg_cd="11680", stdg_cd="10300", mno="0012", sno="0002", apt_name="개포자이"
        )

    assert result["search_period"]["end_date"] == silver_last_date
    assert result["count"] == 1
    item = result["data"][0]
    assert item["apt_name"] == "개포자이"
    assert item["cgg_nm"] == "강남구"
    assert item["stdg_nm"] == "개포동"
    assert item["total_deal_count"] == 2
    assert item["total_deal_amount"] == 506000
    assert item["average_deal_price"] == 253000
    assert any("Silver fallback used" in r.message for r in caplog.records)


def test_get_apt_trend_summary_silver_fallback_result_is_cached(monkeypatch):
    """동일 단지를 연속 2회 조회하면 두 번째 호출은 캐시 히트로 처리되어 실버 스캔
    (_fetch_silver_rows)이 다시 실행되지 않아야 한다."""
    monkeypatch.setattr(apt_trend_service.duckdb_client, "get_connection", lambda: MagicMock())
    monkeypatch.setattr(apt_trend_service, "_fetch_rows", lambda *a, **k: [])
    monkeypatch.setattr(apt_trend_service.duckdb_client, "resolve_recent_match_date", lambda *a, **k: None)

    calls: list[int] = []

    def fake_fetch_silver_rows(con, cgg_cd, stdg_cd, mno, sno, apt_name):
        calls.append(1)
        return [
            {
                "cgg_cd": cgg_cd, "cgg_nm": "강남구", "stdg_cd": stdg_cd, "stdg_nm": "개포동",
                "apt_name": apt_name, "mno": mno, "sno": sno,
                "deal_date": "2026-05-15", "floor": 19, "pyeong": 46.52,
                "trade_amount": 320000, "trade_count": 1,
            }
        ]

    monkeypatch.setattr(apt_trend_service, "_fetch_silver_rows", fake_fetch_silver_rows)

    kwargs = dict(cgg_cd="11680", stdg_cd="10300", mno="0012", sno="0002", apt_name="개포자이")
    result_1 = apt_trend_service.get_apt_trend_summary(**kwargs)
    result_2 = apt_trend_service.get_apt_trend_summary(**kwargs)

    assert result_1["search_period"] == result_2["search_period"]
    assert result_1["count"] == result_2["count"] == 1
    assert len(calls) == 1  # 두 번째 호출은 캐시 히트라 실버 스캔이 다시 실행되지 않는다.


def test_get_apt_trend_summary_keeps_empty_result_when_no_match_at_all(monkeypatch):
    monkeypatch.setattr(apt_trend_service.duckdb_client, "get_connection", lambda: MagicMock())
    monkeypatch.setattr(apt_trend_service, "_fetch_rows", lambda *a, **k: [])
    monkeypatch.setattr(apt_trend_service.duckdb_client, "resolve_recent_match_date", lambda *a, **k: None)

    result = apt_trend_service.get_apt_trend_summary(
        cgg_cd="00000", stdg_cd="00000", mno="0", sno="0", apt_name=None
    )

    assert result["count"] == 0
    assert result["data"] == []


def test_get_apt_trend_summary_passes_entity_filter_without_date_condition_to_fallback(monkeypatch):
    """resolve_recent_match_date에는 날짜 조건 없이 단지 필터(cgg_cd/stdg_cd/mno/sno/apt_name)만
    전달되어야 한다(전체 이력에서 조회해야 하므로)."""
    captured: dict = {}

    def fake_resolve_recent_match_date(con, glob_pattern, date_column, where_sql, params):
        captured["date_column"] = date_column
        captured["where_sql"] = where_sql
        captured["params"] = params
        return None

    monkeypatch.setattr(apt_trend_service.duckdb_client, "get_connection", lambda: MagicMock())
    monkeypatch.setattr(apt_trend_service, "_fetch_rows", lambda *a, **k: [])
    monkeypatch.setattr(
        apt_trend_service.duckdb_client, "resolve_recent_match_date", fake_resolve_recent_match_date
    )

    apt_trend_service.get_apt_trend_summary(
        cgg_cd="11500", stdg_cd="10300", mno="661", sno="0", apt_name="래미안"
    )

    assert captured["date_column"] == "deal_date"
    assert "start_date" not in captured["params"]
    assert "end_date" not in captured["params"]
    assert captured["params"]["apt_name"] == "%래미안%"
    assert "apt_name ILIKE $apt_name" in captured["where_sql"]


def test_get_apt_trend_summary_anchor_fallback_result_is_cached(monkeypatch):
    """동일 단지를 연속 2회 조회하면 두 번째 호출은 캐시 히트로 처리되어
    resolve_recent_match_date/재조회 스캔이 다시 실행되지 않아야 한다."""
    monkeypatch.setattr(apt_trend_service.duckdb_client, "get_connection", lambda: MagicMock())

    naive_start, _ = apt_trend_service._period_range(date.today())
    matched = naive_start - timedelta(days=15)

    fetch_calls = {"n": 0}
    resolve_calls = {"n": 0}

    def fake_fetch_rows(con, cgg_cd, stdg_cd, mno, sno, apt_name, start_date, end_date):
        fetch_calls["n"] += 1
        if end_date != matched:
            return []  # naive 창 조회는 항상 빈 결과
        return [
            {
                "cgg_cd": cgg_cd, "cgg_nm": "강서구", "stdg_cd": stdg_cd, "stdg_nm": "화곡동",
                "apt_name": "테스트아파트", "mno": mno, "sno": sno,
                "deal_date": matched.isoformat(), "floor": 5, "trade_amount": 50000,
                "pyeong": 25.0, "trade_count": 1,
            }
        ]

    def fake_resolve_recent_match_date(*a, **k):
        resolve_calls["n"] += 1
        return matched

    monkeypatch.setattr(apt_trend_service, "_fetch_rows", fake_fetch_rows)
    monkeypatch.setattr(
        apt_trend_service.duckdb_client, "resolve_recent_match_date", fake_resolve_recent_match_date
    )

    kwargs = dict(cgg_cd="11500", stdg_cd="10300", mno="661", sno="0", apt_name=None)
    result_1 = apt_trend_service.get_apt_trend_summary(**kwargs)
    result_2 = apt_trend_service.get_apt_trend_summary(**kwargs)

    assert result_1["search_period"] == result_2["search_period"]
    assert result_1["count"] == result_2["count"] == 1
    # naive 조회(빈 결과)는 매번 실행되지만(캐싱 대상이 아님), 앵커 이동 재조회
    # (resolve_recent_match_date + 이동된 창의 _fetch_rows)는 캐시 히트로 1회만 실행되어야 한다.
    assert resolve_calls["n"] == 1
    assert fetch_calls["n"] == 3  # naive(1회차) + naive(2회차) + 이동된 창 재조회(1회차, 캐시됨)


def test_get_apt_trend_summary_does_not_call_fallback_when_naive_window_has_rows(monkeypatch):
    monkeypatch.setattr(apt_trend_service.duckdb_client, "get_connection", lambda: MagicMock())
    monkeypatch.setattr(
        apt_trend_service, "_fetch_rows",
        lambda *a, **k: [
            {"cgg_cd": "11500", "cgg_nm": "강서구", "stdg_cd": "10300", "stdg_nm": "화곡동",
             "apt_name": "테스트", "mno": "1", "sno": "0", "deal_date": "2026-08-30",
             "floor": 3, "trade_amount": 40000, "pyeong": 20.0, "trade_count": 1}
        ],
    )
    called = {"n": 0}

    def fail_if_called(*a, **k):
        called["n"] += 1

    monkeypatch.setattr(apt_trend_service.duckdb_client, "resolve_recent_match_date", fail_if_called)

    apt_trend_service.get_apt_trend_summary(cgg_cd="11500", stdg_cd="10300", mno="1", sno="0", apt_name=None)

    assert called["n"] == 0


# ---------------------------------------------------------------------------
# _build_count_change_rate: MIN_TRADE_COUNT 필터링 제거 회귀 테스트
# (docs/plans/backend-apt-trend-count-change-rate-fix-plan.md Phase 4)
# ---------------------------------------------------------------------------


def _trend(deal_counts: list[int]) -> list[dict]:
    return [{"deal_count": c} for c in deal_counts]


def test_count_change_rate_low_volume_still_produces_a_value():
    """i. 저거래량 케이스: 전 구간이 3건 미만이어도 0이 아닌 이상 증감률을 계산해야 한다
    (기존 MIN_TRADE_COUNT=3 필터링 시 전부 제외되어 None이 나오던 회귀 케이스)."""
    result = apt_trend_service._build_count_change_rate(_trend([1, 2, 1, 0, 2, 3]))
    assert result is not None


def test_count_change_rate_only_excludes_step_with_zero_prev_count():
    """ii. prev_count == 0 가드: 첫 스텝(0 -> 5)만 제외되고 나머지 스텝은 정상 계산되어야 한다."""
    trend = _trend([0, 5, 3, 4, 2, 6])
    result = apt_trend_service._build_count_change_rate(trend)
    assert result is not None

    # 수동 계산: 스텝1(0->5)은 제외. 스텝2~5만 가중평균(가중치 2,3,4,5).
    steps = [(5, 3, 2), (3, 4, 3), (4, 2, 4), (2, 6, 5)]
    weighted_sum = sum((curr - prev) / prev * 100 * w for prev, curr, w in steps)
    weight_total = sum(w for _, _, w in steps)
    expected = round(weighted_sum / weight_total)
    assert result == expected


def test_count_change_rate_skips_zero_gap_instead_of_treating_as_cliff():
    """실제 사용자 리포트 재현: 중간에 0건 구간이 여러 개 끼어 있을 때, 이를 "인접 구간"으로
    취급해 비교하면 -100%에 가까운 왜곡된 값이 나온다(5건->0건이 즉시 -100%가 되어버림).
    거래가 있는 구간끼리만(5건과 3건) 비교하면 완만한 -40% 감소로 정확히 계산되어야 한다."""
    result = apt_trend_service._build_count_change_rate(_trend([5, 0, 0, 0, 0, 3]))
    assert result == -40  # (3-5)/5*100 = -40%, 인접 비교였다면 첫 스텝만으로 -100%가 나왔을 것.


def test_count_change_rate_reproduces_reported_apt_no_real_change():
    """실제 리포트 사례 재현(새롬(1164-13), 11680/10300/1164/0013): 90일 중 처음과 마지막
    2주 구간에만 각각 1건씩 거래가 있고 나머지 4구간은 0건이었다. 수정 전에는 count_change_rate가
    -100으로 계산됐지만(1건->0건 인접 비교), 실제로는 1건->1건으로 변동이 전혀 없으므로 0이어야
    한다."""
    result = apt_trend_service._build_count_change_rate(_trend([1, 0, 0, 0, 0, 1]))
    assert result == 0


def test_count_change_rate_only_pairs_non_zero_buckets_weight_uses_original_index():
    """0건 구간을 건너뛰어 짝지어도, 가중치는 원래 biweekly_trend에서의 위치(0-based index)를
    그대로 사용해야 한다(최신 구간일수록 높은 가중치라는 기존 원칙 유지)."""
    # deal_count=[2, 4, 0, 0, 6, 0] -> 0건 아닌 구간은 index 0(2), 1(4), 4(6).
    # 짝: (idx0->idx1, weight=1), (idx1->idx4, weight=4).
    trend = _trend([2, 4, 0, 0, 6, 0])
    result = apt_trend_service._build_count_change_rate(trend)
    step1_rate = (4 - 2) / 2 * 100  # 100
    step2_rate = (6 - 4) / 4 * 100  # 50
    expected = round((step1_rate * 1 + step2_rate * 4) / (1 + 4))
    assert result == expected


def test_count_change_rate_all_zero_except_last_returns_none():
    """iii. 완전 무거래: 마지막 구간을 제외한 모든 prev_count가 0이면 계산 가능한 스텝이
    하나도 없으므로 여전히 None을 반환해야 한다."""
    result = apt_trend_service._build_count_change_rate(_trend([0, 0, 0, 0, 0, 5]))
    assert result is None


def test_count_change_rate_never_raises_zero_division_error():
    """모든 스텝이 prev_count == 0이어도(마지막 구간 포함 전부 0) ZeroDivisionError가 발생하면 안 된다."""
    result = apt_trend_service._build_count_change_rate(_trend([0, 0, 0, 0, 0, 0]))
    assert result is None


def test_count_change_rate_no_min_trade_count_constant():
    """MIN_TRADE_COUNT 상수가 apt_trend_service에서 완전히 제거되었는지 확인한다."""
    assert not hasattr(apt_trend_service, "MIN_TRADE_COUNT")
