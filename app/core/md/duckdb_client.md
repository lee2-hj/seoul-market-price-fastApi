# duckdb_client.py 명세

## 1. 메타 정보

| 항목 | 값 |
|---|---|
| source_path | backend_fastApi/app/core/duckdb_client.py |
| source_sha256 | 1f6458d76ffac57648320df3f2db5ee1a7e3c58c2167e297411d3c530e703f01 |
| source_lines | 256 |

## 2. 역할 요약

MinIO(S3 호환)에 적재된 parquet 데이터를 DuckDB로 조회하기 위한 커넥션 생성, base_date/RAW 날짜 파티션 탐색(당일 우선 → 최신 우선 → 조건 매칭 소급 탐색), 쿼리 결과를 JSON-safe 딕셔너리로 변환하는 유틸리티 함수 모음이다.

## 3. 외부 인터페이스

| 이름 | 종류 | 시그니처 | 반환 타입 |
|---|---|---|---|
| _PARTITION_PATTERN | const | `_PARTITION_PATTERN = re.compile(r"year=(\d{4})/month=(\d{2})/day=(\d{2})")` | re.Pattern |
| logger | const | `logger = logging.getLogger(__name__)` | logging.Logger |
| get_connection | function | `def get_connection() -> duckdb.DuckDBPyConnection` | duckdb.DuckDBPyConnection |
| mart_base_path | function | `def mart_base_path(mart_table: str) -> str` | str |
| list_base_dates | function | `def list_base_dates(con: duckdb.DuckDBPyConnection, mart_table: str) -> list[str]` | list[str] |
| resolve_base_date | function | `def resolve_base_date(con: duckdb.DuckDBPyConnection, mart_table: str) -> str` | str |
| resolve_base_date_for_filter | function | `def resolve_base_date_for_filter(con: duckdb.DuckDBPyConnection, mart_table: str, where_sql: str, params: dict[str, Any], *, max_lookback: int \| None = None) -> str \| None` | str \| None |
| raw_base_path | function | `def raw_base_path(dataset: str) -> str` | str |
| resolve_latest_date_partition | function | `def resolve_latest_date_partition(con: duckdb.DuckDBPyConnection, dataset: str) -> tuple[str, str, str]` | tuple[str, str, str] |
| resolve_latest_date_partition_for_filter | function | `def resolve_latest_date_partition_for_filter(con: duckdb.DuckDBPyConnection, dataset: str, where_sql: str, params: dict[str, Any], *, max_lookback: int \| None = None) -> tuple[str, str, str] \| None` | tuple[str, str, str] \| None |
| resolve_recent_match_date | function | `def resolve_recent_match_date(con: duckdb.DuckDBPyConnection, glob_pattern: str, date_column: str, where_sql: str, params: dict[str, Any]) -> date \| None` | date \| None |
| to_json_safe | function | `def to_json_safe(value: Any) -> Any` | Any |
| rows_to_dicts | function | `def rows_to_dicts(result: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]` | list[dict[str, Any]] |

## 4. 의존성(imports)

- 표준 라이브러리:
  - `from datetime import date, datetime`
  - `from decimal import Decimal`
  - `import logging`
  - `import re`
  - `from typing import Any`
- 서드파티:
  - `import duckdb`
- 내부 모듈:
  - `from app.core.config import settings`

## 5. 로직 상세

### _PARTITION_PATTERN

- 목적: RAW 데이터셋 경로에서 `year=YYYY/month=MM/day=DD` 형태의 파티션 문자열을 추출하는 정규식.
- 값: `re.compile(r"year=(\d{4})/month=(\d{2})/day=(\d{2})")` — 그룹 1: 4자리 연도, 그룹 2: 2자리 월, 그룹 3: 2자리 일.

### logger

- 목적: 이 모듈 전용 로거.
- 값: `logging.getLogger(__name__)`.

### get_connection

- 목적: MinIO(S3 호환) 접속이 설정된 인메모리 DuckDB 커넥션을 생성한다(원문 docstring: "MinIO(S3 호환) 접속이 설정된 인메모리 DuckDB 커넥션을 생성한다.").
- 파라미터: 없음.
- 처리 흐름:
  1. `con = duckdb.connect(database=":memory:")`로 인메모리 커넥션 생성.
  2. `con.execute("INSTALL httpfs;")` 실행.
  3. `con.execute("LOAD httpfs;")` 실행.
  4. `con.execute(f"SET s3_endpoint = '{settings.s3_end_point}';")` 실행.
  5. `con.execute(f"SET s3_access_key_id = '{settings.s3_access_key}';")` 실행.
  6. `con.execute(f"SET s3_secret_access_key = '{settings.s3_secret_key}';")` 실행.
  7. `con.execute(f"SET s3_url_style = '{settings.s3_url_style}';")` 실행.
  8. `con.execute(f"SET s3_use_ssl = {'true' if settings.s3_use_ssl else 'false'};")` 실행(파이썬 bool을 SQL 리터럴 `'true'`/`'false'` 문자열로 변환).
  9. `con.execute(f"SET s3_region = '{settings.aws_region}';")` 실행.
- 반환값: 설정이 끝난 `con`(duckdb.DuckDBPyConnection). 예외 없음(각 `execute` 실패 시 duckdb 예외가 그대로 전파됨, 이 함수에서 별도 처리 없음).

### mart_base_path

- 목적: mart 테이블의 S3 base 경로 문자열을 만든다.
- 파라미터: `mart_table: str` — mart 테이블명.
- 처리 흐름: 1. `f"s3://{settings.lake}/mart/{mart_table}"`를 그대로 반환.
- 반환값: 항상 위 형식의 문자열. 예외 없음.

### list_base_dates

- 목적: mart_table에 존재하는 모든 base_date 파티션명을 최신순(내림차순)으로 정렬해 반환한다(원문 docstring: "mart_table에 존재하는 모든 base_date 파티션명을 최신순(내림차순)으로 정렬해 반환한다. resolve_base_date()와 resolve_base_date_for_filter()가 공통으로 사용하는 파티션 목록 조회 로직이다. 파티션이 하나도 없으면 FileNotFoundError.").
- 파라미터: `con: duckdb.DuckDBPyConnection`, `mart_table: str`.
- 처리 흐름:
  1. `base_path = mart_base_path(mart_table)`.
  2. `all_pattern = f"{base_path}/base_date=*/*.parquet"`.
  3. `paths = con.execute("SELECT file FROM glob($pattern)", {"pattern": all_pattern}).fetchall()`.
  4. `if not paths:` 이면 `raise FileNotFoundError(f"'{mart_table}' 마트에서 조회 가능한 base_date 파티션을 찾을 수 없습니다.")`.
  5. `marker = "base_date="`; `available_dates: set[str] = set()` 초기화.
  6. `paths`의 각 `(path,)`에 대해: `idx = path.find(marker)`; `if idx == -1: continue`; `remainder = path[idx + len(marker):]`; `available_dates.add(remainder.split("/", 1)[0])`.
  7. `if not available_dates:` 이면 `raise FileNotFoundError(f"'{mart_table}' 마트 경로에서 base_date 파티션명을 파싱하지 못했습니다.")`.
  8. `return sorted(available_dates, reverse=True)`.
- 반환값: base_date 문자열의 내림차순 정렬 리스트. 실패 시(파티션 없음/파싱 실패) `FileNotFoundError` 발생(빈 리스트를 반환하지 않음).

### resolve_base_date

- 목적: 배치 당일 파티션을 우선 조회하고, 없으면 최신(MAX) base_date 파티션을 선택한다(원문 docstring 그대로).
- 파라미터: `con: duckdb.DuckDBPyConnection`, `mart_table: str`.
- 처리 흐름:
  1. `today_str = date.today().isoformat()`.
  2. `base_path = mart_base_path(mart_table)`.
  3. `today_pattern = f"{base_path}/base_date={today_str}/*.parquet"`.
  4. `if con.execute("SELECT COUNT(*) FROM glob($pattern)", {"pattern": today_pattern}).fetchone()[0] > 0:` 이면 `return today_str`.
  5. 그렇지 않으면 `return list_base_dates(con, mart_table)[0]`(내림차순 정렬 첫 원소 = 최신).
- 반환값: 당일 파티션이 있으면 오늘 날짜 문자열, 없으면 `list_base_dates`의 최신값. `list_base_dates`가 던지는 `FileNotFoundError`가 전파될 수 있음.

### resolve_base_date_for_filter

- 목적: 요청의 조회 조건(where_sql/params)에 매칭되는 row가 1건 이상 존재하는 가장 최근 base_date를 찾는다(원문 docstring: "요청의 조회 조건(where_sql/params)에 매칭되는 row가 1건 이상 존재하는 가장 최근 base_date를 찾는다. 파티션 존재 여부만 보는 resolve_base_date()와 달리, 실제 조건에 매칭되는 데이터가 있는지까지 확인한다. 최신 base_date부터 내림차순으로 최대 max_lookback개(생략 시 settings.max_base_date_lookback) 파티션까지 `SELECT EXISTS(...LIMIT 1)` 형태의 가벼운 쿼리로 순차 확인하며, 매칭되는 첫 base_date를 즉시 반환한다(조기 종료). 흔한 경우(최신 파티션에 이미 데이터가 있음)는 쿼리 1회로 끝난다. max_lookback개를 모두 확인해도 매칭 데이터가 없으면 None을 반환한다(예외를 던지지 않음 — 호출자가 기존 resolve_base_date()의 결과로 폴백해 빈 결과를 반환해야 한다).").
- 파라미터:
  - `con: duckdb.DuckDBPyConnection`
  - `mart_table: str`
  - `where_sql: str` — SQL WHERE 절 조각(빈 문자열 가능).
  - `params: dict[str, Any]` — `where_sql`의 바인딩 파라미터.
  - `max_lookback: int | None = None`(키워드 전용, `*` 이후) — 생략(None) 시 `settings.max_base_date_lookback` 사용.
- 처리 흐름:
  1. `candidates = list_base_dates(con, mart_table)`.
  2. `naive_latest = candidates[0]`.
  3. `lookback = max_lookback if max_lookback is not None else settings.max_base_date_lookback`.
  4. `base_path = mart_base_path(mart_table)`.
  5. `checked = 0`.
  6. `candidates[:lookback]`을 순회하며 각 `candidate`마다:
     a. `checked += 1`.
     b. `glob_pattern = f"{base_path}/base_date={candidate}/*.parquet"`.
     c. `query`는 **f-string**(`query = f"""..."""`, `.format()` 아님)으로 아래와 같이 조립(`{where_sql}`은 f-string 치환식이며 파라미터 인자 `where_sql`의 값이 SQL 텍스트 그대로 치환됨 — 값 자체는 별도 바인딩되지 않음):
        ```python
        query = f"""
            SELECT EXISTS(
                SELECT 1 FROM read_parquet($glob, hive_partitioning = true)
                {where_sql}
                LIMIT 1
            )
        """
        ```
     d. `query_params = {**params, "glob": glob_pattern}`.
     e. `matched = con.execute(query, query_params).fetchone()[0]`.
     f. `if matched:` 이면, `candidate != naive_latest`일 때만 `logger.info("Fallback used for table=%s, condition_summary=%s, final_base_date=%s, lookback_partitions_checked=%d", mart_table, (where_sql or "(no filter)")[:100], candidate, checked)` 로깅 후 `return candidate`(조기 종료).
  7. 루프를 다 돌아도 매칭이 없으면 `return None`.
- 반환값: 매칭된 base_date 문자열, 또는 `None`(lookback 범위 내 매칭 없음). `list_base_dates`가 던지는 `FileNotFoundError`가 전파될 수 있음.

### raw_base_path

- 목적: RAW 데이터셋의 S3 base 경로 문자열을 만든다.
- 파라미터: `dataset: str`.
- 처리 흐름: 1. `f"s3://{settings.raw}/{dataset}"`를 그대로 반환.
- 반환값: 항상 위 형식의 문자열. 예외 없음.

### resolve_latest_date_partition

- 목적: RAW 버킷의 year=yyyy/month=MM/day=dd 파티션 중 오늘 파티션을 우선 조회하고, 없으면 가장 최근(최신) 날짜 파티션의 (year, month, day)를 반환한다(원문 docstring 그대로).
- 파라미터: `con: duckdb.DuckDBPyConnection`, `dataset: str`.
- 처리 흐름:
  1. `base_path = raw_base_path(dataset)`.
  2. `today = date.today()`; `today_year, today_month, today_day = f"{today.year:04d}", f"{today.month:02d}", f"{today.day:02d}"`.
  3. `today_pattern = f"{base_path}/year={today_year}/month={today_month}/day={today_day}/*.parquet"`.
  4. `if con.execute("SELECT COUNT(*) FROM glob($pattern)", {"pattern": today_pattern}).fetchone()[0] > 0:` 이면 `return today_year, today_month, today_day`.
  5. `all_pattern = f"{base_path}/year=*/month=*/day=*/*.parquet"`.
  6. `paths = con.execute("SELECT file FROM glob($pattern)", {"pattern": all_pattern}).fetchall()`.
  7. `if not paths:` 이면 `raise FileNotFoundError(f"'{dataset}' 데이터셋에서 조회 가능한 year/month/day 파티션을 찾을 수 없습니다.")`.
  8. `partitions: set[tuple[str, str, str]] = set()` 초기화. `paths`의 각 `(path,)`에 대해 `match = _PARTITION_PATTERN.search(path)`; 매칭되면 `partitions.add(match.groups())`.
  9. `if not partitions:` 이면 `raise FileNotFoundError(f"'{dataset}' 데이터셋 경로에서 year/month/day 파티션명을 파싱하지 못했습니다.")`.
  10. `return max(partitions)`(튜플 사전식 비교로 최신 날짜 선택).
- 반환값: `(year, month, day)` 문자열 3튜플. 실패 시 `FileNotFoundError`.

### resolve_latest_date_partition_for_filter

- 목적: RAW 버킷(year=/month=/day= 파티션)에서 where_sql/params 조건에 매칭되는 row가 1건 이상 존재하는 가장 최근 (year, month, day)를 찾는다(원문 docstring: "RAW 버킷(year=/month=/day= 파티션)에서 where_sql/params 조건에 매칭되는 row가 1건 이상 존재하는 가장 최근 (year, month, day)를 찾는다. resolve_base_date_for_filter의 RAW 데이터셋 버전이며, 동작 원리(조기 종료/최대 max_lookback개/미매칭 시 None 반환/폴백 발생 시에만 로깅)는 동일하다. 파티션 자체가 하나도 없으면(=폴더 자체가 비어있음) resolve_latest_date_partition()과 동일하게 FileNotFoundError를 던진다.").
- 파라미터:
  - `con: duckdb.DuckDBPyConnection`
  - `dataset: str`
  - `where_sql: str`
  - `params: dict[str, Any]`
  - `max_lookback: int | None = None`(키워드 전용).
- 처리 흐름:
  1. `base_path = raw_base_path(dataset)`.
  2. `all_pattern = f"{base_path}/year=*/month=*/day=*/*.parquet"`.
  3. `paths = con.execute("SELECT file FROM glob($pattern)", {"pattern": all_pattern}).fetchall()`.
  4. `if not paths:` 이면 `raise FileNotFoundError(f"'{dataset}' 데이터셋에서 조회 가능한 year/month/day 파티션을 찾을 수 없습니다.")`.
  5. `partitions: set[tuple[str, str, str]] = set()` 초기화, `paths`의 각 `(path,)`에 대해 `match = _PARTITION_PATTERN.search(path)`; 매칭되면 `partitions.add(match.groups())`.
  6. `if not partitions:` 이면 `raise FileNotFoundError(f"'{dataset}' 데이터셋 경로에서 year/month/day 파티션명을 파싱하지 못했습니다.")`.
  7. `candidates = sorted(partitions, reverse=True)`; `naive_latest = candidates[0]`.
  8. `lookback = max_lookback if max_lookback is not None else settings.max_base_date_lookback`.
  9. `checked = 0`.
  10. `candidates[:lookback]`을 순회하며 각 `candidate`(=`(year, month, day)`)마다:
      a. `checked += 1`.
      b. `year, month, day = candidate`.
      c. `glob_pattern = f"{base_path}/year={year}/month={month}/day={day}/*.parquet"`.
      d. `query`는 **f-string**(`query = f"""..."""`, `.format()` 아님)으로 아래와 같이 조립(`{where_sql}`은 f-string 치환식):
         ```python
         query = f"""
             SELECT EXISTS(
                 SELECT 1 FROM read_parquet($glob, hive_partitioning = true)
                 {where_sql}
                 LIMIT 1
             )
         """
         ```
      e. `query_params = {**params, "glob": glob_pattern}`.
      f. `matched = con.execute(query, query_params).fetchone()[0]`.
      g. `if matched:` 이면, `candidate != naive_latest`일 때만 `logger.info("Fallback used for dataset=%s, condition_summary=%s, final_partition=year=%s/month=%s/day=%s, lookback_partitions_checked=%d", dataset, (where_sql or "(no filter)")[:100], year, month, day, checked)` 로깅 후 `return candidate`.
  11. 루프를 다 돌아도 매칭 없으면 `return None`.
- 반환값: 매칭된 `(year, month, day)` 튜플, 또는 `None`. 파티션이 전혀 없으면 `FileNotFoundError`.

### resolve_recent_match_date

- 목적: range-앵커형(apt_trend_service/rtt_service) 전용으로, 파티션을 하나씩 순회하지 않고 날짜 범위 제한 없이 전체 이력에서 조건에 매칭되는 가장 최근 date_column 값을 단일 집계 쿼리로 찾는다(원문 docstring: "range-앵커형(apt_trend_service/rtt_service) 전용: 파티션을 하나씩 순회하지 않고, 날짜 범위 제한 없이 전체 이력에서 where_sql/params 조건에 매칭되는 가장 최근 date_column 값을 단일 `SELECT MAX(date_column)` 집계 쿼리로 찾는다. 비용이 파티션 개수와 무관하게 일정하다(resolve_base_date_for_filter와 달리 조기 종료할 것도 없이 쿼리 1회로 끝남). 매칭되는 row가 하나도 없으면 None을 반환한다. 이 함수 자체는 로깅하지 않는다 — 호출자가 \"나이브 조회 0건 → 이 함수 호출 → 창 이동\" 흐름 전체를 판단할 수 있으므로, 실제로 창이 이동된 경우의 로깅은 호출부(rtt_service/apt_trend_service)에서 수행한다.").
- 파라미터: `con: duckdb.DuckDBPyConnection`, `glob_pattern: str`, `date_column: str`, `where_sql: str`, `params: dict[str, Any]`.
- 처리 흐름:
  1. `query`는 **f-string**(`query = f"""..."""`, `.format()` 아님)으로 아래와 같이 조립(`{date_column}`, `{where_sql}`은 모두 f-string 치환식):
     ```python
     query = f"""
         SELECT MAX({date_column})
         FROM read_parquet($glob, hive_partitioning = true)
         {where_sql}
     """
     ```
  2. `query_params = {**params, "glob": glob_pattern}`.
  3. `row = con.execute(query, query_params).fetchone()`.
  4. `return row[0] if row and row[0] is not None else None`.
- 반환값: 매칭되는 최신 `date_column` 값(date) 또는 `None`(매칭 없음). 이 함수 자체는 로깅하지 않음(원문 docstring 명시).

### to_json_safe

- 목적: DuckDB가 반환하는 Decimal/date/datetime 등을 JSON 응답용 기본 타입으로 변환한다(원문 docstring 그대로).
- 파라미터: `value: Any`.
- 처리 흐름:
  1. `if isinstance(value, Decimal): return float(value)`.
  2. `if isinstance(value, (datetime, date)): return value.isoformat()`.
  3. 위 조건에 해당하지 않으면 `return value`(원본 그대로).
- 반환값: `Decimal`은 `float`, `datetime`/`date`는 ISO 8601 문자열, 그 외 타입은 입력값 그대로. 순서 주의: `datetime`이 `date`의 서브클래스이므로 `isinstance(value, (datetime, date))` 한 번의 검사로 둘 다 처리.

### rows_to_dicts

- 목적: DuckDB 쿼리 결과를 컬럼 생략 없이 JSON-safe한 딕셔너리 리스트로 변환한다(원문 docstring 그대로).
- 파라미터: `result: duckdb.DuckDBPyConnection` — `execute()` 실행 후의 결과 객체(타입 힌트상 `duckdb.DuckDBPyConnection`으로 선언되어 있으나 실제로는 `.description`/`.fetchall()`을 갖는 커서/결과 객체).
- 처리 흐름:
  1. `columns = [col[0] for col in result.description]`로 컬럼명 리스트 추출.
  2. `result.fetchall()`의 각 `row`에 대해, `zip(columns, row)`로 `(col, val)` 쌍을 만들고 `to_json_safe(val)`을 적용한 딕셔너리 컴프리헨션 `{col: to_json_safe(val) for col, val in zip(columns, row)}`을 생성.
  3. 위 딕셔너리들을 리스트로 모아 반환: `[{...} for row in result.fetchall()]`.
- 반환값: 각 row가 `{컬럼명: JSON-safe 값}` 딕셔너리인 리스트. row가 없으면 빈 리스트.

## 6. 모듈 레벨 상수/설정값

| 이름 | 값 |
|---|---|
| _PARTITION_PATTERN | `re.compile(r"year=(\d{4})/month=(\d{2})/day=(\d{2})")` |
| logger | `logging.getLogger(__name__)` |

## 7. 역참조(이 파일을 사용하는 곳)

- `app/services/dong_summary_service.py` — `from app.core import duckdb_client`.
- `app/services/apt_price_service.py` — `from app.core import duckdb_client`.
- `app/services/apt_compare_service.py` — `from app.core import duckdb_client`.
- `app/services/real_estate_service.py` — `from app.core import duckdb_client`.
- `app/services/dashboard_service.py` — `from app.core import duckdb_client`.
- `app/services/apt_trend_service.py` — `from app.core import duckdb_client`.
- `app/services/mart_service.py` — `from app.core import duckdb_client`.
- `app/services/rtt_service.py` — `from app.core import duckdb_client`.
- `app/services/region_apt_compare_service.py` — `from app.core import duckdb_client`.
- `tests/core/test_duckdb_client.py` — `from app.core import duckdb_client`(이 모듈 자체의 단위 테스트).

## 8. 재생성 지침

> 위 내용을 근거로 `backend_fastApi/app/core/duckdb_client.py` 파일을 동일한 로직으로 재작성하라. 여기 명시되지 않은 세부 구현(변수명 스타일, 코드 포맷 등)은 기존 프로젝트 컨벤션(PEP 8, 저장소 내 동일 계층 파일들의 스타일)을 따른다.
