"""apt_compare_service의 base_date 폴백 반영 + 기존 grp 값 변환("40" -> "40+") 회귀 테스트."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.services import apt_compare_service as svc


def test_compare_apartments_uses_fallback_base_date(monkeypatch):
    monkeypatch.setattr(svc.duckdb_client, "get_connection", lambda: MagicMock())
    monkeypatch.setattr(
        svc.duckdb_client, "resolve_base_date_for_filter", lambda *a, **k: "2026-08-27"
    )
    monkeypatch.setattr(svc.duckdb_client, "resolve_base_date", lambda *a, **k: "2026-08-30")

    class _FakeCursor:
        description = [("cgg_cd",)]

        def fetchall(self):
            return []

    monkeypatch.setattr(svc.duckdb_client, "rows_to_dicts", lambda result: [])

    class _FakeCon:
        def execute(self, query, params=None):
            return _FakeCursor()

        def close(self):
            pass

    monkeypatch.setattr(svc.duckdb_client, "get_connection", lambda: _FakeCon())

    base_date, items = svc.compare_apartments(
        cgg_cd="11500",
        stdg_cd="10300",
        bldg_nm=None,
        mno="1",
        sno="0",
        query_type="pyeong",
        grp="30",
    )

    assert base_date == "2026-08-27"
    assert items == []


def test_compare_apartments_still_converts_pyeong_grp_40_to_40_plus(monkeypatch):
    """리팩터링 후에도 기존 관례("40" -> "40+")가 where 절 파라미터에 그대로 반영되어야 한다."""
    captured: dict = {}

    def fake_resolve_for_filter(con, mart_table, where_sql, params, **kwargs):
        captured["params"] = params
        return "2026-08-30"

    monkeypatch.setattr(svc.duckdb_client, "resolve_base_date_for_filter", fake_resolve_for_filter)
    monkeypatch.setattr(svc.duckdb_client, "resolve_base_date", lambda *a, **k: "2026-08-30")
    monkeypatch.setattr(svc.duckdb_client, "rows_to_dicts", lambda result: [])

    class _FakeCon:
        def execute(self, query, params=None):
            return object()

        def close(self):
            pass

    monkeypatch.setattr(svc.duckdb_client, "get_connection", lambda: _FakeCon())

    svc.compare_apartments(
        cgg_cd="11500", stdg_cd="10300", bldg_nm=None, mno="1", sno="0",
        query_type="pyeong", grp="40",
    )

    assert captured["params"]["grp"] == "40+"


def test_fetch_recent_supply_pyeong_uses_fallback_base_date(monkeypatch):
    captured: dict = {}

    def fake_resolve_for_filter(con, mart_table, where_sql, params, **kwargs):
        captured["mart_table"] = mart_table
        return "2026-08-27"

    monkeypatch.setattr(svc.duckdb_client, "resolve_base_date_for_filter", fake_resolve_for_filter)
    monkeypatch.setattr(svc.duckdb_client, "resolve_base_date", lambda *a, **k: "2026-08-30")

    class _FakeCon:
        def execute(self, query, params=None):
            class _R:
                def fetchone(self):
                    return (12.3,)

            return _R()

        def close(self):
            pass

    monkeypatch.setattr(svc.duckdb_client, "get_connection", lambda: _FakeCon())

    result = svc.fetch_recent_supply_pyeong(
        cgg_cd="11500", stdg_cd="10300", bldg_nm=None, mno="1", sno="0"
    )

    assert result == 12.3
    assert captured["mart_table"] == svc.MART_TABLE_BY_QUERY_TYPE["pyeong"]
