# test_duckdb_client.py 명세

## 1. 메타 정보

| 항목 | 값 |
|---|---|
| source_path | backend_fastApi/tests/core/test_duckdb_client.py |
| source_sha256 | 1bc7c637d5c62e81cfca6ebf56be47ea92abad9b9b38d1145208e2f985f34723 |
| source_lines | 257 |

## 2. 역할 요약

`app/core/duckdb_client.py`의 base_date/RAW 날짜 파티션 폴백(소급 조회) 로직을, 실제 MinIO(S3) 접속 없이 페이크 DuckDB 커넥션(`_FakeConnection`/`_FakeRawConnection`/`_FakeMaxConnection`)으로 검증하는 회귀 테스트 모음이다. `list_base_dates`, `resolve_base_date_for_filter`, `resolve_latest_date_partition_for_filter`, `resolve_recent_match_date`의 조기 종료, 소급 순서, `max_lookback` 상한, 매칭 실패 시 `None` 반환, 폴백 발생 시 로깅 여부를 검증한다.

모듈 docstring(원문): "app/core/duckdb_client.py의 base_date 조건부 폴백(소급 조회) 로직 회귀 테스트.\n\n실제 MinIO(S3) 접속 없이도 검증할 수 있도록, DuckDB 커넥션을 흉내내는 FakeConnection으로 glob()/EXISTS 쿼리 결과를 스크립트로 지정해 list_base_dates()/resolve_base_date_for_filter()의 동작(조기 종료, 소급 순서, max_lookback 상한, 매칭 실패 시 None 반환, 폴백 발생 시 로깅)만 독립적으로 검증한다."

## 3. 외부 인터페이스

| 이름 | 종류 | 시그니처 | 반환 타입 |
|---|---|---|---|
| MART_TABLE | const | `MART_TABLE = "dm_apt_price_avg"` | str |
| _PARTITION_PATHS | const | `_PARTITION_PATHS = [...]` | list[tuple[str]] |
| _FakeResult | class | `class _FakeResult` | - |
| _FakeConnection | class | `class _FakeConnection` | - |
| fake_con | function | `def fake_con()` (`@pytest.fixture`) | _FakeConnection |
| test_list_base_dates_returns_descending_order | function | `def test_list_base_dates_returns_descending_order(fake_con)` | None |
| test_list_base_dates_raises_when_no_partition | function | `def test_list_base_dates_raises_when_no_partition()` | None |
| test_resolve_base_date_for_filter_matches_latest_partition_in_one_check | function | `def test_resolve_base_date_for_filter_matches_latest_partition_in_one_check()` | None |
| test_resolve_base_date_for_filter_falls_back_to_older_partition | function | `def test_resolve_base_date_for_filter_falls_back_to_older_partition(caplog)` | None |
| test_resolve_base_date_for_filter_no_log_when_naive_latest_matches | function | `def test_resolve_base_date_for_filter_no_log_when_naive_latest_matches(caplog)` | None |
| test_resolve_base_date_for_filter_respects_max_lookback | function | `def test_resolve_base_date_for_filter_respects_max_lookback()` | None |
| test_resolve_base_date_for_filter_returns_none_when_no_partition_matches | function | `def test_resolve_base_date_for_filter_returns_none_when_no_partition_matches()` | None |
| test_resolve_base_date_for_filter_supports_empty_where_clause | function | `def test_resolve_base_date_for_filter_supports_empty_where_clause()` | None |
| test_resolve_base_date_for_filter_uses_settings_default_lookback | function | `def test_resolve_base_date_for_filter_uses_settings_default_lookback(monkeypatch)` | None |
| DATASET | const | `DATASET = "real_estate"` | str |
| _RAW_PARTITION_PATHS | const | `_RAW_PARTITION_PATHS = [...]` | list[tuple[str]] |
| _FakeRawConnection | class | `class _FakeRawConnection` | - |
| test_resolve_latest_date_partition_for_filter_matches_latest_in_one_check | function | `def test_resolve_latest_date_partition_for_filter_matches_latest_in_one_check()` | None |
| test_resolve_latest_date_partition_for_filter_falls_back_to_older_day | function | `def test_resolve_latest_date_partition_for_filter_falls_back_to_older_day()` | None |
| test_resolve_latest_date_partition_for_filter_returns_none_when_no_match | function | `def test_resolve_latest_date_partition_for_filter_returns_none_when_no_match()` | None |
| test_resolve_latest_date_partition_for_filter_raises_when_no_partition_at_all | function | `def test_resolve_latest_date_partition_for_filter_raises_when_no_partition_at_all()` | None |
| _FakeMaxConnection | class | `class _FakeMaxConnection` | - |
| test_resolve_recent_match_date_returns_max_date_when_found | function | `def test_resolve_recent_match_date_returns_max_date_when_found()` | None |
| test_resolve_recent_match_date_returns_none_when_no_match | function | `def test_resolve_recent_match_date_returns_none_when_no_match()` | None |

## 4. 의존성(imports)

- 표준 라이브러리:
  - `from __future__ import annotations`
  - `import logging`
- 서드파티:
  - `import pytest`
- 내부 모듈:
  - `from app.core import duckdb_client`

(테스트 함수 `test_resolve_recent_match_date_returns_max_date_when_found` 내부에 지역 임포트 `from datetime import date as _date`가 있음 — 함수 스코프 임포트이므로 위 3그룹 분류에는 포함하지 않고 여기 별도 기록.)

## 5. 로직 상세

### MART_TABLE

- 값: `"dm_apt_price_avg"`.

### _PARTITION_PATHS

- 목적: `list_base_dates` 등에 넘길 가짜 `glob()` 반환값. 주석 원문: "최신순(내림차순)이 아니라 일부러 뒤섞어 넣어 glob() 원시 반환 순서와 무관하게 list_base_dates()가 스스로 내림차순 정렬하는지도 함께 검증한다."
- 값:
  ```python
  _PARTITION_PATHS = [
      (f"s3://warehouse/mart/{MART_TABLE}/base_date=2026-08-29/part.parquet",),
      (f"s3://warehouse/mart/{MART_TABLE}/base_date=2026-08-30/part.parquet",),
      (f"s3://warehouse/mart/{MART_TABLE}/base_date=2026-08-27/part.parquet",),
  ]
  ```

### _FakeResult

- 목적: `fetchone()`/`fetchall()`이 동일한 고정값을 반환하는 결과 객체 스텁.
- 처리 흐름: `__init__(self, value)`는 `self._value = value`. `fetchone()`은 `self._value` 반환. `fetchall()`도 `self._value` 반환.

### _FakeConnection

- 목적(원문 docstring): "glob() 목록 조회와 SELECT EXISTS(...) 매칭 여부 확인만 흉내내는 가짜 커넥션. `matches`에 지정된 base_date만 조건에 매칭되는 row가 있는 것으로 취급한다."
- 처리 흐름:
  1. `__init__(self, glob_paths, matches: dict[str, bool])`: `self.glob_paths = glob_paths`; `self.matches = matches`; `self.checked_dates: list[str] = []`.
  2. `execute(self, query: str, params: dict | None = None)`:
     a. `params = params or {}`.
     b. `if "FROM glob($pattern)" in query: return _FakeResult(self.glob_paths)`.
     c. `if "SELECT EXISTS(" in query:` 이면 `glob = params["glob"]`; `marker = "base_date="`; `base_date = glob[glob.find(marker) + len(marker):].split("/", 1)[0]`; `self.checked_dates.append(base_date)`; `return _FakeResult((self.matches.get(base_date, False),))`.
     d. 위 두 패턴에 모두 해당하지 않으면 `raise AssertionError(f"예상하지 못한 쿼리: {query}")`.

### fake_con

- 목적: `_FakeConnection(_PARTITION_PATHS, matches={})`를 제공하는 pytest fixture.
- 처리 흐름: `return _FakeConnection(_PARTITION_PATHS, matches={})`.

### test_list_base_dates_returns_descending_order(fake_con)

- Given: `fake_con` fixture(매칭 없음, `_PARTITION_PATHS` 그대로).
- When: `duckdb_client.list_base_dates(fake_con, MART_TABLE)` 호출.
- Then(원문 assert): `assert duckdb_client.list_base_dates(fake_con, MART_TABLE) == ["2026-08-30", "2026-08-29", "2026-08-27"]`.

### test_list_base_dates_raises_when_no_partition()

- Given: `con = _FakeConnection(glob_paths=[], matches={})`.
- When/Then(원문 assert): `with pytest.raises(FileNotFoundError): duckdb_client.list_base_dates(con, MART_TABLE)`.

### test_resolve_base_date_for_filter_matches_latest_partition_in_one_check()

- 함수 docstring(원문): "가장 흔한 케이스: 최신 파티션에 이미 조건 매칭 데이터가 있으면 1회 확인으로 끝난다."
- Given: `con = _FakeConnection(_PARTITION_PATHS, matches={"2026-08-30": True})`.
- When: `result = duckdb_client.resolve_base_date_for_filter(con, MART_TABLE, "WHERE cgg_cd = $cgg_cd", {"cgg_cd": "11680"})`.
- Then(원문 assert):
  - `assert result == "2026-08-30"`
  - `assert con.checked_dates == ["2026-08-30"]`

### test_resolve_base_date_for_filter_falls_back_to_older_partition(caplog)

- 함수 docstring(원문): "최신 파티션엔 없고 더 과거 파티션에 매칭 데이터가 있으면 그 날짜로 소급하고, 실제로 소급이 발생했으므로 INFO 로그를 남긴다."
- Given: `con = _FakeConnection(_PARTITION_PATHS, matches={"2026-08-27": True})`.
- When: `with caplog.at_level(logging.INFO, logger="app.core.duckdb_client"): result = duckdb_client.resolve_base_date_for_filter(con, MART_TABLE, "WHERE cgg_cd = $cgg_cd", {"cgg_cd": "11680"})`.
- Then(원문 assert):
  - `assert result == "2026-08-27"`
  - `assert con.checked_dates == ["2026-08-30", "2026-08-29", "2026-08-27"]`
  - `assert any("Fallback used" in record.message for record in caplog.records)`

### test_resolve_base_date_for_filter_no_log_when_naive_latest_matches(caplog)

- 함수 docstring(원문): "폴백이 실제로 일어나지 않으면(=최신 날짜 그대로 사용) 로그를 남기지 않는다."
- Given: `con = _FakeConnection(_PARTITION_PATHS, matches={"2026-08-30": True})`.
- When: `with caplog.at_level(logging.INFO, logger="app.core.duckdb_client"): duckdb_client.resolve_base_date_for_filter(con, MART_TABLE, "WHERE cgg_cd = $cgg_cd", {"cgg_cd": "11680"})`.
- Then(원문 assert): `assert caplog.records == []`.

### test_resolve_base_date_for_filter_respects_max_lookback()

- 함수 docstring(원문): "max_lookback개까지만 확인하고, 그 안에서 못 찾으면 더 과거 파티션은 조회조차 하지 않는다."
- Given: `con = _FakeConnection(_PARTITION_PATHS, matches={"2026-08-27": True})`.
- When: `result = duckdb_client.resolve_base_date_for_filter(con, MART_TABLE, "WHERE cgg_cd = $cgg_cd", {"cgg_cd": "11680"}, max_lookback=2)`.
- Then(원문 assert):
  - `assert result is None`
  - `assert con.checked_dates == ["2026-08-30", "2026-08-29"]`

### test_resolve_base_date_for_filter_returns_none_when_no_partition_matches()

- 함수 docstring(원문): "max_lookback(기본 30, 파티션이 3개뿐이라 전부) 안에서 아무 파티션도 매칭되지 않으면 예외 없이 None을 반환한다(호출자가 resolve_base_date()로 폴백)."
- Given: `con = _FakeConnection(_PARTITION_PATHS, matches={})`.
- When: `result = duckdb_client.resolve_base_date_for_filter(con, MART_TABLE, "WHERE cgg_cd = $cgg_cd", {"cgg_cd": "00000"})`.
- Then(원문 assert):
  - `assert result is None`
  - `assert con.checked_dates == ["2026-08-30", "2026-08-29", "2026-08-27"]`

### test_resolve_base_date_for_filter_supports_empty_where_clause()

- 함수 docstring(원문): "dong_summary_service처럼 지역 필터가 없어 where_sql이 빈 문자열인 경우도 정상 동작해야 한다."
- Given: `con = _FakeConnection(_PARTITION_PATHS, matches={"2026-08-30": True})`.
- When: `result = duckdb_client.resolve_base_date_for_filter(con, MART_TABLE, "", {})`.
- Then(원문 assert): `assert result == "2026-08-30"`.

### test_resolve_base_date_for_filter_uses_settings_default_lookback(monkeypatch)

- 함수 docstring(원문): "max_lookback을 명시하지 않으면 settings.max_base_date_lookback(기본 30)을 사용한다."
- Given: `monkeypatch.setattr(duckdb_client.settings, "max_base_date_lookback", 1)`; `con = _FakeConnection(_PARTITION_PATHS, matches={"2026-08-27": True})`.
- When: `result = duckdb_client.resolve_base_date_for_filter(con, MART_TABLE, "WHERE cgg_cd = $cgg_cd", {"cgg_cd": "11680"})`.
- Then(원문 assert):
  - `assert result is None`
  - `assert con.checked_dates == ["2026-08-30"]`

### DATASET

- 값: `"real_estate"`. 주석 구분선: `# ---------------------------------------------------------------------------` / `# resolve_latest_date_partition_for_filter (RAW year/month/day 파티션 버전)` / `# ---------------------------------------------------------------------------`.

### _RAW_PARTITION_PATHS

- 값:
  ```python
  _RAW_PARTITION_PATHS = [
      (f"s3://lake/{DATASET}/year=2026/month=08/day=29/part.parquet",),
      (f"s3://lake/{DATASET}/year=2026/month=08/day=30/part.parquet",),
      (f"s3://lake/{DATASET}/year=2026/month=08/day=27/part.parquet",),
  ]
  ```

### _FakeRawConnection

- 목적(원문 docstring): "RAW year=/month=/day= 파티션용 glob()/EXISTS 페이크 커넥션."
- 처리 흐름:
  1. `__init__(self, glob_paths, matches: dict[tuple[str, str, str], bool])`: `self.glob_paths = glob_paths`; `self.matches = matches`; `self.checked: list[tuple[str, str, str]] = []`.
  2. `execute(self, query: str, params: dict | None = None)`:
     a. `params = params or {}`.
     b. `if "FROM glob($pattern)" in query: return _FakeResult(self.glob_paths)`.
     c. `if "SELECT EXISTS(" in query:` 이면 `glob = params["glob"]`; `match = duckdb_client._PARTITION_PATTERN.search(glob)`; `key = match.groups()`; `self.checked.append(key)`; `return _FakeResult((self.matches.get(key, False),))`.
     d. 아니면 `raise AssertionError(f"예상하지 못한 쿼리: {query}")`.

### test_resolve_latest_date_partition_for_filter_matches_latest_in_one_check()

- Given: `con = _FakeRawConnection(_RAW_PARTITION_PATHS, matches={("2026", "08", "30"): True})`.
- When: `result = duckdb_client.resolve_latest_date_partition_for_filter(con, DATASET, "WHERE BLDG_USG = $bldg_usg", {"bldg_usg": "아파트"})`.
- Then(원문 assert):
  - `assert result == ("2026", "08", "30")`
  - `assert con.checked == [("2026", "08", "30")]`

### test_resolve_latest_date_partition_for_filter_falls_back_to_older_day()

- Given: `con = _FakeRawConnection(_RAW_PARTITION_PATHS, matches={("2026", "08", "27"): True})`.
- When: `result = duckdb_client.resolve_latest_date_partition_for_filter(con, DATASET, "WHERE BLDG_USG = $bldg_usg", {"bldg_usg": "아파트"})`.
- Then(원문 assert):
  - `assert result == ("2026", "08", "27")`
  - `assert con.checked == [("2026", "08", "30"), ("2026", "08", "29"), ("2026", "08", "27")]`

### test_resolve_latest_date_partition_for_filter_returns_none_when_no_match()

- Given: `con = _FakeRawConnection(_RAW_PARTITION_PATHS, matches={})`.
- When: `result = duckdb_client.resolve_latest_date_partition_for_filter(con, DATASET, "WHERE BLDG_USG = $bldg_usg", {"bldg_usg": "아파트"})`.
- Then(원문 assert): `assert result is None`.

### test_resolve_latest_date_partition_for_filter_raises_when_no_partition_at_all()

- Given: `con = _FakeRawConnection(glob_paths=[], matches={})`.
- When/Then(원문 assert): `with pytest.raises(FileNotFoundError): duckdb_client.resolve_latest_date_partition_for_filter(con, DATASET, "WHERE BLDG_USG = $bldg_usg", {"bldg_usg": "아파트"})`.

### _FakeMaxConnection

- 목적(원문 docstring): "SELECT MAX(date_column) 단일 집계 쿼리만 흉내내는 페이크 커넥션. `rows`는 (매칭 조건 함수, 반환할 날짜) 튜플 목록이며, params가 매칭 조건을 만족하는 첫 항목의 날짜를 반환한다."(주: 이 docstring은 실제 구현과 다소 불일치 — 실제 구현은 `max_value`를 그대로 반환하는 단순 스텁이다. 아래는 실제 코드 기준.)
- 처리 흐름:
  1. `__init__(self, max_value)`: `self.max_value = max_value`; `self.executed_queries: list[str] = []`.
  2. `execute(self, query: str, params: dict | None = None)`: `self.executed_queries.append(query)`; `assert "SELECT MAX(" in query`; `return _FakeResult((self.max_value,))`.

### test_resolve_recent_match_date_returns_max_date_when_found()

- Given: 지역 임포트 `from datetime import date as _date`; `con = _FakeMaxConnection(_date(2026, 5, 1))`.
- When: `result = duckdb_client.resolve_recent_match_date(con, "s3://warehouse/mart/apt_mkt_trends/**/*.parquet", "deal_date", "WHERE cgg_cd = $cgg_cd", {"cgg_cd": "11680"})`.
- Then(원문 assert): `assert result == _date(2026, 5, 1)`.

### test_resolve_recent_match_date_returns_none_when_no_match()

- Given: `con = _FakeMaxConnection(None)`.
- When: `result = duckdb_client.resolve_recent_match_date(con, "s3://warehouse/mart/apt_mkt_trends/**/*.parquet", "deal_date", "WHERE cgg_cd = $cgg_cd", {"cgg_cd": "00000"})`.
- Then(원문 assert): `assert result is None`.

## 6. 모듈 레벨 상수/설정값

| 이름 | 값 |
|---|---|
| MART_TABLE | `"dm_apt_price_avg"` |
| _PARTITION_PATHS | 3항 참조 |
| DATASET | `"real_estate"` |
| _RAW_PARTITION_PATHS | 5항 참조 |

## 7. 역참조(이 파일을 사용하는 곳)

- 없음(pytest가 파일명 패턴(`test_*.py`)으로 자동 수집·실행하는 테스트 모듈이며, 다른 소스 모듈이 이 파일을 import하지 않음).

## 8. 재생성 지침

> 위 내용을 근거로 `backend_fastApi/tests/core/test_duckdb_client.py` 파일을 동일한 로직으로 재작성하라. 여기 명시되지 않은 세부 구현(변수명 스타일, 코드 포맷 등)은 기존 프로젝트 컨벤션(PEP 8, 저장소 내 동일 계층 파일들의 스타일)을 따른다.
