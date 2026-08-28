from typing import Any

from app.core import duckdb_client

MART_TABLE = "dm_apt_price_avg"
TOP_BOTTOM_LIMIT = 5


def _build_where_clause(
    region_cgg_cd: str | None, region_stdg_cd: str | None
) -> tuple[str, dict[str, str]]:
    """평당가/매매가가 유효한(0 초과) row만 대상으로 하고, 주어진 지역 조건을 동적으로 추가한다."""
    conditions = ["deal_cnt > 0", "total_pyeong_amt > 0", "total_thing_amt > 0"]
    params: dict[str, str] = {}
    if region_cgg_cd:
        conditions.append("cgg_cd = $cgg_cd")
        params["cgg_cd"] = region_cgg_cd
    if region_stdg_cd:
        conditions.append("stdg_cd = $stdg_cd")
        params["stdg_cd"] = region_stdg_cd
    return "WHERE " + " AND ".join(conditions), params


def _metric_column(metric_type: str) -> str:
    """metric_type에 대응하는 정렬 기준 컬럼명을 반환한다."""
    return "avg_pyeong_amt" if metric_type == "pyeong" else "avg_thing_amt"


def _fetch_ranked(
    con,
    base_date: str,
    region_cgg_cd: str | None,
    region_stdg_cd: str | None,
    metric_type: str,
    order: str,
    exclude_items: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """아파트별 평균 거래가/평균 평당가(각 total_*_amt / deal_cnt, 반올림)를 계산하고
    metric_type 기준 컬럼으로 정렬하여 상위/하위 row를 추출한다. exclude_items가 주어지면
    (cgg_cd, stdg_cd, bldg_nm) 키가 일치하는 row는 결과에서 제외한다(top/bottom 중복 방지)."""
    parquet_glob = f"{duckdb_client.mart_base_path(MART_TABLE)}/base_date={base_date}/*.parquet"
    where_clause, params = _build_where_clause(region_cgg_cd, region_stdg_cd)
    metric_column = _metric_column(metric_type)

    exclude_clause = ""
    if exclude_items:
        tuples = []
        for i, item in enumerate(exclude_items):
            tuples.append(f"($cgg_cd_ex{i}, $stdg_cd_ex{i}, $bldg_nm_ex{i})")
            params[f"cgg_cd_ex{i}"] = item["cgg_cd"]
            params[f"stdg_cd_ex{i}"] = item["stdg_cd"]
            params[f"bldg_nm_ex{i}"] = item["bldg_nm"]
        exclude_clause = f" AND (cgg_cd, stdg_cd, bldg_nm) NOT IN ({', '.join(tuples)})"

    query = f"""
        SELECT
            * EXCLUDE (total_thing_amt, total_pyeong_amt),
            CAST(ROUND(total_thing_amt::DOUBLE / deal_cnt) AS BIGINT) AS avg_thing_amt,
            CAST(ROUND(total_pyeong_amt::DOUBLE / deal_cnt) AS BIGINT) AS avg_pyeong_amt
        FROM read_parquet('{parquet_glob}', hive_partitioning = true)
        {where_clause}
        {exclude_clause}
        ORDER BY {metric_column} {order}
        LIMIT {TOP_BOTTOM_LIMIT}
    """
    result = con.execute(query, params)
    return duckdb_client.rows_to_dicts(result)


def _count_rows(
    con,
    base_date: str,
    region_cgg_cd: str | None,
    region_stdg_cd: str | None,
) -> int:
    """지정된 지역 조건에 해당하는 아파트(row) 개수를 센다."""
    parquet_glob = f"{duckdb_client.mart_base_path(MART_TABLE)}/base_date={base_date}/*.parquet"
    where_clause, params = _build_where_clause(region_cgg_cd, region_stdg_cd)

    query = f"""
        SELECT COUNT(*)
        FROM read_parquet('{parquet_glob}', hive_partitioning = true)
        {where_clause}
    """
    (row_count,) = con.execute(query, params).fetchone()
    return row_count or 0


def _fetch_summary(
    con,
    base_date: str,
    region_cgg_cd: str | None,
    region_stdg_cd: str | None,
) -> tuple[int, int, int]:
    """지정된 지역 조건에 해당하는 전체 거래건수와 평균 거래금액/평균 평당가(반올림)를 집계한다."""
    parquet_glob = f"{duckdb_client.mart_base_path(MART_TABLE)}/base_date={base_date}/*.parquet"
    where_clause, params = _build_where_clause(region_cgg_cd, region_stdg_cd)

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


def get_top_bottom(
    *, region_cgg_cd: str | None, region_stdg_cd: str | None, metric_type: str
) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]], int, int, int]:
    """지정된(선택적) 지역 조건 내 아파트별 metric_type 기준(평균 평당가 또는 평균 거래가) 상위/하위 5개와
    전체 집계(총 거래건수/평균 거래금액/평균 평당가)를 MinIO Parquet에서 동적으로 조회한다."""
    con = duckdb_client.get_connection()
    try:
        base_date = duckdb_client.resolve_base_date(con, MART_TABLE)
        row_count = _count_rows(con, base_date, region_cgg_cd, region_stdg_cd)
        top_items = _fetch_ranked(con, base_date, region_cgg_cd, region_stdg_cd, metric_type, "DESC")
        bottom_items = (
            _fetch_ranked(
                con, base_date, region_cgg_cd, region_stdg_cd, metric_type, "ASC", exclude_items=top_items
            )
            if row_count > TOP_BOTTOM_LIMIT
            else []
        )
        total_count, avg_thing_amt, avg_pyeong_amt = _fetch_summary(
            con, base_date, region_cgg_cd, region_stdg_cd
        )
    finally:
        con.close()
    return base_date, top_items, bottom_items, total_count, avg_thing_amt, avg_pyeong_amt
