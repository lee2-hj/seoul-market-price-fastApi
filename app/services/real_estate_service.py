from typing import Any

from app.core import duckdb_client

DATASET = "real_estate"
PYEONG_DIVISOR = 3.305785


def get_latest_listings() -> tuple[str, list[dict[str, Any]]]:
    """RAW 버킷의 real_estate 데이터셋에서 오늘(없으면 가장 최근) 파티션의 아파트별 최신 실거래 목록을 조회한다.
    BLDG_USG = '아파트'인 row만 대상으로 하며(연립다세대/오피스텔/단독다가구 등은 제외), 같은 날 동일
    건물(자치구+법정동+지번+건물명)의 거래가 여러 건이면 매매가/평당가는 평균값으로 집계한다. price_change는
    같은 건물의 가장 최근 이전 거래일(과거 전체 파티션 중, 아파트 거래만) 대비 매매가 변동(만원)이다."""
    con = duckdb_client.get_connection()
    try:
        year, month, day = duckdb_client.resolve_latest_date_partition(con, DATASET)
        history_glob = f"{duckdb_client.raw_base_path(DATASET)}/**/*.parquet"

        query = f"""
            WITH daily AS (
                SELECT
                    CGG_CD AS cgg_cd,
                    ANY_VALUE(CGG_NM) AS cgg_nm,
                    STDG_CD AS stdg_cd,
                    ANY_VALUE(STDG_NM) AS stdg_nm,
                    BLDG_NM AS bldg_nm,
                    MNO AS mno,
                    SNO AS sno,
                    CAST(year AS VARCHAR) AS year,
                    month,
                    day,
                    AVG(TRY_CAST(THING_AMT AS DOUBLE)) AS avg_thing_amt,
                    AVG(TRY_CAST(THING_AMT AS DOUBLE) / NULLIF(ARCH_AREA / {PYEONG_DIVISOR}, 0)) AS avg_pyeong_amt
                FROM read_parquet($history_glob, hive_partitioning = true)
                WHERE BLDG_USG = '아파트'
                GROUP BY CGG_CD, STDG_CD, BLDG_NM, MNO, SNO, year, month, day
            ),
            with_prev AS (
                SELECT
                    *,
                    LAG(avg_thing_amt) OVER (
                        PARTITION BY cgg_cd, stdg_cd, mno, sno, bldg_nm
                        ORDER BY year, month, day
                    ) AS prev_avg_thing_amt
                FROM daily
            )
            SELECT
                bldg_nm AS apt_name,
                cgg_nm,
                stdg_nm,
                CAST(ROUND(avg_thing_amt) AS BIGINT) AS thing_amt,
                CAST(ROUND(avg_pyeong_amt) AS BIGINT) AS pyeong_amt,
                CASE
                    WHEN prev_avg_thing_amt IS NULL THEN NULL
                    ELSE CAST(ROUND(avg_thing_amt - prev_avg_thing_amt) AS BIGINT)
                END AS price_change,
                make_date(CAST(year AS INT), CAST(month AS INT), CAST(day AS INT)) AS update_date
            FROM with_prev
            WHERE year = $year AND month = $month AND day = $day
            ORDER BY apt_name
        """
        params = {"history_glob": history_glob, "year": year, "month": month, "day": day}
        result = con.execute(query, params)
        items = duckdb_client.rows_to_dicts(result)
    finally:
        con.close()

    base_date = f"{year}-{month}-{day}"
    return base_date, items
