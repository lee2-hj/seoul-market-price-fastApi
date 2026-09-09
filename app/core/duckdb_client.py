import logging
import re
import threading
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import duckdb
from cachetools import TTLCache

from app.core.config import settings

_PARTITION_PATTERN = re.compile(r"year=(\d{4})/month=(\d{2})/day=(\d{2})")

logger = logging.getLogger(__name__)

# 매 요청마다 duckdb.connect() + INSTALL/LOAD httpfs를 새로 하면(과거 방식), httpfs 익스텐션
# 로딩 자체의 오버헤드(디스크/네트워크 I/O)가 매 요청에 누적되어 응답 지연(nginx 499 유발)의 한
# 원인이 된다. 그래서 프로세스당 단 하나의 "베이스" 커넥션만 최초 호출 시 지연 생성(lazy
# singleton)해 익스텐션 설치만 재사용한다. DuckDB 커넥션 객체 자체는 여러 스레드에서 동시에 쓰기
# 안전하지 않지만(FastAPI의 동기 엔드포인트는 starlette가 threadpool의 여러 스레드에서 동시
# 실행할 수 있음), con.cursor()로 베이스 커넥션에서 파생된 커넥션은 같은 데이터베이스(로드된
# 익스텐션 포함)를 공유하면서도 스레드마다 독립적으로 안전하게 사용할 수 있다(DuckDB 공식 권장
# 패턴).
#
# 단, S3(MinIO 등) 접속 설정(SET s3_endpoint/s3_access_key_id/...)은 익스텐션 로드와 달리
# 커넥션 로컬(session-local) 스코프라서 cursor()로 파생된 커넥션에는 자동으로 전파되지
# 않는다 - 베이스 커넥션에만 SET해두면 cursor 쪽은 그 설정이 비어 기본 AWS S3 엔드포인트로
# 요청이 나가버려 "NoSuchBucket: The specified bucket does not exist" 같은 오류가 난다(실제
# 운영에서 재현된 버그). 그래서 S3 설정은 베이스 커넥션이 아니라 get_connection()이 반환하는
# cursor 각각에 매번 적용한다 - INSTALL/LOAD와 달리 네트워크 I/O 없는 가벼운 SET이라 요청마다
# 다시 실행해도 성능에 영향이 없다.
_base_connection: duckdb.DuckDBPyConnection | None = None
_base_connection_lock = threading.Lock()


def _create_base_connection() -> duckdb.DuckDBPyConnection:
    """httpfs 익스텐션 설치/로드만 마친 인메모리 DuckDB 베이스 커넥션을 생성한다. S3 접속 설정은
    여기서 하지 않는다(커넥션 로컬 스코프라 cursor()로 파생된 커넥션에 전파되지 않으므로) - 대신
    get_connection()이 반환하는 cursor마다 _apply_s3_config()로 적용한다."""
    con = duckdb.connect(database=":memory:")
    con.execute("INSTALL httpfs;")
    con.execute("LOAD httpfs;")
    return con


def _get_base_connection() -> duckdb.DuckDBPyConnection:
    global _base_connection
    if _base_connection is None:
        with _base_connection_lock:
            if _base_connection is None:  # double-checked locking
                _base_connection = _create_base_connection()
    return _base_connection


def _apply_s3_config(con: duckdb.DuckDBPyConnection) -> None:
    """S3(MinIO 등) 접속 설정을 이 커넥션(cursor 포함)에 적용한다. 커넥션 로컬 스코프라 커넥션마다
    다시 적용해야 하며, 네트워크 I/O가 없는 가벼운 SET이라 매 요청 재실행해도 무방하다."""
    con.execute(f"SET s3_endpoint = '{settings.s3_end_point}';")
    con.execute(f"SET s3_access_key_id = '{settings.s3_access_key}';")
    con.execute(f"SET s3_secret_access_key = '{settings.s3_secret_key}';")
    con.execute(f"SET s3_url_style = '{settings.s3_url_style}';")
    con.execute(f"SET s3_use_ssl = {'true' if settings.s3_use_ssl else 'false'};")
    con.execute(f"SET s3_region = '{settings.aws_region}';")


def get_connection() -> duckdb.DuckDBPyConnection:
    """모듈 레벨 싱글턴 베이스 커넥션(익스텐션 설치 완료)에서 파생된 새 cursor()에 S3 접속 설정을
    적용해 반환한다. 호출부 입장에서는 기존과 동일하게 '독립된 커넥션 하나'로 취급해 쓰고
    finally에서 close()하면 된다."""
    con = _get_base_connection().cursor()
    _apply_s3_config(con)
    return con


def mart_base_path(mart_table: str) -> str:
    return f"s3://{settings.lake}/mart/{mart_table}"


def silver_base_path(dataset: str) -> str:
    """실버(Iceberg) 레이어 데이터셋의 테이블 경로. mart_base_path()와 달리 'mart/' 프리픽스 없이
    lake(warehouse) 버킷 루트에 위치한다(예: fact_apt_transactions, dim_apartment). iceberg_scan()으로
    읽어야 하는 실제 Iceberg 테이블이며(스키마가 파일마다 진화해 read_parquet 단순 glob은 스키마
    불일치 에러가 날 수 있음), 이 경로는 iceberg_scan()의 인자로 그대로 사용한다."""
    return f"s3://{settings.lake}/{dataset}"


def list_base_dates(con: duckdb.DuckDBPyConnection, mart_table: str) -> list[str]:
    """mart_table에 존재하는 모든 base_date 파티션명을 최신순(내림차순)으로 정렬해 반환한다.
    resolve_base_date()와 resolve_base_date_for_filter()가 공통으로 사용하는 파티션 목록
    조회 로직이다. 파티션이 하나도 없으면 FileNotFoundError."""
    base_path = mart_base_path(mart_table)
    all_pattern = f"{base_path}/base_date=*/*.parquet"
    paths = con.execute("SELECT file FROM glob($pattern)", {"pattern": all_pattern}).fetchall()
    if not paths:
        raise FileNotFoundError(f"'{mart_table}' 마트에서 조회 가능한 base_date 파티션을 찾을 수 없습니다.")

    marker = "base_date="
    available_dates: set[str] = set()
    for (path,) in paths:
        idx = path.find(marker)
        if idx == -1:
            continue
        remainder = path[idx + len(marker):]
        available_dates.add(remainder.split("/", 1)[0])

    if not available_dates:
        raise FileNotFoundError(f"'{mart_table}' 마트 경로에서 base_date 파티션명을 파싱하지 못했습니다.")
    return sorted(available_dates, reverse=True)


def resolve_base_date(con: duckdb.DuckDBPyConnection, mart_table: str) -> str:
    """mart_table에 존재하는 base_date 파티션 중 가장 최근 값을 반환한다.

    과거에는 `SELECT COUNT(*) FROM glob('.../base_date=오늘/*.parquet')`로 오늘 파티션의 존재
    여부를 먼저 확인하고(있으면 그대로 사용), 없으면 list_base_dates()로 폴백했다. 하지만 실제로는
    오늘 파티션에 parquet 파일이 정상적으로 존재하는데도

        duckdb.HTTPException: HTTP GET error reading 's3://.../base_date=2026-09-08' (HTTP 404)

    가 발생하는 사례가 확인됐다 - 특정 파티션 "폴더" 경로를 glob으로 직접 겨냥하면, 백엔드
    오브젝트 스토리지(GCS의 S3 호환 API 등)의 목록 조회 결과에 실제 parquet 파일이 아닌 그 폴더
    "키" 자체가 섞여 들어오는 경우가 있고, 이를 실제 오브젝트인 것처럼 GET하려다 404가 난다.

    그래서 특정 파티션 폴더를 콕 집어 존재 여부를 확인하는 대신, mart_table 전체를 재귀
    와일드카드(`**/*.parquet`)로 read_parquet에 넘겨 hive_partitioning으로 노출되는 base_date
    컬럼의 MAX 값을 SQL 집계로 직접 구한다. 이 경로는 실제로 열 수 있는 parquet 파일들만
    대상으로 하므로 위 문제가 재현되지 않는다. '오늘 파티션 우선'이라는 과거 동작과 결과도
    동일하다 - 정상적인 배치 파이프라인이라면 미래 날짜 파티션이 있을 수 없으므로, 오늘
    파티션이 존재한다면 그것이 항상 전체 MAX와 같기 때문이다."""
    recursive_pattern = f"{mart_base_path(mart_table)}/**/*.parquet"
    row = con.execute(
        "SELECT MAX(base_date) FROM read_parquet($pattern, hive_partitioning = true)",
        {"pattern": recursive_pattern},
    ).fetchone()

    max_base_date = row[0] if row else None
    if max_base_date is None:
        raise FileNotFoundError(f"'{mart_table}' 마트에서 조회 가능한 base_date 파티션을 찾을 수 없습니다.")

    return max_base_date.isoformat() if hasattr(max_base_date, "isoformat") else str(max_base_date)


_base_date_cache: TTLCache = TTLCache(
    maxsize=settings.base_date_cache_maxsize, ttl=settings.base_date_cache_ttl_seconds
)
_base_date_cache_lock = threading.Lock()
_BASE_DATE_SENTINEL = object()


def resolve_base_date_cached(con: duckdb.DuckDBPyConnection, mart_table: str) -> str:
    """resolve_base_date()와 동일한 값(mart_table의 최신 base_date)을 반환하지만, mart_table별로
    최대 settings.base_date_cache_ttl_seconds(기본 3600초=1시간) 동안 결과를 캐싱해 재계산을
    건너뛴다.

    resolve_base_date()는 hive_partitioning read_parquet로 마트 전체 이력(2023년부터 누적된
    수백 개 parquet 파일)을 열어 MAX(base_date)를 집계하므로 캐시 미스 시 수십 초가 걸릴 수 있다.
    이 마트들은 Airflow 배치로 하루 1회만 갱신되므로, 요청마다 이 무거운 스캔을 반복할 필요가
    없다 - 1시간에 한 번만 재계산해도 최신 데이터 반영이 실질적으로 지연되지 않는다.

    cachetools.TTLCache는 스레드-세이프하지 않으므로(FastAPI 동기 엔드포인트가 threadpool의
    여러 스레드에서 동시 실행될 수 있음) Lock으로 감싸되, 실제 계산(resolve_base_date 호출)은
    Lock 밖에서 수행해 느린 S3 스캔 동안 다른 요청이 캐시를 건드리지 못하는 상황을 피한다.
    서로 다른 요청이 같은 미스 키를 동시에 계산하는 드문 cache stampede가 가능하지만, 계산 자체가
    멱등이므로 결과 정합성에는 영향이 없다."""
    with _base_date_cache_lock:
        cached = _base_date_cache.get(mart_table, _BASE_DATE_SENTINEL)
    if cached is not _BASE_DATE_SENTINEL:
        return cached

    value = resolve_base_date(con, mart_table)
    with _base_date_cache_lock:
        _base_date_cache[mart_table] = value
    return value


def clear_base_date_cache() -> None:
    """테스트 격리 및 운영 중 강제 갱신을 위한 base_date 캐시 초기화."""
    with _base_date_cache_lock:
        _base_date_cache.clear()


def resolve_base_date_for_filter(
    con: duckdb.DuckDBPyConnection,
    mart_table: str,
    where_sql: str,
    params: dict[str, Any],
    *,
    max_lookback: int | None = None,
) -> str | None:
    """요청의 조회 조건(where_sql/params)에 매칭되는 row가 1건 이상 존재하는 가장 최근
    base_date를 찾는다. 파티션 존재 여부만 보는 resolve_base_date()와 달리, 실제 조건에
    매칭되는 데이터가 있는지까지 확인한다.

    최신 base_date부터 내림차순으로 최대 max_lookback개(생략 시
    settings.max_base_date_lookback) 파티션까지 `SELECT EXISTS(...LIMIT 1)` 형태의 가벼운
    쿼리로 순차 확인하며, 매칭되는 첫 base_date를 즉시 반환한다(조기 종료). 흔한 경우(최신
    파티션에 이미 데이터가 있음)는 쿼리 1회로 끝난다.

    max_lookback개를 모두 확인해도 매칭 데이터가 없으면 None을 반환한다(예외를 던지지
    않음 — 호출자가 기존 resolve_base_date()의 결과로 폴백해 빈 결과를 반환해야 한다).
    """
    candidates = list_base_dates(con, mart_table)
    naive_latest = candidates[0]
    lookback = max_lookback if max_lookback is not None else settings.max_base_date_lookback
    base_path = mart_base_path(mart_table)

    checked = 0
    for candidate in candidates[:lookback]:
        checked += 1
        glob_pattern = f"{base_path}/base_date={candidate}/*.parquet"
        query = f"""
            SELECT EXISTS(
                SELECT 1 FROM read_parquet($glob, hive_partitioning = true)
                {where_sql}
                LIMIT 1
            )
        """
        query_params = {**params, "glob": glob_pattern}
        matched = con.execute(query, query_params).fetchone()[0]
        if matched:
            if candidate != naive_latest:
                logger.info(
                    "Fallback used for table=%s, condition_summary=%s, "
                    "final_base_date=%s, lookback_partitions_checked=%d",
                    mart_table,
                    (where_sql or "(no filter)")[:100],
                    candidate,
                    checked,
                )
            return candidate

    return None


def raw_base_path(dataset: str) -> str:
    return f"s3://{settings.raw}/{dataset}"


def resolve_latest_date_partition(con: duckdb.DuckDBPyConnection, dataset: str) -> tuple[str, str, str]:
    """RAW 버킷의 year=yyyy/month=MM/day=dd 파티션 중 오늘 파티션을 우선 조회하고,
    없으면 가장 최근(최신) 날짜 파티션의 (year, month, day)를 반환한다."""
    base_path = raw_base_path(dataset)
    today = date.today()
    today_year, today_month, today_day = f"{today.year:04d}", f"{today.month:02d}", f"{today.day:02d}"

    today_pattern = f"{base_path}/year={today_year}/month={today_month}/day={today_day}/*.parquet"
    if con.execute("SELECT COUNT(*) FROM glob($pattern)", {"pattern": today_pattern}).fetchone()[0] > 0:
        return today_year, today_month, today_day

    all_pattern = f"{base_path}/year=*/month=*/day=*/*.parquet"
    paths = con.execute("SELECT file FROM glob($pattern)", {"pattern": all_pattern}).fetchall()
    if not paths:
        raise FileNotFoundError(f"'{dataset}' 데이터셋에서 조회 가능한 year/month/day 파티션을 찾을 수 없습니다.")

    partitions: set[tuple[str, str, str]] = set()
    for (path,) in paths:
        match = _PARTITION_PATTERN.search(path)
        if match:
            partitions.add(match.groups())

    if not partitions:
        raise FileNotFoundError(f"'{dataset}' 데이터셋 경로에서 year/month/day 파티션명을 파싱하지 못했습니다.")
    return max(partitions)


def resolve_latest_date_partition_for_filter(
    con: duckdb.DuckDBPyConnection,
    dataset: str,
    where_sql: str,
    params: dict[str, Any],
    *,
    max_lookback: int | None = None,
) -> tuple[str, str, str] | None:
    """RAW 버킷(year=/month=/day= 파티션)에서 where_sql/params 조건에 매칭되는 row가 1건
    이상 존재하는 가장 최근 (year, month, day)를 찾는다. resolve_base_date_for_filter의
    RAW 데이터셋 버전이며, 동작 원리(조기 종료/최대 max_lookback개/미매칭 시 None 반환/
    폴백 발생 시에만 로깅)는 동일하다. 파티션 자체가 하나도 없으면(=폴더 자체가 비어있음)
    resolve_latest_date_partition()과 동일하게 FileNotFoundError를 던진다."""
    base_path = raw_base_path(dataset)
    all_pattern = f"{base_path}/year=*/month=*/day=*/*.parquet"
    paths = con.execute("SELECT file FROM glob($pattern)", {"pattern": all_pattern}).fetchall()
    if not paths:
        raise FileNotFoundError(f"'{dataset}' 데이터셋에서 조회 가능한 year/month/day 파티션을 찾을 수 없습니다.")

    partitions: set[tuple[str, str, str]] = set()
    for (path,) in paths:
        match = _PARTITION_PATTERN.search(path)
        if match:
            partitions.add(match.groups())
    if not partitions:
        raise FileNotFoundError(f"'{dataset}' 데이터셋 경로에서 year/month/day 파티션명을 파싱하지 못했습니다.")

    candidates = sorted(partitions, reverse=True)
    naive_latest = candidates[0]
    lookback = max_lookback if max_lookback is not None else settings.max_base_date_lookback

    checked = 0
    for candidate in candidates[:lookback]:
        checked += 1
        year, month, day = candidate
        glob_pattern = f"{base_path}/year={year}/month={month}/day={day}/*.parquet"
        query = f"""
            SELECT EXISTS(
                SELECT 1 FROM read_parquet($glob, hive_partitioning = true)
                {where_sql}
                LIMIT 1
            )
        """
        query_params = {**params, "glob": glob_pattern}
        matched = con.execute(query, query_params).fetchone()[0]
        if matched:
            if candidate != naive_latest:
                logger.info(
                    "Fallback used for dataset=%s, condition_summary=%s, "
                    "final_partition=year=%s/month=%s/day=%s, lookback_partitions_checked=%d",
                    dataset,
                    (where_sql or "(no filter)")[:100],
                    year,
                    month,
                    day,
                    checked,
                )
            return candidate

    return None


def resolve_recent_match_date(
    con: duckdb.DuckDBPyConnection,
    glob_pattern: str,
    date_column: str,
    where_sql: str,
    params: dict[str, Any],
) -> date | None:
    """range-앵커형(apt_trend_service/rtt_service) 전용: 파티션을 하나씩 순회하지 않고,
    날짜 범위 제한 없이 전체 이력에서 where_sql/params 조건에 매칭되는 가장 최근
    date_column 값을 단일 `SELECT MAX(date_column)` 집계 쿼리로 찾는다. 비용이 파티션
    개수와 무관하게 일정하다(resolve_base_date_for_filter와 달리 조기 종료할 것도 없이
    쿼리 1회로 끝남). 매칭되는 row가 하나도 없으면 None을 반환한다. 이 함수 자체는
    로깅하지 않는다 — 호출자가 "나이브 조회 0건 → 이 함수 호출 → 창 이동" 흐름 전체를
    판단할 수 있으므로, 실제로 창이 이동된 경우의 로깅은 호출부(rtt_service/
    apt_trend_service)에서 수행한다."""
    query = f"""
        SELECT MAX({date_column})
        FROM read_parquet($glob, hive_partitioning = true)
        {where_sql}
    """
    query_params = {**params, "glob": glob_pattern}
    row = con.execute(query, query_params).fetchone()
    return row[0] if row and row[0] is not None else None


def to_json_safe(value: Any) -> Any:
    """DuckDB가 반환하는 Decimal/date/datetime 등을 JSON 응답용 기본 타입으로 변환한다."""
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def rows_to_dicts(result: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    """DuckDB 쿼리 결과를 컬럼 생략 없이 JSON-safe한 딕셔너리 리스트로 변환한다."""
    columns = [col[0] for col in result.description]
    return [
        {col: to_json_safe(val) for col, val in zip(columns, row)}
        for row in result.fetchall()
    ]
