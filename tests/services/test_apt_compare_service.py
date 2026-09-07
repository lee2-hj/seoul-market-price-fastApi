"""apt_compare_service의 base_date 폴백 반영 + 기존 grp 값 변환("40" -> "40+") 회귀 테스트.

+ 실버(fact_apt_transactions) Fallback 회귀 테스트: dm_apt_pyeong_price/dm_apt_flr_price가
apt_mkt_trends와 동일하게 ~85~90일 롤링 보존 마트라 특정 단지+그룹의 마지막 실거래가 그보다
오래되면 골드에서 영영 못 찾는 실제 사례(강남구 개포동 '개포자이' 11680/10300/0012/0002)를
재현한다."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.core import cache as cache_module
from app.services import apt_compare_service as svc


@pytest.fixture(autouse=True)
def _clear_silver_fallback_cache():
    cache_module.clear(svc.CACHE_NAMESPACE)
    yield
    cache_module.clear(svc.CACHE_NAMESPACE)


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


def test_compare_apartments_retries_transient_storage_error_on_gold_fetch(monkeypatch):
    """골드 마트 조회(base_date 탐색+실제 read) 중 스토리지 일시적 IO 오류가 나면, 성공할
    때까지(최대 GOLD_QUERY_RETRY_ATTEMPTS회) 매번 새 커넥션으로 재시도해야 한다."""
    monkeypatch.setattr(svc.duckdb_client, "resolve_base_date_for_filter", lambda *a, **k: "2026-08-27")
    monkeypatch.setattr(svc.duckdb_client, "rows_to_dicts", lambda result: [{"cgg_cd": "11500"}])
    monkeypatch.setattr(svc.time, "sleep", lambda *_: None)

    attempts = {"n": 0}

    class _FlakyCon:
        def execute(self, query, params=None):
            attempts["n"] += 1
            if attempts["n"] < 2:
                raise IOError("Could not connect to server error for HTTP GET")
            return object()

        def close(self):
            pass

    monkeypatch.setattr(svc.duckdb_client, "get_connection", lambda: _FlakyCon())

    base_date, items = svc.compare_apartments(
        cgg_cd="11500", stdg_cd="10300", bldg_nm=None, mno="1", sno="0",
        query_type="pyeong", grp="30",
    )

    assert base_date == "2026-08-27"
    assert items == [{"cgg_cd": "11500"}]
    assert attempts["n"] == 2


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


# ---------------------------------------------------------------------------
# fetch_recent_supply_pyeong: 스토리지 일시적 IO 오류 재시도 회귀 테스트
# (실제 사례: cgg_cd=11680/stdg_cd=10300/bldg_nm=개포2차현대아파트(220) 조회 시
# resolve_base_date_for_filter 내부에서 MinIO 연결 오류로 500이 발생했음)
# ---------------------------------------------------------------------------


def test_fetch_recent_supply_pyeong_retries_transient_storage_error(monkeypatch):
    """처음 두 번은 일시적 IO 오류가 나고 세 번째 시도에서 성공하면, 그 값을 그대로 반환해야
    한다(매 시도마다 새 커넥션을 사용)."""
    monkeypatch.setattr(svc.duckdb_client, "resolve_base_date_for_filter", lambda *a, **k: "2026-08-27")
    monkeypatch.setattr(svc.time, "sleep", lambda *_: None)

    attempts = {"n": 0}

    class _FlakyCon:
        def execute(self, query, params=None):
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise IOError("Could not connect to server error for HTTP GET")

            class _R:
                def fetchone(self):
                    return (15.5,)

            return _R()

        def close(self):
            pass

    monkeypatch.setattr(svc.duckdb_client, "get_connection", lambda: _FlakyCon())

    result = svc.fetch_recent_supply_pyeong(cgg_cd="11680", stdg_cd="10300", bldg_nm=None, mno="1", sno="0")

    assert result == 15.5
    assert attempts["n"] == 3


def test_fetch_recent_supply_pyeong_raises_after_exhausting_retries(monkeypatch):
    """모든 재시도가 실패하면 마지막 예외를 그대로 올린다 - 호출부(엔드포인트)가 이를 잡아
    None으로 대체하는 건 엔드포인트의 책임이다."""
    monkeypatch.setattr(svc.duckdb_client, "resolve_base_date_for_filter", lambda *a, **k: "2026-08-27")
    monkeypatch.setattr(svc.time, "sleep", lambda *_: None)

    class _AlwaysFailCon:
        def execute(self, query, params=None):
            raise IOError("Could not connect to server error for HTTP GET")

        def close(self):
            pass

    monkeypatch.setattr(svc.duckdb_client, "get_connection", lambda: _AlwaysFailCon())

    with pytest.raises(IOError):
        svc.fetch_recent_supply_pyeong(cgg_cd="11680", stdg_cd="10300", bldg_nm=None, mno="1", sno="0")


# ---------------------------------------------------------------------------
# 실버(fact_apt_transactions) 레이어 Fallback
# ---------------------------------------------------------------------------


def test_pyeong_grp_label_buckets_by_ten_and_caps_at_40_plus():
    assert svc._pyeong_grp_label(5.0) == "10"
    assert svc._pyeong_grp_label(22.77) == "20"
    assert svc._pyeong_grp_label(27.54) == "20"
    assert svc._pyeong_grp_label(45.15) == "40+"
    assert svc._pyeong_grp_label(60.48) == "40+"


def test_flr_grp_label_matches_fixed_global_thresholds():
    """실측 확인된 dm_apt_flr_price 고정 임계값: LOW<=5, MID 6~15, HIGH>=16."""
    assert svc._flr_grp_label(-1) == "LOW"
    assert svc._flr_grp_label(5) == "LOW"
    assert svc._flr_grp_label(6) == "MID"
    assert svc._flr_grp_label(15) == "MID"
    assert svc._flr_grp_label(16) == "HIGH"
    assert svc._flr_grp_label(52) == "HIGH"


def _fake_gold_empty_con():
    """골드 마트 조회 결과가 항상 빈 리스트인 가짜 커넥션(rows_to_dicts를 몽키패치하지 않고도
    con.execute()만으로 충분하도록, duckdb_client.rows_to_dicts가 처리 가능한 빈 결과를 반환)."""

    class _FakeCursor:
        description = [("cgg_cd",)]

        def fetchall(self):
            return []

    class _FakeCon:
        def execute(self, query, params=None):
            return _FakeCursor()

        def close(self):
            pass

    return _FakeCon()


def test_compare_apartments_falls_back_to_silver_when_gold_has_no_row(monkeypatch, caplog):
    """개포자이(11680/10300/0012/0002) 재현: 골드(dm_apt_pyeong_price) 전체 파티션에 매칭 row가
    없어도(마트 보존 기간 밖) 실버에서 이 단지+grp의 마지막 거래일 기준 90일 집계를 찾아야 한다."""
    import logging

    monkeypatch.setattr(svc.duckdb_client, "get_connection", lambda: _fake_gold_empty_con())
    monkeypatch.setattr(svc.duckdb_client, "resolve_base_date_for_filter", lambda *a, **k: None)
    monkeypatch.setattr(svc.duckdb_client, "resolve_base_date", lambda *a, **k: "2026-09-07")

    def fake_silver_row(con, cgg_cd, stdg_cd, bldg_nm, mno, sno, query_type, grp):
        assert (cgg_cd, stdg_cd, bldg_nm, mno, sno, query_type, grp) == (
            "11680", "10300", "개포자이", "0012", "0002", "pyeong", "40+",
        )
        return {
            "cgg_cd": cgg_cd, "cgg_nm": "강남구", "stdg_cd": stdg_cd, "stdg_nm": "개포동",
            "bldg_nm": bldg_nm, "latitude": None, "longitude": None, "is_exact_location": None,
            "mno": mno, "sno": sno, "updated_at": None,
            "pyeong_grp": "40+", "deal_cnt": 2, "total_thing_amt": 506000, "total_pyeong_amt": 8814,
            "recent_thing_amt": 320000, "recent_pyeong_amt": 5291,
            "recent_deal_date": "2026-05-15", "recent_supply_pyeong": 60.48,
        }

    monkeypatch.setattr(svc, "_fetch_silver_group_row", fake_silver_row)

    with caplog.at_level(logging.INFO, logger="app.services.apt_compare_service"):
        base_date, items = svc.compare_apartments(
            cgg_cd="11680", stdg_cd="10300", bldg_nm="개포자이", mno="0012", sno="0002",
            query_type="pyeong", grp="40",
        )

    assert base_date == "2026-05-15"
    assert len(items) == 1
    assert items[0]["deal_cnt"] == 2
    assert items[0]["pyeong_grp"] == "40+"
    assert any("Silver fallback used" in r.message for r in caplog.records)


def test_fetch_silver_group_row_returns_none_without_bldg_nm_or_grp():
    """bldg_nm이 없으면(선택 파라미터) 실버에서 단지를 정확히 특정할 수 없고, grp가 없으면
    버킷 필터를 적용할 수 없으므로 두 경우 모두 스토리지 조회 없이 즉시 None을 반환해야 한다."""
    assert svc._fetch_silver_group_row(
        MagicMock(), "11680", "10300", None, "0012", "0002", "pyeong", "40+"
    ) is None
    assert svc._fetch_silver_group_row(
        MagicMock(), "11680", "10300", "개포자이", "0012", "0002", "pyeong", ""
    ) is None


def test_compare_apartments_silver_fallback_skipped_without_bldg_nm(monkeypatch):
    """bldg_nm이 없으면(선택 파라미터) 실버 폴백은 (실제 가드 로직에 의해) 항상 빈 리스트로
    끝나야 한다 - _fetch_silver_group_row를 몽키패치하지 않고 실제 함수 그대로 검증한다."""
    monkeypatch.setattr(svc.duckdb_client, "get_connection", lambda: _fake_gold_empty_con())
    monkeypatch.setattr(svc.duckdb_client, "resolve_base_date_for_filter", lambda *a, **k: None)
    monkeypatch.setattr(svc.duckdb_client, "resolve_base_date", lambda *a, **k: "2026-09-07")

    base_date, items = svc.compare_apartments(
        cgg_cd="11680", stdg_cd="10300", bldg_nm=None, mno="0012", sno="0002",
        query_type="pyeong", grp="40",
    )

    assert items == []
    assert base_date == "2026-09-07"


def test_compare_apartments_silver_fallback_result_is_cached(monkeypatch):
    """동일 단지+그룹을 연속 2회 조회하면 두 번째 호출은 캐시 히트로 처리되어 실버 스캔
    (_fetch_silver_group_row)이 다시 실행되지 않아야 한다."""
    monkeypatch.setattr(svc.duckdb_client, "get_connection", lambda: _fake_gold_empty_con())
    monkeypatch.setattr(svc.duckdb_client, "resolve_base_date_for_filter", lambda *a, **k: None)
    monkeypatch.setattr(svc.duckdb_client, "resolve_base_date", lambda *a, **k: "2026-09-07")

    calls: list[int] = []

    def fake_silver_row(con, cgg_cd, stdg_cd, bldg_nm, mno, sno, query_type, grp):
        calls.append(1)
        return {
            "cgg_cd": cgg_cd, "cgg_nm": "강남구", "stdg_cd": stdg_cd, "stdg_nm": "개포동",
            "bldg_nm": bldg_nm, "latitude": None, "longitude": None, "is_exact_location": None,
            "mno": mno, "sno": sno, "updated_at": None,
            "pyeong_grp": grp, "deal_cnt": 2, "total_thing_amt": 506000, "total_pyeong_amt": 8814,
            "recent_thing_amt": 320000, "recent_pyeong_amt": 5291,
            "recent_deal_date": "2026-05-15", "recent_supply_pyeong": 60.48,
        }

    monkeypatch.setattr(svc, "_fetch_silver_group_row", fake_silver_row)

    kwargs = dict(
        cgg_cd="11680", stdg_cd="10300", bldg_nm="개포자이", mno="0012", sno="0002",
        query_type="pyeong", grp="40",
    )
    result_1 = svc.compare_apartments(**kwargs)
    result_2 = svc.compare_apartments(**kwargs)

    assert result_1 == result_2
    assert len(calls) == 1  # 두 번째 호출은 캐시 히트라 실버 스캔이 다시 실행되지 않는다.
