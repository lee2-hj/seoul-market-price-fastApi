from typing import Any

from app.core import duckdb_client

MART_TABLE = "dm_main"


def get_recent_changes() -> tuple[str, str | None, list[dict[str, Any]]]:
    """dm_main 마트의 최신 base_date 파티션을 직전 base_date 파티션과 비교해, 신규로 추가됐거나
    (deal_cnt/total_thing_amt/total_pyeong_amt 중 하나라도) 값이 바뀐 행만 반환한다. 식별 키는
    (cgg_cd, stdg_cd, bldg_nm, mno, sno, area, deal_date)이며 mno/sno는 NULL 안전 비교(IS NOT
    DISTINCT FROM)로 조인한다. latitude/longitude 변경은 판정에서 제외하고 응답에만 노출한다.
    직전 파티션이 없으면(파티션이 1개뿐) 조인 없이 최신 파티션 전체를 status='NEW'로 반환한다."""
    con = duckdb_client.get_connection()
    try:
        base_date = duckdb_client.resolve_base_date(con, MART_TABLE)

        all_dates = duckdb_client.list_base_dates(con, MART_TABLE)
        compared_base_date = all_dates[1] if len(all_dates) > 1 else None

        latest_glob = f"{duckdb_client.mart_base_path(MART_TABLE)}/base_date={base_date}/*.parquet"

        if compared_base_date is not None:
            previous_glob = (
                f"{duckdb_client.mart_base_path(MART_TABLE)}/base_date={compared_base_date}/*.parquet"
            )
            query = """
                WITH latest AS (
                    SELECT cgg_cd, cgg_nm, stdg_cd, stdg_nm, bldg_nm, mno, sno, area, deal_date,
                           deal_cnt, total_thing_amt, total_pyeong_amt, latitude, longitude
                    FROM read_parquet($latest_glob, hive_partitioning = true)
                ),
                previous AS (
                    SELECT cgg_cd, stdg_cd, bldg_nm, mno, sno, area, deal_date,
                           deal_cnt, total_thing_amt, total_pyeong_amt
                    FROM read_parquet($previous_glob, hive_partitioning = true)
                )
                SELECT
                    l.cgg_cd, l.cgg_nm, l.stdg_cd, l.stdg_nm, l.bldg_nm, l.mno, l.sno, l.area,
                    l.deal_date, l.deal_cnt,
                    ROUND(l.total_thing_amt::DOUBLE / l.deal_cnt) AS thing_amt,
                    ROUND(l.total_pyeong_amt::DOUBLE / l.deal_cnt) AS pyeong_amt,
                    l.latitude, l.longitude,
                    CASE WHEN p.cgg_cd IS NULL THEN 'NEW' ELSE 'UPDATED' END AS status
                FROM latest l
                LEFT JOIN previous p
                    ON l.cgg_cd = p.cgg_cd AND l.stdg_cd = p.stdg_cd AND l.bldg_nm = p.bldg_nm
                    AND l.mno IS NOT DISTINCT FROM p.mno AND l.sno IS NOT DISTINCT FROM p.sno
                    AND l.area = p.area AND l.deal_date = p.deal_date
                WHERE p.cgg_cd IS NULL
                   OR l.deal_cnt IS DISTINCT FROM p.deal_cnt
                   OR l.total_thing_amt IS DISTINCT FROM p.total_thing_amt
                   OR l.total_pyeong_amt IS DISTINCT FROM p.total_pyeong_amt
                ORDER BY l.deal_date DESC, l.cgg_nm ASC, l.stdg_nm ASC, l.bldg_nm ASC
            """
            params = {"latest_glob": latest_glob, "previous_glob": previous_glob}
        else:
            query = """
                SELECT
                    cgg_cd, cgg_nm, stdg_cd, stdg_nm, bldg_nm, mno, sno, area, deal_date,
                    deal_cnt,
                    ROUND(total_thing_amt::DOUBLE / deal_cnt) AS thing_amt,
                    ROUND(total_pyeong_amt::DOUBLE / deal_cnt) AS pyeong_amt,
                    latitude, longitude,
                    'NEW' AS status
                FROM read_parquet($latest_glob, hive_partitioning = true)
                ORDER BY deal_date DESC, cgg_nm ASC, stdg_nm ASC, bldg_nm ASC
            """
            params = {"latest_glob": latest_glob}

        result = con.execute(query, params)
        items = duckdb_client.rows_to_dicts(result)
    finally:
        con.close()

    return base_date, compared_base_date, items
