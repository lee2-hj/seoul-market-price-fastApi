from typing import Any

from app.core import duckdb_client

MART_TABLE = "dm_dong_pyeong_price_avg"


def _build_where_clause(cgg_cd: str, stdg_cd: str | None) -> tuple[str, dict[str, str]]:
    conditions: list[str] = []
    params: dict[str, str] = {}
    if cgg_cd:
        conditions.append("cgg_cd = $cgg_cd")
        params["cgg_cd"] = cgg_cd
    if stdg_cd:
        conditions.append("stdg_cd = $stdg_cd")
        params["stdg_cd"] = stdg_cd
    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    return where_clause, params


def _fetch_region_rows(
    con,
    base_date: str,
    cgg_cd: str,
    stdg_cd: str | None,
) -> list[dict[str, Any]]:
    """선택된 base_date 파티션에서 자치구코드(필수) + 법정동코드(선택) 조건에 맞는 row를 동적으로 추출한다."""
    parquet_glob = f"{duckdb_client.mart_base_path(MART_TABLE)}/base_date={base_date}/*.parquet"
    where_clause, params = _build_where_clause(cgg_cd, stdg_cd)

    query = f"""
        SELECT *
        FROM read_parquet('{parquet_glob}', hive_partitioning = true)
        {where_clause}
    """
    result = con.execute(query, params)
    return duckdb_client.rows_to_dicts(result)


def _fetch_region_summary(
    con,
    base_date: str,
    cgg_cd: str,
    stdg_cd: str | None,
) -> tuple[int, int, int]:
    """선택된 base_date 파티션에서 자치구코드(필수) + 법정동코드(선택) 조건에 맞는 전체 거래건수(total_count)와
    평균 매매가(SUM(total_thing_amt) / 전체 거래건수), 평균 평당가(SUM(total_pyeong_amt) / 전체 거래건수)를
    반올림하여 집계한다."""
    parquet_glob = f"{duckdb_client.mart_base_path(MART_TABLE)}/base_date={base_date}/*.parquet"
    where_clause, params = _build_where_clause(cgg_cd, stdg_cd)

    query = f"""
        SELECT
            SUM(deal_cnt) AS total_count,
            SUM(total_thing_amt) AS sum_thing_amt,
            SUM(total_pyeong_amt) AS sum_pyeong_amt
        FROM read_parquet('{parquet_glob}', hive_partitioning = true)
        {where_clause}
    """
    total_count, sum_thing_amt, sum_pyeong_amt = con.execute(query, params).fetchone()
    total_count = total_count or 0
    avg_thing_amt = round(sum_thing_amt / total_count) if total_count else 0
    avg_pyeong_amt = round(sum_pyeong_amt / total_count) if total_count else 0
    return total_count, avg_thing_amt, avg_pyeong_amt


def compare_dong_pyeong(
    *,
    region1_cgg_cd: str,
    region1_stdg_cd: str | None,
    region2_cgg_cd: str,
    region2_stdg_cd: str | None,
) -> tuple[
    str,
    list[dict[str, Any]],
    list[dict[str, Any]],
    tuple[int, int, int],
    tuple[int, int, int],
]:
    """프론트에서 선택한 두 지역(자치구코드 필수 + 법정동코드 선택)의 동 단위 시세 데이터와
    지역별 집계(그룹별 데이터 개수/평균 매매가/평균 평당가)를 MinIO Parquet에서 동적으로 필터링한다."""
    con = duckdb_client.get_connection()
    try:
        base_date = duckdb_client.resolve_base_date(con, MART_TABLE)
        region1_items = _fetch_region_rows(con, base_date, region1_cgg_cd, region1_stdg_cd)
        region2_items = _fetch_region_rows(con, base_date, region2_cgg_cd, region2_stdg_cd)
        region1_summary = _fetch_region_summary(con, base_date, region1_cgg_cd, region1_stdg_cd)
        region2_summary = _fetch_region_summary(con, base_date, region2_cgg_cd, region2_stdg_cd)
    finally:
        con.close()
    return base_date, region1_items, region2_items, region1_summary, region2_summary
