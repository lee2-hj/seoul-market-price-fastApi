"""rtt_service.get_rtt_summary() 회귀 테스트. 항상 나이브 90일 창(오늘 기준)의 base_date
데이터만 사용하며, 과거 base_date/실버(fact_apt_transactions) 레이어로 거슬러 올라가는 폴백은
없다."""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import MagicMock

from app.services import rtt_service


def test_get_rtt_summary_keeps_empty_result_when_no_match_at_all(monkeypatch):
    monkeypatch.setattr(rtt_service.duckdb_client, "get_connection", lambda: MagicMock())
    monkeypatch.setattr(rtt_service, "_fetch_rows", lambda *a, **k: [])

    result = rtt_service.get_rtt_summary(sgg_cd="00000")

    assert result["total_deal_cnt"] == 0
    assert result["recent_trades"] == []


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
