"""apt_price_service.get_top_bottom()의 base_date 폴백 반영 회귀 테스트.

duckdb_client.resolve_base_date_for_filter()/resolve_base_date() 자체는
tests/core/test_duckdb_client.py에서 이미 검증했으므로, 여기서는 서비스가
"naive 최신 base_date"가 아니라 "폴백 탐색 결과"를 실제로 사용하는지만 격리해서 확인한다.
DB 접속(get_connection)과 내부 조회 헬퍼는 모두 monkeypatch로 대체해 MinIO 없이 실행한다.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from app.services import apt_price_service


def _patch_common(monkeypatch, *, filter_result: str | None, naive_latest: str):
    monkeypatch.setattr(apt_price_service.duckdb_client, "get_connection", lambda: MagicMock())
    monkeypatch.setattr(
        apt_price_service.duckdb_client,
        "resolve_base_date_for_filter",
        lambda *args, **kwargs: filter_result,
    )
    monkeypatch.setattr(
        apt_price_service.duckdb_client, "resolve_base_date", lambda *args, **kwargs: naive_latest
    )
    monkeypatch.setattr(apt_price_service, "_count_rows", lambda *args, **kwargs: 2)
    monkeypatch.setattr(apt_price_service, "_fetch_ranked", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        apt_price_service, "_fetch_summary", lambda *args, **kwargs: (2, 1000, 100)
    )


def test_get_top_bottom_uses_fallback_base_date_when_filter_matches_past_partition(monkeypatch):
    """최신 파티션(naive)엔 지역 조건 매칭 데이터가 없고 과거 파티션에만 있는 경우,
    응답 base_date는 소급된 날짜여야 한다(최신 날짜가 그대로 노출되면 회귀)."""
    _patch_common(monkeypatch, filter_result="2026-08-27", naive_latest="2026-08-30")

    base_date, *_ = apt_price_service.get_top_bottom(
        region_cgg_cd="11680", region_stdg_cd=None, metric_type="pyeong"
    )

    assert base_date == "2026-08-27"


def test_get_top_bottom_falls_back_to_naive_latest_when_no_partition_matches(monkeypatch):
    """조건에 매칭되는 파티션이 하나도 없으면(resolve_base_date_for_filter → None),
    기존과 동일하게 resolve_base_date()의 최신 파티션을 사용해야 한다."""
    _patch_common(monkeypatch, filter_result=None, naive_latest="2026-08-30")

    base_date, *_ = apt_price_service.get_top_bottom(
        region_cgg_cd="00000", region_stdg_cd=None, metric_type="pyeong"
    )

    assert base_date == "2026-08-30"


def test_get_top_bottom_passes_where_clause_built_from_region_filters(monkeypatch):
    """resolve_base_date_for_filter가 apt_price_service._build_where_clause로 만든 조건을
    그대로 전달받는지 확인한다(엉뚱한 조건으로 존재 확인을 하면 폴백이 무의미해진다)."""
    captured: dict = {}

    def fake_resolve_for_filter(con, mart_table, where_sql, params, **kwargs):
        captured["mart_table"] = mart_table
        captured["where_sql"] = where_sql
        captured["params"] = params
        return "2026-08-30"

    monkeypatch.setattr(apt_price_service.duckdb_client, "get_connection", lambda: MagicMock())
    monkeypatch.setattr(
        apt_price_service.duckdb_client, "resolve_base_date_for_filter", fake_resolve_for_filter
    )
    monkeypatch.setattr(
        apt_price_service.duckdb_client, "resolve_base_date", lambda *a, **k: "2026-08-30"
    )
    monkeypatch.setattr(apt_price_service, "_count_rows", lambda *a, **k: 0)
    monkeypatch.setattr(apt_price_service, "_fetch_ranked", lambda *a, **k: [])
    monkeypatch.setattr(apt_price_service, "_fetch_summary", lambda *a, **k: (0, 0, 0))

    apt_price_service.get_top_bottom(
        region_cgg_cd="11680", region_stdg_cd="10300", metric_type="pyeong"
    )

    assert captured["mart_table"] == apt_price_service.MART_TABLE
    assert captured["params"] == {"cgg_cd": "11680", "stdg_cd": "10300"}
    assert "cgg_cd = $cgg_cd" in captured["where_sql"]
    assert "stdg_cd = $stdg_cd" in captured["where_sql"]
