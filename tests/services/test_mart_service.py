"""mart_service.compare_dong_pyeong()의 독립 2-엔티티(지역1/지역2) base_date 폴백 회귀 테스트.

명세서 5항 4번: 지역1/지역2는 서로 독립적으로 폴백을 탐색하며, 한쪽만 소급되고 다른 쪽은
최신 날짜를 그대로 쓰는 것이 정상 동작이다.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from app.services import mart_service


def test_compare_dong_pyeong_regions_fallback_independently(monkeypatch):
    """region1은 최신 파티션에 매칭 데이터가 있어 그대로 최신 날짜를 쓰고,
    region2만 매칭 데이터가 없어 과거로 소급되는 케이스."""

    def fake_resolve_for_filter(con, mart_table, where_sql, params, **kwargs):
        # region1_where/region2_where는 _build_where_clause가 만든 조건이며 cgg_cd 값으로 구분된다.
        if params.get("cgg_cd") == "11680":
            return "2026-08-30"  # region1: 최신 그대로
        if params.get("cgg_cd") == "11650":
            return "2026-08-27"  # region2: 소급됨
        raise AssertionError(f"예상하지 못한 params: {params}")

    monkeypatch.setattr(mart_service.duckdb_client, "get_connection", lambda: MagicMock())
    monkeypatch.setattr(
        mart_service.duckdb_client, "resolve_base_date_for_filter", fake_resolve_for_filter
    )
    monkeypatch.setattr(
        mart_service.duckdb_client, "resolve_base_date", lambda *a, **k: "2026-08-30"
    )
    monkeypatch.setattr(mart_service, "_fetch_region_rows", lambda con, base_date, *a, **k: [])
    monkeypatch.setattr(
        mart_service, "_fetch_region_summary", lambda con, base_date, *a, **k: (0, 0, 0)
    )

    (
        base_date,
        region1_base_date,
        region2_base_date,
        region1_items,
        region2_items,
        region1_summary,
        region2_summary,
    ) = mart_service.compare_dong_pyeong(
        region1_cgg_cd="11680",
        region1_stdg_cd=None,
        region2_cgg_cd="11650",
        region2_stdg_cd=None,
    )

    assert region1_base_date == "2026-08-30"
    assert region2_base_date == "2026-08-27"
    # 하위 호환용 최상위 base_date는 두 지역 중 더 최신인 날짜여야 한다.
    assert base_date == "2026-08-30"


def test_compare_dong_pyeong_both_regions_fall_back_to_naive_latest(monkeypatch):
    """둘 다 매칭되는 과거 파티션이 없으면 각자 resolve_base_date()의 최신 파티션으로 폴백한다."""
    monkeypatch.setattr(mart_service.duckdb_client, "get_connection", lambda: MagicMock())
    monkeypatch.setattr(
        mart_service.duckdb_client, "resolve_base_date_for_filter", lambda *a, **k: None
    )
    monkeypatch.setattr(
        mart_service.duckdb_client, "resolve_base_date", lambda *a, **k: "2026-08-30"
    )
    monkeypatch.setattr(mart_service, "_fetch_region_rows", lambda *a, **k: [])
    monkeypatch.setattr(mart_service, "_fetch_region_summary", lambda *a, **k: (0, 0, 0))

    base_date, region1_base_date, region2_base_date, *_ = mart_service.compare_dong_pyeong(
        region1_cgg_cd="00000",
        region1_stdg_cd=None,
        region2_cgg_cd="00001",
        region2_stdg_cd=None,
    )

    assert region1_base_date == region2_base_date == base_date == "2026-08-30"
