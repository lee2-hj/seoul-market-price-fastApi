"""rtt_service.get_rtt_summary()의 range-앵커형 base_date 폴백(90일 창 이동) 회귀 테스트."""

from __future__ import annotations

import logging
from datetime import date, timedelta
from unittest.mock import MagicMock

from app.services import rtt_service


def test_get_rtt_summary_shifts_window_when_naive_period_has_no_matching_trades(monkeypatch, caplog):
    """나이브 90일 창에는 거래가 없고, lookback(기본 30일) 이내의 과거에 거래가 있으면
    창을 그 시점으로 이동시켜 재조회해야 한다."""
    monkeypatch.setattr(rtt_service.duckdb_client, "get_connection", lambda: MagicMock())

    call_count = {"n": 0}
    naive_start, _ = rtt_service._period_range(date.today())
    # naive 창보다 과거이면서도 max_base_date_lookback(30일) 상한 이내인 날짜.
    matched = naive_start - timedelta(days=15)

    def fake_fetch_rows(con, sgg_cd, dong_cd, start_date, end_date):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return []  # 나이브 창: 거래 없음
        # 이동된 창으로 재조회했을 때: 실제로 이동된 날짜 범위인지 확인
        assert end_date == matched
        assert start_date == matched - timedelta(days=rtt_service.PERIOD_DAYS - 1)
        return [{
            "trade_count": 3, "trade_amount": 30000, "deal_date": matched.isoformat(),
            "sgg_nm": "강남구", "dong_nm": "역삼동", "apt_name": "테스트", "mno": "1", "sno": "0",
            "floor": 5, "pyeong": 25.0, "exclusive_area_m2": 82.6,
        }]

    monkeypatch.setattr(rtt_service, "_fetch_rows", fake_fetch_rows)
    monkeypatch.setattr(rtt_service.duckdb_client, "resolve_recent_match_date", lambda *a, **k: matched)

    with caplog.at_level(logging.INFO, logger="app.services.rtt_service"):
        result = rtt_service.get_rtt_summary(sgg_cd="11680")

    assert result["period_end"] == matched
    assert result["period_start"] == matched - timedelta(days=rtt_service.PERIOD_DAYS - 1)
    assert result["total_deal_cnt"] == 3
    assert any("Anchor fallback used" in r.message for r in caplog.records)


def test_get_rtt_summary_keeps_empty_result_when_match_exceeds_lookback(monkeypatch):
    """매칭된 날짜가 있어도 lookback 상한을 벗어나면 창을 이동하지 않고 빈 결과를 그대로 반환한다."""
    monkeypatch.setattr(rtt_service.duckdb_client, "get_connection", lambda: MagicMock())
    monkeypatch.setattr(rtt_service, "_fetch_rows", lambda *a, **k: [])

    naive_start, _ = rtt_service._period_range(date.today())
    too_old = naive_start - timedelta(days=rtt_service.settings.max_base_date_lookback + 10)
    monkeypatch.setattr(rtt_service.duckdb_client, "resolve_recent_match_date", lambda *a, **k: too_old)

    result = rtt_service.get_rtt_summary(sgg_cd="11680")

    expected_start, expected_end = rtt_service._period_range(date.today())
    assert result["total_deal_cnt"] == 0
    assert result["period_start"] == expected_start
    assert result["period_end"] == expected_end


def test_get_rtt_summary_keeps_empty_result_when_no_match_at_all(monkeypatch):
    monkeypatch.setattr(rtt_service.duckdb_client, "get_connection", lambda: MagicMock())
    monkeypatch.setattr(rtt_service, "_fetch_rows", lambda *a, **k: [])
    monkeypatch.setattr(rtt_service.duckdb_client, "resolve_recent_match_date", lambda *a, **k: None)

    result = rtt_service.get_rtt_summary(sgg_cd="00000")

    assert result["total_deal_cnt"] == 0
    assert result["recent_trades"] == []


def test_get_rtt_summary_does_not_call_fallback_when_naive_window_has_rows(monkeypatch):
    """흔한 경우(나이브 90일 창에 이미 데이터가 있음)는 resolve_recent_match_date를 호출하지
    않아야 한다(추가 비용 없음)."""
    monkeypatch.setattr(rtt_service.duckdb_client, "get_connection", lambda: MagicMock())
    monkeypatch.setattr(
        rtt_service, "_fetch_rows",
        lambda *a, **k: [{
            "trade_count": 1, "trade_amount": 10000, "deal_date": "2026-08-30",
            "sgg_nm": "강남구", "dong_nm": "역삼동", "apt_name": "테스트", "mno": "1", "sno": "0",
            "floor": 5, "pyeong": 25.0, "exclusive_area_m2": 82.6,
        }],
    )

    called = {"n": 0}

    def fail_if_called(*a, **k):
        called["n"] += 1
        return None

    monkeypatch.setattr(rtt_service.duckdb_client, "resolve_recent_match_date", fail_if_called)

    rtt_service.get_rtt_summary(sgg_cd="11680")

    assert called["n"] == 0
