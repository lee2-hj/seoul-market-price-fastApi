import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import duckdb

from app.core.config import settings

_PARTITION_PATTERN = re.compile(r"year=(\d{4})/month=(\d{2})/day=(\d{2})")


def get_connection() -> duckdb.DuckDBPyConnection:
    """MinIO(S3 호환) 접속이 설정된 인메모리 DuckDB 커넥션을 생성한다."""
    con = duckdb.connect(database=":memory:")
    con.execute("INSTALL httpfs;")
    con.execute("LOAD httpfs;")
    con.execute(f"SET s3_endpoint = '{settings.s3_end_point}';")
    con.execute(f"SET s3_access_key_id = '{settings.s3_access_key}';")
    con.execute(f"SET s3_secret_access_key = '{settings.s3_secret_key}';")
    con.execute(f"SET s3_url_style = '{settings.s3_url_style}';")
    con.execute(f"SET s3_use_ssl = {'true' if settings.s3_use_ssl else 'false'};")
    con.execute(f"SET s3_region = '{settings.aws_region}';")
    return con


def mart_base_path(mart_table: str) -> str:
    return f"s3://{settings.lake}/mart/{mart_table}"


def resolve_base_date(con: duckdb.DuckDBPyConnection, mart_table: str) -> str:
    """배치 당일 파티션을 우선 조회하고, 없으면 최신(MAX) base_date 파티션을 선택한다."""
    today_str = date.today().isoformat()
    base_path = mart_base_path(mart_table)

    today_pattern = f"{base_path}/base_date={today_str}/*.parquet"
    if con.execute("SELECT COUNT(*) FROM glob($pattern)", {"pattern": today_pattern}).fetchone()[0] > 0:
        return today_str

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
    return max(available_dates)


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
