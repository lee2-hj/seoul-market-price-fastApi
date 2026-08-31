"""region_apt_compare_service.compare_region_apts()의 독립 2-엔티티(단지1/단지2) base_date
폴백 회귀 테스트. 한쪽 단지만 소급되고 다른 쪽은 매칭 자체가 없어 빈 객체({})로 남는 케이스를
포함한다(명세서 5항, Phase 5 세 번째 테스트 항목)."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.services import region_apt_compare_service as svc


def test_compare_region_apts_one_falls_back_other_has_no_match(monkeypatch):
    def fake_resolve_for_filter(con, mart_table, where_sql, params, **kwargs):
        if params.get("apt_nm") == "아파트1":
            return "2026-08-27"  # 단지1: 과거로 소급되어 매칭됨
        return None  # 단지2: max_lookback 안에서 매칭 자체가 없음

    monkeypatch.setattr(svc.duckdb_client, "get_connection", lambda: MagicMock())
    monkeypatch.setattr(svc.duckdb_client, "resolve_base_date_for_filter", fake_resolve_for_filter)
    monkeypatch.setattr(svc.duckdb_client, "resolve_base_date", lambda *a, **k: "2026-08-30")

    def fake_fetch_apt_row(con, base_date, cgg_cd, bjd_cd, apt_nm, mno, sno):
        if apt_nm == "아파트1":
            return {
                "apt_name": "아파트1",
                "trade_count": 3,
                "total_trade_amount": 30000,
                "total_price_per_pyeong": 9000,
                "total_pyeong": 90,
                "latest_trade_pyeong": 30.0,
                "household_count": 200,
                "build_year": 2010,
                "use_approval_date": "2010-05-01",
            }
        return None  # 단지2: 최근 90일 실거래 매칭 row 자체가 없음

    monkeypatch.setattr(svc, "_fetch_apt_row", fake_fetch_apt_row)

    group_1, group_2 = svc.compare_region_apts(
        cgg_cd_1="11500",
        bjd_cd_1="10300",
        apt_nm_1="아파트1",
        mno_1="1",
        sno_1="0",
        cgg_cd_2="11500",
        bjd_cd_2="10300",
        apt_nm_2="아파트2",
        mno_2="2",
        sno_2="0",
    )

    assert group_1["apt_name"] == "아파트1"
    assert group_1["base_date"] == "2026-08-27"
    # 단지2는 매칭되는 row가 없으므로 base_date를 포함하지 않는 빈 객체여야 한다.
    assert group_2 == {}


def test_compare_region_apts_matched_but_zero_trade_count_omits_base_date(monkeypatch):
    """단지를 찾긴 했지만(row 존재) 최근 90일 거래가 0건이면 기존 관례대로 빈 객체({})를 유지한다."""
    monkeypatch.setattr(svc.duckdb_client, "get_connection", lambda: MagicMock())
    monkeypatch.setattr(svc.duckdb_client, "resolve_base_date_for_filter", lambda *a, **k: "2026-08-30")
    monkeypatch.setattr(svc.duckdb_client, "resolve_base_date", lambda *a, **k: "2026-08-30")
    monkeypatch.setattr(
        svc, "_fetch_apt_row", lambda *a, **k: {"apt_name": "아파트1", "trade_count": 0}
    )

    group_1, group_2 = svc.compare_region_apts(
        cgg_cd_1="11500", bjd_cd_1="10300", apt_nm_1="아파트1", mno_1="1", sno_1="0",
        cgg_cd_2="11500", bjd_cd_2="10300", apt_nm_2="아파트1", mno_2="1", sno_2="0",
    )

    assert group_1 == {}
    assert group_2 == {}
