from typing import Any

from app.core import duckdb_client

MART_TABLE_BY_QUERY_TYPE: dict[str, str] = {
    "pyeong": "dm_apt_pyeong_price",
    "floor": "dm_apt_flr_price",
}

GRP_COLUMN_BY_QUERY_TYPE: dict[str, str] = {
    "pyeong": "pyeong_grp",
    "floor": "flr_grp",
}


def compare_apartments(
    *, cgg_cd: str, stdg_cd: str, bldg_nm: str | None, mno: str, sno: str, query_type: str, grp: str | None
) -> tuple[str, list[dict[str, Any]]]:
    """query_type(평단가/층별가)에 해당하는 마트의 최신 base_date 파티션에서
    자치구코드(cgg_cd) + 법정동코드(stdg_cd) + 지번 본번(mno) + 지번 부번(sno) + 건물명(bldg_nm, 선택, 부분일치 LIKE) +
    그룹(grp, 선택, pyeong_grp 또는 flr_grp 컬럼)이 일치하는 row를 가공 없이 그대로 조회한다."""
    mart_table = MART_TABLE_BY_QUERY_TYPE[query_type]
    grp_column = GRP_COLUMN_BY_QUERY_TYPE[query_type]
    con = duckdb_client.get_connection()
    try:
        base_date = duckdb_client.resolve_base_date(con, mart_table)
        parquet_glob = f"{duckdb_client.mart_base_path(mart_table)}/base_date={base_date}/*.parquet"
        params: dict[str, str] = {"cgg_cd": cgg_cd, "stdg_cd": stdg_cd, "mno": mno, "sno": sno}
        where_clause = "WHERE cgg_cd = $cgg_cd AND stdg_cd = $stdg_cd AND mno = $mno AND sno = $sno"
        if bldg_nm:
            where_clause += " AND bldg_nm LIKE $bldg_nm"
            params["bldg_nm"] = f"%{bldg_nm}%"
        if grp:
            where_clause += f" AND {grp_column} = $grp"
            # 마트의 pyeong_grp 컬럼은 최상위 구간을 "40+"로 저장하므로, 입력값 "40"을 "40+"로 변환해 조회한다.
            params["grp"] = "40+" if query_type == "pyeong" and grp == "40" else grp

        query = f"""
            SELECT *
            FROM read_parquet('{parquet_glob}', hive_partitioning = true)
            {where_clause}
        """
        result = con.execute(query, params)
        items = duckdb_client.rows_to_dicts(result)
    finally:
        con.close()
    return base_date, items


def fetch_recent_supply_pyeong(
    *, cgg_cd: str, stdg_cd: str, bldg_nm: str | None, mno: str, sno: str
) -> float | None:
    """dm_apt_pyeong_price 마트에는 있지만 dm_apt_flr_price 마트에는 없는 recent_supply_pyeong을 보완하기 위해,
    자치구코드+법정동코드+지번 본번(mno)+지번 부번(sno)(+건물명, 선택)이 일치하는 row 중 recent_deal_date가 가장
    최근인 row의 recent_supply_pyeong 값을 조회한다. query_type='floor' 조회 시 사용."""
    mart_table = MART_TABLE_BY_QUERY_TYPE["pyeong"]
    con = duckdb_client.get_connection()
    try:
        base_date = duckdb_client.resolve_base_date(con, mart_table)
        parquet_glob = f"{duckdb_client.mart_base_path(mart_table)}/base_date={base_date}/*.parquet"
        params: dict[str, str] = {"cgg_cd": cgg_cd, "stdg_cd": stdg_cd, "mno": mno, "sno": sno}
        where_clause = "WHERE cgg_cd = $cgg_cd AND stdg_cd = $stdg_cd AND mno = $mno AND sno = $sno"
        if bldg_nm:
            where_clause += " AND bldg_nm LIKE $bldg_nm"
            params["bldg_nm"] = f"%{bldg_nm}%"

        query = f"""
            SELECT recent_supply_pyeong
            FROM read_parquet('{parquet_glob}', hive_partitioning = true)
            {where_clause}
            ORDER BY recent_deal_date DESC
            LIMIT 1
        """
        row = con.execute(query, params).fetchone()
    finally:
        con.close()
    return row[0] if row else None
