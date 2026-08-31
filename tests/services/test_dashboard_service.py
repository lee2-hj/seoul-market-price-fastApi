"""dashboard_service.get_dashboard()의 선호지역 위젯 3종 base_date 폴백 회귀 테스트.

명세서 5항 5번: 필터 없는 2개 위젯(seoul_top5_districts/price_change_top5)은 항상
latest_base_date(파티션 존재 여부 폴백)를 쓰고, resolved_cgg_cd로 필터링하는 3개 위젯만
그 지역 조건 기준으로 독립적으로 소급된 preference_base_date를 쓴다 — 한 응답 안에서
위젯 그룹별로 base_date가 갈라질 수 있다.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from app.services import dashboard_service


def test_get_dashboard_preference_widgets_fall_back_independently_of_naive_latest(monkeypatch):
    monkeypatch.setattr(dashboard_service.duckdb_client, "get_connection", lambda: MagicMock())
    monkeypatch.setattr(
        dashboard_service.duckdb_client, "resolve_base_date", lambda *a, **k: "2026-08-30"
    )

    captured: dict = {}

    def fake_resolve_for_filter(con, mart_table, where_sql, params, **kwargs):
        captured["where_sql"] = where_sql
        captured["params"] = params
        return "2026-08-27"  # 선호지역 조건은 과거로 소급됨

    monkeypatch.setattr(
        dashboard_service.duckdb_client, "resolve_base_date_for_filter", fake_resolve_for_filter
    )

    seen_base_dates: dict[str, str] = {}

    def record(name):
        def _fn(con, base_date, *a, **k):
            seen_base_dates[name] = base_date
            return []

        return _fn

    def fake_price_change_top5(con, base_date):
        seen_base_dates["price_change"] = base_date
        return {"rising_top5": [], "falling_top5": []}

    monkeypatch.setattr(dashboard_service, "_build_seoul_top5_districts", record("seoul_top5"))
    monkeypatch.setattr(dashboard_service, "_build_price_change_top5", fake_price_change_top5)
    monkeypatch.setattr(dashboard_service, "_build_preference_price_trend", record("price_trend"))
    monkeypatch.setattr(dashboard_service, "_build_top_trading_dongs", record("top_dongs"))
    monkeypatch.setattr(dashboard_service, "_build_top_trading_apts", record("top_apts"))

    result = dashboard_service.get_dashboard(cgg_cd="11680")

    assert result["preference_base_date"] == "2026-08-27"
    # 필터 없는 2개 위젯은 나이브 최신 날짜(2026-08-30) 그대로 사용.
    assert seen_base_dates["seoul_top5"] == "2026-08-30"
    assert seen_base_dates["price_change"] == "2026-08-30"
    # 선호지역 필터 3개 위젯은 소급된 날짜(2026-08-27)를 사용.
    assert seen_base_dates["price_trend"] == "2026-08-27"
    assert seen_base_dates["top_dongs"] == "2026-08-27"
    assert seen_base_dates["top_apts"] == "2026-08-27"
    # resolve_base_date_for_filter에는 resolved_cgg_cd 조건이 전달되어야 한다.
    assert captured["params"] == {"cgg_cd": "11680"}
    assert "cgg_cd = $cgg_cd" in captured["where_sql"]


def test_get_dashboard_preference_base_date_falls_back_to_naive_latest_when_no_match(monkeypatch):
    monkeypatch.setattr(dashboard_service.duckdb_client, "get_connection", lambda: MagicMock())
    monkeypatch.setattr(
        dashboard_service.duckdb_client, "resolve_base_date", lambda *a, **k: "2026-08-30"
    )
    monkeypatch.setattr(
        dashboard_service.duckdb_client, "resolve_base_date_for_filter", lambda *a, **k: None
    )
    monkeypatch.setattr(dashboard_service, "_build_seoul_top5_districts", lambda *a, **k: [])
    monkeypatch.setattr(
        dashboard_service, "_build_price_change_top5", lambda *a, **k: {"rising_top5": [], "falling_top5": []}
    )
    monkeypatch.setattr(dashboard_service, "_build_preference_price_trend", lambda *a, **k: [])
    monkeypatch.setattr(dashboard_service, "_build_top_trading_dongs", lambda *a, **k: [])
    monkeypatch.setattr(dashboard_service, "_build_top_trading_apts", lambda *a, **k: [])

    result = dashboard_service.get_dashboard(cgg_cd="00000")

    assert result["preference_base_date"] == "2026-08-30"


def test_get_dashboard_defaults_cgg_cd_when_blank(monkeypatch):
    monkeypatch.setattr(dashboard_service.duckdb_client, "get_connection", lambda: MagicMock())
    monkeypatch.setattr(
        dashboard_service.duckdb_client, "resolve_base_date", lambda *a, **k: "2026-08-30"
    )
    monkeypatch.setattr(
        dashboard_service.duckdb_client, "resolve_base_date_for_filter", lambda *a, **k: "2026-08-30"
    )
    monkeypatch.setattr(dashboard_service, "_build_seoul_top5_districts", lambda *a, **k: [])
    monkeypatch.setattr(
        dashboard_service, "_build_price_change_top5", lambda *a, **k: {"rising_top5": [], "falling_top5": []}
    )
    monkeypatch.setattr(dashboard_service, "_build_preference_price_trend", lambda *a, **k: [])
    monkeypatch.setattr(dashboard_service, "_build_top_trading_dongs", lambda *a, **k: [])
    monkeypatch.setattr(dashboard_service, "_build_top_trading_apts", lambda *a, **k: [])

    result = dashboard_service.get_dashboard(cgg_cd=None)

    assert result["cgg_cd"] == dashboard_service.DEFAULT_CGG_CD
