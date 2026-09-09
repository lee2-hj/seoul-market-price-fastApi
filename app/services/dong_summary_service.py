from collections import OrderedDict
from typing import Any

from app.core import duckdb_client

MART_TABLE = "dm_dong_pyeong_price_avg"


def _build_where_clause(region_cgg: str | None) -> tuple[str, dict[str, str]]:
    """자치구 조건(코드 또는 명칭)을 동적으로 추가한다."""
    if not region_cgg:
        return "", {}
    return "WHERE (cgg_cd = $region_cgg OR cgg_nm = $region_cgg)", {"region_cgg": region_cgg}


def _fetch_rows(con, base_date: str, region_cgg: str | None) -> list[dict[str, Any]]:
    parquet_glob = f"{duckdb_client.mart_base_path(MART_TABLE)}/base_date={base_date}/*.parquet"
    where_clause, params = _build_where_clause(region_cgg)

    query = f"""
        SELECT *
        FROM read_parquet('{parquet_glob}', hive_partitioning = true)
        {where_clause}
    """
    result = con.execute(query, params)
    return duckdb_client.rows_to_dicts(result)


def _group_rows(
    rows: list[dict[str, Any]], code_field: str, name_field: str
) -> dict[str, dict[str, Any]]:
    """row 목록을 code_field(cgg_cd 또는 stdg_cd) 기준으로 그룹화하고, 그룹별 전체 거래건수(total_count =
    SUM(deal_cnt))와 평균 매매가(SUM(total_thing_amt) / total_count), 평균 평당가(SUM(total_pyeong_amt) /
    total_count)를 반올림하여 함께 집계한다. (compare.py의 _fetch_region_summary와 동일한 계산식)"""
    groups: "OrderedDict[str, dict[str, Any]]" = OrderedDict()
    for row in rows:
        code = row[code_field]
        group = groups.get(code)
        if group is None:
            group = {
                "code": code,
                "name": row[name_field],
                "_total_count": 0,
                "_sum_thing_amt": 0,
                "_sum_pyeong_amt": 0,
            }
            groups[code] = group
        group["_total_count"] += row["deal_cnt"]
        group["_sum_thing_amt"] += row["total_thing_amt"]
        group["_sum_pyeong_amt"] += row["total_pyeong_amt"]

    for group in groups.values():
        total_count = group.pop("_total_count")
        sum_thing_amt = group.pop("_sum_thing_amt")
        sum_pyeong_amt = group.pop("_sum_pyeong_amt")
        group["total_count"] = total_count
        group["avg_thing_amt"] = round(sum_thing_amt / total_count) if total_count else 0
        group["avg_pyeong_amt"] = round(sum_pyeong_amt / total_count) if total_count else 0

    return groups


def get_dong_summary(
    *, region_cgg: str | None
) -> tuple[str, dict[str, dict[str, Any]]]:
    """region_cgg가 없으면 cgg_cd끼리, 있으면 해당 자치구 내 데이터를 stdg_cd끼리 그룹화하여
    그룹별 집계(total_count/avg_thing_amt/avg_pyeong_amt)를 반환한다. base_date는 최신 파티션만
    보는 것이 아니라, 조건에 맞는 데이터가 있는 가장 최근 base_date까지 소급 조회한다."""
    con = duckdb_client.get_connection()
    try:
        where_clause, where_params = _build_where_clause(region_cgg)
        base_date = duckdb_client.resolve_base_date_for_filter(
            con, MART_TABLE, where_clause, where_params
        ) or duckdb_client.resolve_base_date_cached(con, MART_TABLE)
        rows = _fetch_rows(con, base_date, region_cgg)
        if region_cgg:
            groups = _group_rows(rows, "stdg_cd", "stdg_nm")
        else:
            groups = _group_rows(rows, "cgg_cd", "cgg_nm")
    finally:
        con.close()
    return base_date, groups
