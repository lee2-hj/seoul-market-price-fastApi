"""app/core/duckdb_client.py의 base_date 조건부 폴백(소급 조회) 로직 회귀 테스트.

실제 MinIO(S3) 접속 없이도 검증할 수 있도록, DuckDB 커넥션을 흉내내는 FakeConnection으로
glob()/EXISTS 쿼리 결과를 스크립트로 지정해 list_base_dates()/resolve_base_date_for_filter()의
동작(조기 종료, 소급 순서, max_lookback 상한, 매칭 실패 시 None 반환, 폴백 발생 시 로깅)만
독립적으로 검증한다.
"""

from __future__ import annotations

import logging

import pytest

from app.core import duckdb_client

MART_TABLE = "dm_apt_price_avg"

# 최신순(내림차순)이 아니라 일부러 뒤섞어 넣어 glob() 원시 반환 순서와 무관하게
# list_base_dates()가 스스로 내림차순 정렬하는지도 함께 검증한다.
_PARTITION_PATHS = [
    (f"s3://warehouse/mart/{MART_TABLE}/base_date=2026-08-29/part.parquet",),
    (f"s3://warehouse/mart/{MART_TABLE}/base_date=2026-08-30/part.parquet",),
    (f"s3://warehouse/mart/{MART_TABLE}/base_date=2026-08-27/part.parquet",),
]


class _FakeResult:
    def __init__(self, value):
        self._value = value

    def fetchone(self):
        return self._value

    def fetchall(self):
        return self._value


class _FakeConnection:
    """glob() 목록 조회와 SELECT EXISTS(...) 매칭 여부 확인만 흉내내는 가짜 커넥션.
    `matches`에 지정된 base_date만 조건에 매칭되는 row가 있는 것으로 취급한다."""

    def __init__(self, glob_paths, matches: dict[str, bool]):
        self.glob_paths = glob_paths
        self.matches = matches
        self.checked_dates: list[str] = []

    def execute(self, query: str, params: dict | None = None):
        params = params or {}
        if "FROM glob($pattern)" in query:
            return _FakeResult(self.glob_paths)
        if "SELECT EXISTS(" in query:
            glob = params["glob"]
            marker = "base_date="
            base_date = glob[glob.find(marker) + len(marker):].split("/", 1)[0]
            self.checked_dates.append(base_date)
            return _FakeResult((self.matches.get(base_date, False),))
        raise AssertionError(f"예상하지 못한 쿼리: {query}")


@pytest.fixture
def fake_con():
    return _FakeConnection(_PARTITION_PATHS, matches={})


def test_list_base_dates_returns_descending_order(fake_con):
    assert duckdb_client.list_base_dates(fake_con, MART_TABLE) == [
        "2026-08-30",
        "2026-08-29",
        "2026-08-27",
    ]


def test_list_base_dates_raises_when_no_partition():
    con = _FakeConnection(glob_paths=[], matches={})
    with pytest.raises(FileNotFoundError):
        duckdb_client.list_base_dates(con, MART_TABLE)


def test_resolve_base_date_for_filter_matches_latest_partition_in_one_check():
    """가장 흔한 케이스: 최신 파티션에 이미 조건 매칭 데이터가 있으면 1회 확인으로 끝난다."""
    con = _FakeConnection(_PARTITION_PATHS, matches={"2026-08-30": True})
    result = duckdb_client.resolve_base_date_for_filter(
        con, MART_TABLE, "WHERE cgg_cd = $cgg_cd", {"cgg_cd": "11680"}
    )
    assert result == "2026-08-30"
    assert con.checked_dates == ["2026-08-30"]


def test_resolve_base_date_for_filter_falls_back_to_older_partition(caplog):
    """최신 파티션엔 없고 더 과거 파티션에 매칭 데이터가 있으면 그 날짜로 소급하고,
    실제로 소급이 발생했으므로 INFO 로그를 남긴다."""
    con = _FakeConnection(_PARTITION_PATHS, matches={"2026-08-27": True})
    with caplog.at_level(logging.INFO, logger="app.core.duckdb_client"):
        result = duckdb_client.resolve_base_date_for_filter(
            con, MART_TABLE, "WHERE cgg_cd = $cgg_cd", {"cgg_cd": "11680"}
        )
    assert result == "2026-08-27"
    assert con.checked_dates == ["2026-08-30", "2026-08-29", "2026-08-27"]
    assert any("Fallback used" in record.message for record in caplog.records)


def test_resolve_base_date_for_filter_no_log_when_naive_latest_matches(caplog):
    """폴백이 실제로 일어나지 않으면(=최신 날짜 그대로 사용) 로그를 남기지 않는다."""
    con = _FakeConnection(_PARTITION_PATHS, matches={"2026-08-30": True})
    with caplog.at_level(logging.INFO, logger="app.core.duckdb_client"):
        duckdb_client.resolve_base_date_for_filter(
            con, MART_TABLE, "WHERE cgg_cd = $cgg_cd", {"cgg_cd": "11680"}
        )
    assert caplog.records == []


def test_resolve_base_date_for_filter_respects_max_lookback():
    """max_lookback개까지만 확인하고, 그 안에서 못 찾으면 더 과거 파티션은 조회조차 하지 않는다."""
    con = _FakeConnection(_PARTITION_PATHS, matches={"2026-08-27": True})
    result = duckdb_client.resolve_base_date_for_filter(
        con, MART_TABLE, "WHERE cgg_cd = $cgg_cd", {"cgg_cd": "11680"}, max_lookback=2
    )
    assert result is None
    assert con.checked_dates == ["2026-08-30", "2026-08-29"]


def test_resolve_base_date_for_filter_returns_none_when_no_partition_matches():
    """max_lookback(기본 30, 파티션이 3개뿐이라 전부) 안에서 아무 파티션도 매칭되지 않으면
    예외 없이 None을 반환한다(호출자가 resolve_base_date()로 폴백)."""
    con = _FakeConnection(_PARTITION_PATHS, matches={})
    result = duckdb_client.resolve_base_date_for_filter(
        con, MART_TABLE, "WHERE cgg_cd = $cgg_cd", {"cgg_cd": "00000"}
    )
    assert result is None
    assert con.checked_dates == ["2026-08-30", "2026-08-29", "2026-08-27"]


def test_resolve_base_date_for_filter_supports_empty_where_clause():
    """dong_summary_service처럼 지역 필터가 없어 where_sql이 빈 문자열인 경우도 정상 동작해야 한다."""
    con = _FakeConnection(_PARTITION_PATHS, matches={"2026-08-30": True})
    result = duckdb_client.resolve_base_date_for_filter(con, MART_TABLE, "", {})
    assert result == "2026-08-30"


def test_resolve_base_date_for_filter_uses_settings_default_lookback(monkeypatch):
    """max_lookback을 명시하지 않으면 settings.max_base_date_lookback(기본 30)을 사용한다."""
    monkeypatch.setattr(duckdb_client.settings, "max_base_date_lookback", 1)
    con = _FakeConnection(_PARTITION_PATHS, matches={"2026-08-27": True})
    result = duckdb_client.resolve_base_date_for_filter(
        con, MART_TABLE, "WHERE cgg_cd = $cgg_cd", {"cgg_cd": "11680"}
    )
    assert result is None
    assert con.checked_dates == ["2026-08-30"]


# ---------------------------------------------------------------------------
# resolve_latest_date_partition_for_filter (RAW year/month/day 파티션 버전)
# ---------------------------------------------------------------------------

DATASET = "real_estate"

_RAW_PARTITION_PATHS = [
    (f"s3://lake/{DATASET}/year=2026/month=08/day=29/part.parquet",),
    (f"s3://lake/{DATASET}/year=2026/month=08/day=30/part.parquet",),
    (f"s3://lake/{DATASET}/year=2026/month=08/day=27/part.parquet",),
]


class _FakeRawConnection:
    """RAW year=/month=/day= 파티션용 glob()/EXISTS 페이크 커넥션."""

    def __init__(self, glob_paths, matches: dict[tuple[str, str, str], bool]):
        self.glob_paths = glob_paths
        self.matches = matches
        self.checked: list[tuple[str, str, str]] = []

    def execute(self, query: str, params: dict | None = None):
        params = params or {}
        if "FROM glob($pattern)" in query:
            return _FakeResult(self.glob_paths)
        if "SELECT EXISTS(" in query:
            glob = params["glob"]
            match = duckdb_client._PARTITION_PATTERN.search(glob)
            key = match.groups()
            self.checked.append(key)
            return _FakeResult((self.matches.get(key, False),))
        raise AssertionError(f"예상하지 못한 쿼리: {query}")


def test_resolve_latest_date_partition_for_filter_matches_latest_in_one_check():
    con = _FakeRawConnection(_RAW_PARTITION_PATHS, matches={("2026", "08", "30"): True})
    result = duckdb_client.resolve_latest_date_partition_for_filter(
        con, DATASET, "WHERE BLDG_USG = $bldg_usg", {"bldg_usg": "아파트"}
    )
    assert result == ("2026", "08", "30")
    assert con.checked == [("2026", "08", "30")]


def test_resolve_latest_date_partition_for_filter_falls_back_to_older_day():
    con = _FakeRawConnection(_RAW_PARTITION_PATHS, matches={("2026", "08", "27"): True})
    result = duckdb_client.resolve_latest_date_partition_for_filter(
        con, DATASET, "WHERE BLDG_USG = $bldg_usg", {"bldg_usg": "아파트"}
    )
    assert result == ("2026", "08", "27")
    assert con.checked == [("2026", "08", "30"), ("2026", "08", "29"), ("2026", "08", "27")]


def test_resolve_latest_date_partition_for_filter_returns_none_when_no_match():
    con = _FakeRawConnection(_RAW_PARTITION_PATHS, matches={})
    result = duckdb_client.resolve_latest_date_partition_for_filter(
        con, DATASET, "WHERE BLDG_USG = $bldg_usg", {"bldg_usg": "아파트"}
    )
    assert result is None


def test_resolve_latest_date_partition_for_filter_raises_when_no_partition_at_all():
    con = _FakeRawConnection(glob_paths=[], matches={})
    with pytest.raises(FileNotFoundError):
        duckdb_client.resolve_latest_date_partition_for_filter(
            con, DATASET, "WHERE BLDG_USG = $bldg_usg", {"bldg_usg": "아파트"}
        )


# ---------------------------------------------------------------------------
# resolve_recent_match_date (range-앵커형 MAX 집계)
# ---------------------------------------------------------------------------


class _FakeMaxConnection:
    """SELECT MAX(date_column) 단일 집계 쿼리만 흉내내는 페이크 커넥션. `rows`는
    (매칭 조건 함수, 반환할 날짜) 튜플 목록이며, params가 매칭 조건을 만족하는 첫 항목의
    날짜를 반환한다."""

    def __init__(self, max_value):
        self.max_value = max_value
        self.executed_queries: list[str] = []

    def execute(self, query: str, params: dict | None = None):
        self.executed_queries.append(query)
        assert "SELECT MAX(" in query
        return _FakeResult((self.max_value,))


def test_resolve_recent_match_date_returns_max_date_when_found():
    from datetime import date as _date

    con = _FakeMaxConnection(_date(2026, 5, 1))
    result = duckdb_client.resolve_recent_match_date(
        con, "s3://warehouse/mart/apt_mkt_trends/**/*.parquet", "deal_date",
        "WHERE cgg_cd = $cgg_cd", {"cgg_cd": "11680"},
    )
    assert result == _date(2026, 5, 1)


def test_resolve_recent_match_date_returns_none_when_no_match():
    con = _FakeMaxConnection(None)
    result = duckdb_client.resolve_recent_match_date(
        con, "s3://warehouse/mart/apt_mkt_trends/**/*.parquet", "deal_date",
        "WHERE cgg_cd = $cgg_cd", {"cgg_cd": "00000"},
    )
    assert result is None
