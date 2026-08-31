"""apt_trend_service 회귀 테스트.

1. get_apt_trend_summary()의 range-앵커형 base_date 폴백(90일 창 이동).
2. _build_count_change_rate()의 표본 부족 필터링(MIN_TRADE_COUNT) 제거 이후 동작
   (backend-apt-trend-count-change-rate-fix 계획서 Phase 4 테스트 케이스).
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from unittest.mock import MagicMock

from app.services import apt_trend_service


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
