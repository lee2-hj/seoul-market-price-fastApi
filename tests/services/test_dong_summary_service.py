"""dong_summary_service.get_dong_summary()의 base_date 폴백 반영 회귀 테스트."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.services import dong_summary_service


def _patch_common(monkeypatch, *, filter_result, naive_latest):
    monkeypatch.setattr(dong_summary_service.duckdb_client, "get_connection", lambda: MagicMock())
    monkeypatch.setattr(
        dong_summary_service.duckdb_client,
        "resolve_base_date_for_filter",
        lambda *a, **k: filter_result,
    )
    monkeypatch.setattr(
        dong_summary_service.duckdb_client, "resolve_base_date", lambda *a, **k: naive_latest
    )
    monkeypatch.setattr(dong_summary_service, "_fetch_rows", lambda *a, **k: [])


def test_get_dong_summary_uses_fallback_base_date(monkeypatch):
    _patch_common(monkeypatch, filter_result="2026-08-27", naive_latest="2026-08-30")

    base_date, groups = dong_summary_service.get_dong_summary(region_cgg="11680")

    assert base_date == "2026-08-27"
    assert groups == {}


def test_get_dong_summary_supports_no_region_filter(monkeypatch):
    """region_cgg가 없으면 where_sql이 빈 문자열이 되는데, 이 경우에도
    resolve_base_date_for_filter가 정상적으로 호출/사용되어야 한다."""
    captured: dict = {}

    def fake_resolve_for_filter(con, mart_table, where_sql, params, **kwargs):
        captured["where_sql"] = where_sql
        captured["params"] = params
        return "2026-08-29"

    monkeypatch.setattr(dong_summary_service.duckdb_client, "get_connection", lambda: MagicMock())
    monkeypatch.setattr(
        dong_summary_service.duckdb_client, "resolve_base_date_for_filter", fake_resolve_for_filter
    )
    monkeypatch.setattr(
        dong_summary_service.duckdb_client, "resolve_base_date", lambda *a, **k: "2026-08-30"
    )
    monkeypatch.setattr(dong_summary_service, "_fetch_rows", lambda *a, **k: [])

    base_date, _ = dong_summary_service.get_dong_summary(region_cgg=None)

    assert base_date == "2026-08-29"
    assert captured["where_sql"] == ""
    assert captured["params"] == {}


def test_get_dong_summary_falls_back_to_naive_latest_when_no_match(monkeypatch):
    _patch_common(monkeypatch, filter_result=None, naive_latest="2026-08-30")

    base_date, _ = dong_summary_service.get_dong_summary(region_cgg="00000")

    assert base_date == "2026-08-30"
