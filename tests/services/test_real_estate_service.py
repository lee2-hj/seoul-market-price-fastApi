"""real_estate_service.get_latest_listings()의 RAW 파티션 base_date 폴백 회귀 테스트."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.services import real_estate_service


def _fake_con_returning_empty():
    con = MagicMock()
    con.execute.return_value.description = [("apt_name",)]
    con.execute.return_value.fetchall.return_value = []
    return con


def test_get_latest_listings_uses_fallback_partition_when_naive_latest_has_no_apt_rows(monkeypatch):
    """오늘(나이브 최신) 파티션 폴더는 있지만 그 날 BLDG_USG='아파트' row가 0건이면,
    아파트 거래가 있는 과거 day 파티션으로 소급되어야 한다."""
    monkeypatch.setattr(real_estate_service.duckdb_client, "get_connection", lambda: _fake_con_returning_empty())
    monkeypatch.setattr(
        real_estate_service.duckdb_client,
        "resolve_latest_date_partition_for_filter",
        lambda *a, **k: ("2026", "08", "27"),
    )
    monkeypatch.setattr(
        real_estate_service.duckdb_client,
        "resolve_latest_date_partition",
        lambda *a, **k: ("2026", "08", "30"),
    )
    monkeypatch.setattr(real_estate_service.duckdb_client, "rows_to_dicts", lambda result: [])

    base_date, items = real_estate_service.get_latest_listings()

    assert base_date == "2026-08-27"
    assert items == []


def test_get_latest_listings_falls_back_to_naive_when_no_apt_partition_matches(monkeypatch):
    monkeypatch.setattr(real_estate_service.duckdb_client, "get_connection", lambda: _fake_con_returning_empty())
    monkeypatch.setattr(
        real_estate_service.duckdb_client, "resolve_latest_date_partition_for_filter", lambda *a, **k: None
    )
    monkeypatch.setattr(
        real_estate_service.duckdb_client,
        "resolve_latest_date_partition",
        lambda *a, **k: ("2026", "08", "30"),
    )
    monkeypatch.setattr(real_estate_service.duckdb_client, "rows_to_dicts", lambda result: [])

    base_date, items = real_estate_service.get_latest_listings()

    assert base_date == "2026-08-30"


def test_get_latest_listings_passes_apt_only_filter_to_fallback(monkeypatch):
    """resolve_latest_date_partition_for_filter에 BLDG_USG='아파트' 조건이 실제로 전달되는지 확인한다."""
    captured: dict = {}

    def fake_fallback(con, dataset, where_sql, params, **kwargs):
        captured["dataset"] = dataset
        captured["where_sql"] = where_sql
        captured["params"] = params
        return ("2026", "08", "30")

    monkeypatch.setattr(real_estate_service.duckdb_client, "get_connection", lambda: _fake_con_returning_empty())
    monkeypatch.setattr(
        real_estate_service.duckdb_client, "resolve_latest_date_partition_for_filter", fake_fallback
    )
    monkeypatch.setattr(real_estate_service.duckdb_client, "rows_to_dicts", lambda result: [])

    real_estate_service.get_latest_listings()

    assert captured["dataset"] == real_estate_service.DATASET
    assert captured["params"] == {"bldg_usg": "아파트"}
    assert "BLDG_USG = $bldg_usg" in captured["where_sql"]
