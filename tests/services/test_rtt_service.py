"""rtt_service.get_rtt_summary()의 range-앵커형 base_date 폴백(90일 창 이동) 회귀 테스트."""

from __future__ import annotations

import logging
from datetime import date, timedelta
from unittest.mock import MagicMock

import pytest

from app.core import cache as cache_module
from app.services import rtt_service


@pytest.fixture(autouse=True)
def _clear_anchor_fallback_cache():
    """rtt_service의 앵커/실버 폴백 캐시(전역 dict)가 테스트 간에 남아있지 않도록 정리한다."""
    cache_module.clear(rtt_service.CACHE_NAMESPACE)
    yield
    cache_module.clear(rtt_service.CACHE_NAMESPACE)


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


def test_get_rtt_summary_falls_back_to_silver_when_mart_retention_window_missed(monkeypatch, caplog):
    """RTT는 최근 ~103일만 보존하는 롤링 마트라(실측: 2026-05-24~2026-09-04), 지역의 마지막
    실거래가 그보다 오래되면 resolve_recent_match_date로도 영영 못 찾는다(실측으로 확인된 실제
    케이스: sgg_cd=11110/dong_cd=16200 - RTT엔 없지만 fact_apt_transactions 원본에는 9건의
    실거래가 있음, 마지막 거래일 2026-05-22). 이 경우 실버(fact_apt_transactions) 원본까지
    온디맨드로 내려가 정상 집계해야 한다."""
    monkeypatch.setattr(rtt_service.duckdb_client, "get_connection", lambda: MagicMock())
    monkeypatch.setattr(rtt_service, "_fetch_rows", lambda *a, **k: [])
    # RTT 마트 자체에는 매칭이 전혀 없다(보존 기간 밖).
    monkeypatch.setattr(rtt_service.duckdb_client, "resolve_recent_match_date", lambda *a, **k: None)

    silver_last_date = date(2026, 5, 22)
    silver_rows = [
        {
            "sgg_cd": "11110", "sgg_nm": "종로구", "dong_cd": "16200", "dong_nm": "신당동",
            "apt_name": "테스트단지", "mno": "1", "sno": "0",
            "deal_date": silver_last_date.isoformat(), "floor": 5,
            "trade_amount": 50000, "pyeong": 25.0, "exclusive_area_m2": 82.6, "trade_count": 1,
        },
        {
            "sgg_cd": "11110", "sgg_nm": "종로구", "dong_cd": "16200", "dong_nm": "신당동",
            "apt_name": "테스트단지2", "mno": "2", "sno": "0",
            "deal_date": (silver_last_date - timedelta(days=10)).isoformat(), "floor": 3,
            "trade_amount": 40000, "pyeong": 20.0, "exclusive_area_m2": 66.1, "trade_count": 1,
        },
    ]

    def fake_fetch_silver_rows(con, sgg_cd, dong_cd):
        assert (sgg_cd, dong_cd) == ("11110", "16200")
        return silver_rows

    monkeypatch.setattr(rtt_service, "_fetch_silver_rows", fake_fetch_silver_rows)

    with caplog.at_level(logging.INFO, logger="app.services.rtt_service"):
        result = rtt_service.get_rtt_summary(sgg_cd="11110", dong_cd="16200")

    assert result["period_end"] == silver_last_date
    assert result["sgg_nm"] == "종로구"
    assert result["dong_nm"] == "신당동"
    assert result["total_deal_cnt"] == 2
    assert result["total_trade_amount"] == 90000
    assert any("Silver fallback used" in r.message for r in caplog.records)


def test_get_rtt_summary_silver_fallback_result_is_cached(monkeypatch):
    """동일 지역을 연속 2회 조회하면 두 번째 호출은 캐시 히트로 처리되어 실버 스캔
    (_fetch_silver_rows)이 다시 실행되지 않아야 한다."""
    monkeypatch.setattr(rtt_service.duckdb_client, "get_connection", lambda: MagicMock())
    monkeypatch.setattr(rtt_service, "_fetch_rows", lambda *a, **k: [])
    monkeypatch.setattr(rtt_service.duckdb_client, "resolve_recent_match_date", lambda *a, **k: None)

    calls: list[int] = []

    def fake_fetch_silver_rows(con, sgg_cd, dong_cd):
        calls.append(1)
        return [
            {
                "sgg_cd": sgg_cd, "sgg_nm": "종로구", "dong_cd": dong_cd, "dong_nm": "신당동",
                "apt_name": "테스트단지", "mno": "1", "sno": "0",
                "deal_date": "2026-05-22", "floor": 5,
                "trade_amount": 50000, "pyeong": 25.0, "exclusive_area_m2": 82.6, "trade_count": 1,
            }
        ]

    monkeypatch.setattr(rtt_service, "_fetch_silver_rows", fake_fetch_silver_rows)

    kwargs = dict(sgg_cd="11110", dong_cd="16200")
    result_1 = rtt_service.get_rtt_summary(**kwargs)
    result_2 = rtt_service.get_rtt_summary(**kwargs)

    assert result_1["period_start"] == result_2["period_start"]
    assert result_1["total_deal_cnt"] == result_2["total_deal_cnt"] == 1
    assert len(calls) == 1  # 두 번째 호출은 캐시 히트라 실버 스캔이 다시 실행되지 않는다.


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


# ---------------------------------------------------------------------------
# _build_avg_pyeong_amount: 평균 평단가 신규 필드
# ---------------------------------------------------------------------------


def test_build_avg_pyeong_amount_averages_per_row_pyeong_price():
    rows = [
        {"trade_amount": 100000, "pyeong": 25.0, "trade_count": 1},  # 평단가 4000
        {"trade_amount": 90000, "pyeong": 30.0, "trade_count": 1},  # 평단가 3000
    ]

    result = rtt_service._build_avg_pyeong_amount(rows, total_deal_cnt=2)

    # (4000 + 3000) / 2 = 3500
    assert result == 3500


def test_build_avg_pyeong_amount_returns_zero_when_no_deals():
    assert rtt_service._build_avg_pyeong_amount([], total_deal_cnt=0) == 0


def test_get_rtt_summary_includes_avg_pyeong_amount(monkeypatch):
    """get_rtt_summary() 응답에 avg_pyeong_amount가 추가되고, 기존 필드는 그대로여야 한다."""
    monkeypatch.setattr(rtt_service.duckdb_client, "get_connection", lambda: MagicMock())
    monkeypatch.setattr(
        rtt_service, "_fetch_rows",
        lambda *a, **k: [
            {
                "trade_count": 1, "trade_amount": 100000, "deal_date": "2026-08-30",
                "sgg_nm": "강남구", "dong_nm": "역삼동", "apt_name": "테스트", "mno": "1", "sno": "0",
                "floor": 5, "pyeong": 25.0, "exclusive_area_m2": 82.6,
            },
            {
                "trade_count": 1, "trade_amount": 90000, "deal_date": "2026-08-31",
                "sgg_nm": "강남구", "dong_nm": "역삼동", "apt_name": "테스트2", "mno": "2", "sno": "0",
                "floor": 3, "pyeong": 30.0, "exclusive_area_m2": 99.2,
            },
        ],
    )

    result = rtt_service.get_rtt_summary(sgg_cd="11680")

    assert result["avg_pyeong_amount"] == 3500
    # 기존 필드는 그대로 유지되어야 한다.
    assert result["total_deal_cnt"] == 2
    assert result["total_trade_amount"] == 190000
    assert result["avg_trade_amount"] == 95000
    assert result["max_trade_amount"] == 100000


# ---------------------------------------------------------------------------
# _build_volume_change_rate: 마트 적재 지연으로 불완전한 구간을 통째로 제외하는 회귀 테스트
# (실제 사례: sgg_cd=11680은 biweekly_trend가 [92,104,66,57,34,5]로 나오는데, 마지막 구간(5)은
# 실제 마지막 거래일(예: 2026-08-29)이 그 구간 종료일(2026-09-07)보다 훨씬 이전이라 아직 다
# 채워지지 않은 구간이다. 이 구간을 그대로 평균에 넣으면 -63.36%까지 왜곡되므로, 그래프
# (biweekly_trend)에서 눈으로도 "덜 찼다"고 보이는 마지막 구간은 비교에서 통째로 제외한다.)
# ---------------------------------------------------------------------------


def _bucket(deal_cnt: int, start_date: date, end_date: date) -> dict:
    return {
        "period_label": f"{start_date.isoformat()}/{end_date.isoformat()}",
        "start_date": start_date,
        "end_date": end_date,
        "deal_cnt": deal_cnt,
        "avg_trade_amount": 0,
    }


def _six_buckets(counts: list[int]) -> list[dict]:
    """실제 응답과 동일하게, 2026-06-10~2026-09-07(90일)을 15일씩 6구간으로 나눈
    biweekly_trend 형태를 만든다."""
    assert len(counts) == 6
    start = date(2026, 6, 10)
    buckets = []
    for i, cnt in enumerate(counts):
        bucket_start = start + timedelta(days=15 * i)
        bucket_end = bucket_start + timedelta(days=14)
        buckets.append(_bucket(cnt, bucket_start, bucket_end))
    return buckets


def test_volume_change_rate_excludes_incomplete_trailing_bucket_entirely():
    """실제 재현: 마지막 구간(2026-08-24~09-07, 5건)의 종료일이 실제 마지막 거래일
    (2026-08-29)보다 미래라 아직 다 채워지지 않은 구간이다. 이 구간을 완전히 제외하고,
    이전 3구간 평균 vs 완전한 나머지 2구간(57, 34) 평균으로 비교해야 한다."""
    biweekly_trend = _six_buckets([92, 104, 66, 57, 34, 5])
    data_end = date(2026, 8, 29)  # 마지막 구간(08-24~09-07) 종료일보다 이전 -> 그 구간 제외

    naive_rate = round((sum([57, 34, 5]) / 3 - sum([92, 104, 66]) / 3) / (sum([92, 104, 66]) / 3) * 100, 2)
    result = rtt_service._build_volume_change_rate(biweekly_trend, data_end)

    prior_avg = (92 + 104 + 66) / 3
    recent_avg = (57 + 34) / 2  # 마지막(불완전한) 구간 제외
    expected = round((recent_avg - prior_avg) / prior_avg * 100, 2)
    assert result == expected
    assert result == -47.9
    # 마지막 구간을 그대로 포함했다면(왜곡된 기존 방식) 훨씬 더 큰 감소로 나왔을 것.
    assert result > naive_rate


def test_volume_change_rate_keeps_all_buckets_when_mart_is_fully_up_to_date():
    """마트가 지연 없이 최신이면(마지막 구간 종료일까지 실제 데이터 존재) 6구간 전부 그대로
    비교에 사용한다(기존 방식과 동일한 결과)."""
    biweekly_trend = _six_buckets([92, 104, 66, 57, 34, 5])
    data_end = date(2026, 9, 7)  # 마지막 구간 종료일과 동일 -> 모든 구간이 완전함

    result = rtt_service._build_volume_change_rate(biweekly_trend, data_end)

    prior_avg = (92 + 104 + 66) / 3
    recent_avg = (57 + 34 + 5) / 3
    expected = round((recent_avg - prior_avg) / prior_avg * 100, 2)
    assert result == expected


def test_volume_change_rate_returns_none_when_all_recent_buckets_incomplete():
    """최근 3구간이 전부 불완전하면(실제 마지막 거래일이 이전 구간 안에 있음) 비교할 최근
    구간이 하나도 남지 않으므로 None을 반환한다."""
    biweekly_trend = _six_buckets([92, 104, 66, 57, 34, 5])
    data_end = date(2026, 7, 20)  # 이전 3구간(06-10~07-24) 안 -> 최근 3구간 전부 제외

    result = rtt_service._build_volume_change_rate(biweekly_trend, data_end)

    assert result is None


def test_volume_change_rate_returns_none_when_prior_average_is_zero():
    """이전 3구간 평균이 0이면(0으로 나누기 불가) None을 반환한다."""
    biweekly_trend = _six_buckets([0, 0, 0, 57, 34, 5])
    data_end = date(2026, 9, 7)

    result = rtt_service._build_volume_change_rate(biweekly_trend, data_end)

    assert result is None


def test_volume_change_rate_treats_all_buckets_as_complete_when_data_end_is_none():
    """rows 자체가 없어 data_end를 알 수 없으면(마트 지연 여부 판단 불가) 모든 구간을 완전한
    것으로 취급해 기존처럼 6구간 전부로 계산한다."""
    biweekly_trend = _six_buckets([10, 10, 10, 5, 5, 5])

    result = rtt_service._build_volume_change_rate(biweekly_trend, None)

    prior_avg = 10.0
    recent_avg = 5.0
    expected = round((recent_avg - prior_avg) / prior_avg * 100, 2)
    assert result == expected
