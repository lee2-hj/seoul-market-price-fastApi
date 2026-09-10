"""apt_trend_service 회귀 테스트.

1. get_apt_trend_summary()는 최신 base_date 파티션에 조건 매칭 데이터가 없으면, 날짜 조건을 뺀
   단지 필터(cgg_cd/stdg_cd/mno/sno/apt_name)만으로 과거 base_date 파티션을 훑어
   (resolve_base_date_for_filter) 매칭되는 가장 최근 파티션으로 폴백한다(그 base_date를 새
   anchor로 90일 창 전체를 다시 조회). lookback 내에 매칭 파티션이 없으면 기존처럼 빈 결과를
   그대로 반환한다(에러 아님). (실사용 리포트 재현: /apt-trend/summary?cgg_cd=11170&stdg_cd=13000
   &mno=0730&sno=0000&apt_name=이태원(이테크빌) — 거래 빈도가 낮아 naive 90일 창엔 안 걸리지만
   과거엔 거래가 있어 폴백 없이는 항상 빈 결과였던 회귀 케이스.)
2. _build_count_change_rate()의 표본 부족 필터링(MIN_TRADE_COUNT) 제거 이후 동작
   (backend-apt-trend-count-change-rate-fix 계획서 Phase 4 테스트 케이스).
3. _build_count_change_rate()의 0건 구간 짝짓기 제외(있는 데이터끼리만 비교) 회귀 테스트 -
   중간에 0건 구간이 끼어 있을 때 인접 비교로 인해 -100%에 가깝게 왜곡되던 문제 수정.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from app.services import apt_trend_service


# ---------------------------------------------------------------------------
# get_apt_trend_summary: base_date 폴백(resolve_base_date_for_filter)
# ---------------------------------------------------------------------------


def test_get_apt_trend_summary_keeps_empty_result_when_no_partition_matches_at_all(monkeypatch):
    """최신 파티션에도, lookback 내 과거 파티션 어디에도 조건 매칭 데이터가 없으면
    (resolve_base_date_for_filter -> None) 빈 결과를 그대로 반환해야 한다(에러 아님)."""
    monkeypatch.setattr(apt_trend_service.duckdb_client, "get_connection", lambda: MagicMock())
    monkeypatch.setattr(
        apt_trend_service.duckdb_client, "resolve_base_date_cached", lambda *a, **k: "2026-09-08"
    )
    monkeypatch.setattr(
        apt_trend_service.duckdb_client, "resolve_base_date_for_filter", lambda *a, **k: None
    )
    monkeypatch.setattr(apt_trend_service, "_fetch_rows", lambda *a, **k: [])

    result = apt_trend_service.get_apt_trend_summary(
        cgg_cd="00000", stdg_cd="00000", mno="0", sno="0", apt_name=None
    )

    assert result["count"] == 0
    assert result["data"] == []


def test_get_apt_trend_summary_falls_back_to_past_base_date_when_naive_window_empty(monkeypatch):
    """실사용 리포트 재현: 최신 파티션(naive, 오늘 기준 90일)엔 조건 매칭 데이터가 없고 과거
    base_date 파티션에만 있으면, 그 base_date를 새 anchor로 삼아 재조회해야 한다(거래 빈도가 낮은
    단지가 naive 90일 창엔 안 걸리지만 과거엔 거래가 있는 케이스 - 폴백 없이는 항상 빈 결과)."""
    row = {
        "cgg_cd": "11170",
        "cgg_nm": "용산구",
        "stdg_cd": "13000",
        "stdg_nm": "이태원동",
        "apt_name": "이태원(이테크빌)",
        "mno": "0730",
        "sno": "0000",
        "deal_date": "2026-06-01",
        "floor": 5,
        "trade_amount": 50000,
        "pyeong": 20,
        "trade_count": 1,
    }
    monkeypatch.setattr(apt_trend_service.duckdb_client, "get_connection", lambda: MagicMock())
    monkeypatch.setattr(
        apt_trend_service.duckdb_client, "resolve_base_date_cached", lambda *a, **k: "2026-09-08"
    )
    monkeypatch.setattr(
        apt_trend_service.duckdb_client, "resolve_base_date_for_filter", lambda *a, **k: "2026-06-15"
    )

    calls: list[str] = []

    def fake_fetch_rows(con, base_date, *args, **kwargs):
        calls.append(base_date)
        return [row] if base_date == "2026-06-15" else []

    monkeypatch.setattr(apt_trend_service, "_fetch_rows", fake_fetch_rows)

    result = apt_trend_service.get_apt_trend_summary(
        cgg_cd="11170", stdg_cd="13000", mno="0730", sno="0000", apt_name="이태원(이테크빌)"
    )

    assert calls == ["2026-09-08", "2026-06-15"]
    assert result["count"] == 1
    assert result["search_period"]["end_date"].isoformat() == "2026-06-15"


def test_get_apt_trend_summary_fallback_where_clause_has_no_date_condition(monkeypatch):
    """resolve_base_date_for_filter에는 날짜 조건 없이 단지 필터만 전달돼야 한다 - 과거 파티션은
    그 시점 기준 90일 윈도우라 naive 날짜 범위로 존재 확인하면 실제로 있는 데이터도 놓친다."""
    captured: dict = {}

    def fake_resolve_for_filter(con, mart_table, where_sql, params, **kwargs):
        captured["where_sql"] = where_sql
        captured["params"] = params
        return None

    monkeypatch.setattr(apt_trend_service.duckdb_client, "get_connection", lambda: MagicMock())
    monkeypatch.setattr(
        apt_trend_service.duckdb_client, "resolve_base_date_cached", lambda *a, **k: "2026-09-08"
    )
    monkeypatch.setattr(
        apt_trend_service.duckdb_client, "resolve_base_date_for_filter", fake_resolve_for_filter
    )
    monkeypatch.setattr(apt_trend_service, "_fetch_rows", lambda *a, **k: [])

    apt_trend_service.get_apt_trend_summary(
        cgg_cd="11170", stdg_cd="13000", mno="0730", sno="0000", apt_name="이태원(이테크빌)"
    )

    assert "deal_date" not in captured["where_sql"]
    assert captured["params"] == {
        "cgg_cd": "11170",
        "stdg_cd": "13000",
        "mno": "0730",
        "sno": "0000",
        "apt_name": "%이태원(이테크빌)%",
    }


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
