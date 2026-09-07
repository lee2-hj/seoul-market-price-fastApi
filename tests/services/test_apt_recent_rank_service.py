"""apt_recent_rank_service 회귀 테스트. rtt_service.py와 동일한 마트(RTT)를 재사용하므로
tests/services/test_rtt_service.py의 monkeypatch(duckdb_client mocking) 패턴을 그대로 따른다.

1. 정상 데이터(8건)로 top5/bottom5 개수·정렬 검증
2. 매칭 5건 이하일 때 bottom이 빈 리스트인지
3. 90일 창에 데이터가 없을 때 앵커 폴백이 동작해 과거 구간으로 이동하는지
4. 완전히 매칭 데이터가 없는 경우(앵커 폴백도 실패) top/bottom이 빈 리스트로 정상 반환되는지
5. pyeong은 반올림해 소수점 없는 정수로 반환되는지(exclusive_area_m2/trade_amount는 원본 그대로)
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from unittest.mock import MagicMock

from app.services import apt_recent_rank_service as svc


def _row(apt_name: str, trade_amount: float, deal_date: str = "2026-09-01") -> dict:
    return {
        "sgg_cd": "11680",
        "sgg_nm": "강남구",
        "dong_cd": "10300",
        "dong_nm": "역삼동",
        "apt_name": apt_name,
        "mno": "1",
        "sno": "0",
        "deal_date": deal_date,
        "floor": 5,
        "trade_amount": trade_amount,
        "pyeong": 25.0,
        "exclusive_area_m2": 82.6,
        "trade_count": 1,
    }


# ---------------------------------------------------------------------------
# 케이스 1: 정상 데이터(8건) - top5/bottom5 개수·정렬 검증
# ---------------------------------------------------------------------------


def test_get_apt_recent_rank_returns_sorted_top5_and_bottom5(monkeypatch):
    monkeypatch.setattr(svc.duckdb_client, "get_connection", lambda: MagicMock())
    amounts = [50000, 80000, 30000, 90000, 60000, 40000, 70000, 20000]
    rows = [_row(f"단지{i}", amt) for i, amt in enumerate(amounts)]
    monkeypatch.setattr(svc, "_fetch_rows", lambda *a, **k: rows)

    result = svc.get_apt_recent_rank(sgg_cd="11680", dong_cd="10300")

    assert [item["trade_amount"] for item in result["top"]] == [90000, 80000, 70000, 60000, 50000]
    assert [item["trade_amount"] for item in result["bottom"]] == [20000, 30000, 40000, 50000, 60000]
    assert result["sgg_nm"] == "강남구"
    assert result["dong_nm"] == "역삼동"
    assert result["sgg_cd"] == "11680"
    assert result["dong_cd"] == "10300"
    # 응답 항목은 RTT 원본 5개 필드만 가공 없이 담아야 한다.
    assert set(result["top"][0].keys()) == {
        "apt_name", "exclusive_area_m2", "pyeong", "floor", "trade_amount",
    }


# ---------------------------------------------------------------------------
# 케이스 2: 매칭 5건 이하 - bottom은 빈 리스트
# ---------------------------------------------------------------------------


def test_get_apt_recent_rank_bottom_is_empty_when_five_or_fewer_rows(monkeypatch):
    monkeypatch.setattr(svc.duckdb_client, "get_connection", lambda: MagicMock())
    rows = [_row(f"단지{i}", amt) for i, amt in enumerate([50000, 80000, 30000, 90000, 60000])]
    monkeypatch.setattr(svc, "_fetch_rows", lambda *a, **k: rows)

    result = svc.get_apt_recent_rank(sgg_cd="11680", dong_cd="10300")

    assert len(result["top"]) == 5
    assert result["bottom"] == []


# ---------------------------------------------------------------------------
# 케이스 3: 90일 창에 데이터 없음 -> 앵커 폴백
# ---------------------------------------------------------------------------


def test_get_apt_recent_rank_shifts_window_when_naive_period_has_no_matching_trades(monkeypatch, caplog):
    monkeypatch.setattr(svc.duckdb_client, "get_connection", lambda: MagicMock())

    naive_start, _ = svc._period_range(date.today())
    matched = naive_start - timedelta(days=15)

    call_count = {"n": 0}

    def fake_fetch_rows(con, sgg_cd, dong_cd, start_date, end_date):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return []  # 나이브 창: 거래 없음
        assert end_date == matched
        assert start_date == matched - timedelta(days=svc.PERIOD_DAYS - 1)
        return [_row("테스트단지", 50000, matched.isoformat())]

    monkeypatch.setattr(svc, "_fetch_rows", fake_fetch_rows)
    monkeypatch.setattr(svc.duckdb_client, "resolve_recent_match_date", lambda *a, **k: matched)

    with caplog.at_level(logging.INFO, logger="app.services.apt_recent_rank_service"):
        result = svc.get_apt_recent_rank(sgg_cd="11680", dong_cd="10300")

    assert result["period_end"] == matched
    assert result["period_start"] == matched - timedelta(days=svc.PERIOD_DAYS - 1)
    assert len(result["top"]) == 1
    assert result["top"][0]["trade_amount"] == 50000
    assert any("Anchor fallback used" in r.message for r in caplog.records)


def test_get_apt_recent_rank_keeps_empty_result_when_match_exceeds_lookback(monkeypatch):
    """매칭된 날짜가 있어도 lookback 상한을 벗어나면 창을 이동하지 않고 빈 결과를 그대로 반환한다."""
    monkeypatch.setattr(svc.duckdb_client, "get_connection", lambda: MagicMock())
    monkeypatch.setattr(svc, "_fetch_rows", lambda *a, **k: [])

    naive_start, _ = svc._period_range(date.today())
    too_old = naive_start - timedelta(days=svc.settings.max_base_date_lookback + 10)
    monkeypatch.setattr(svc.duckdb_client, "resolve_recent_match_date", lambda *a, **k: too_old)

    result = svc.get_apt_recent_rank(sgg_cd="11680", dong_cd="10300")

    expected_start, expected_end = svc._period_range(date.today())
    assert result["top"] == []
    assert result["bottom"] == []
    assert result["period_start"] == expected_start
    assert result["period_end"] == expected_end


def test_get_apt_recent_rank_does_not_call_fallback_when_naive_window_has_rows(monkeypatch):
    """흔한 경우(나이브 90일 창에 이미 데이터가 있음)는 resolve_recent_match_date를 호출하지
    않아야 한다(추가 비용 없음)."""
    monkeypatch.setattr(svc.duckdb_client, "get_connection", lambda: MagicMock())
    monkeypatch.setattr(svc, "_fetch_rows", lambda *a, **k: [_row("테스트단지", 50000)])

    called = {"n": 0}

    def fail_if_called(*a, **k):
        called["n"] += 1
        return None

    monkeypatch.setattr(svc.duckdb_client, "resolve_recent_match_date", fail_if_called)

    svc.get_apt_recent_rank(sgg_cd="11680", dong_cd="10300")

    assert called["n"] == 0


# ---------------------------------------------------------------------------
# 케이스 4: 완전히 매칭 데이터 없음(앵커 폴백도 실패) - top/bottom 모두 빈 리스트
# ---------------------------------------------------------------------------


def test_get_apt_recent_rank_keeps_empty_result_when_no_match_at_all(monkeypatch):
    monkeypatch.setattr(svc.duckdb_client, "get_connection", lambda: MagicMock())
    monkeypatch.setattr(svc, "_fetch_rows", lambda *a, **k: [])
    monkeypatch.setattr(svc.duckdb_client, "resolve_recent_match_date", lambda *a, **k: None)

    result = svc.get_apt_recent_rank(sgg_cd="00000", dong_cd="00000")

    assert result["top"] == []
    assert result["bottom"] == []
    assert result["sgg_nm"] is None
    assert result["dong_nm"] is None


# ---------------------------------------------------------------------------
# 케이스 5: pyeong 반올림(소수점 제거) - exclusive_area_m2/trade_amount는 원본 그대로
# ---------------------------------------------------------------------------


def test_build_rank_item_rounds_pyeong_but_keeps_other_fields_raw():
    row = {
        "apt_name": "테스트단지",
        "exclusive_area_m2": 82.63,
        "pyeong": 25.71,
        "floor": 5,
        "trade_amount": 123456.78,
    }

    item = svc._build_rank_item(row)

    assert item["pyeong"] == 26  # round(25.71) -> 26, 소수점 없는 정수
    assert isinstance(item["pyeong"], int)
    assert item["exclusive_area_m2"] == 82.63  # 원본 그대로(재계산 없음)
    assert item["trade_amount"] == 123456.78  # 원본 그대로(재계산 없음)


def test_get_apt_recent_rank_returns_integer_pyeong_end_to_end(monkeypatch):
    monkeypatch.setattr(svc.duckdb_client, "get_connection", lambda: MagicMock())
    row = _row("테스트단지", 50000)
    row["pyeong"] = 18.46
    monkeypatch.setattr(svc, "_fetch_rows", lambda *a, **k: [row])

    result = svc.get_apt_recent_rank(sgg_cd="11680", dong_cd="10300")

    assert result["top"][0]["pyeong"] == 18  # round(18.46) -> 18
    assert isinstance(result["top"][0]["pyeong"], int)
