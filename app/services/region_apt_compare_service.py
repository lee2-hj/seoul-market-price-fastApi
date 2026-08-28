from typing import Any

from app.core import duckdb_client

# dm_apt_recent_trade 마트 실제 컬럼(DESCRIBE로 확인):
# apt_id, apt_name, sgg_cd, sgg_nm, dong_cd, dong_nm, build_year, mno, sno,
# total_trade_amount(BIGINT, 만원 합계), total_price_per_pyeong(BIGINT, 평당가 합계),
# total_pyeong(DOUBLE, 전용면적(평) 합계), latest_trade_amount, latest_trade_pyeong(DOUBLE, 최근 거래
# 전용면적(평)), trade_count(INTEGER), household_count(INTEGER), use_approval_date, use_approval_year,
# base_date. total_trade_amount/total_price_per_pyeong/total_pyeong은 다른 dm_ 마트(예: dm_apt_price_avg의
# total_thing_amt/total_pyeong_amt)와 동일한 관례로 trade_count건의 합계이므로, 평균값은 각각을
# trade_count로 나눠 계산한다. 이 마트는 이미 "최근" 실거래를 base_date 파티션 단위로 사전집계해 두므로,
# 최신 base_date 파티션만 읽으면 최근 90일 조회 조건을 만족한다(다른 dm_ 마트와 동일).
MART_TABLE = "dm_apt_recent_trade"


def _fetch_apt_row(
    con,
    base_date: str,
    cgg_cd: str,
    bjd_cd: str,
    apt_nm: str,
    mno: str,
    sno: str,
) -> dict[str, Any] | None:
    """자치구코드(sgg_cd)+법정동코드(dong_cd)+아파트명(apt_name)+지번 본번(mno)/부번(sno)이 모두 일치하는
    단지 row 하나를 dm_apt_recent_trade 마트의 최신 base_date 파티션에서 조회한다. 같은 법정동 안에 동명
    단지가 존재할 수 있어(예: 같은 dong_cd 안에 apt_name이 중복되는 경우) 다섯 조건 모두 필수로 AND
    결합해야 단지 하나로 정확히 특정된다."""
    parquet_glob = f"{duckdb_client.mart_base_path(MART_TABLE)}/base_date={base_date}/*.parquet"
    params: dict[str, str] = {
        "cgg_cd": cgg_cd,
        "bjd_cd": bjd_cd,
        "apt_nm": apt_nm,
        "mno": mno,
        "sno": sno,
    }
    query = f"""
        SELECT
            apt_name, household_count, build_year, use_approval_date,
            total_trade_amount, total_price_per_pyeong, total_pyeong,
            latest_trade_pyeong, trade_count
        FROM read_parquet('{parquet_glob}', hive_partitioning = true)
        WHERE sgg_cd = $cgg_cd AND dong_cd = $bjd_cd AND apt_name = $apt_nm
          AND mno = $mno AND sno = $sno
    """
    result = con.execute(query, params)
    rows = duckdb_client.rows_to_dicts(result)
    return rows[0] if rows else None


def _build_group(row: dict[str, Any] | None) -> dict[str, Any]:
    """row를 응답용 비교 지표로 가공한다. avg_deal_price/avg_pyeong_price/avg_pyeong은 각각
    total_trade_amount/total_price_per_pyeong/total_pyeong을 trade_count로 나눠 반올림한 정수다.
    latest_trade_pyeong도 원본 값을 반올림한 정수로 전달한다. 매칭되는 row가 없거나(단지 자체를 못 찾음)
    trade_count가 0이면(최근 90일간 거래 없음) 빈 딕셔너리({})를 반환한다."""
    trade_count = (row or {}).get("trade_count") or 0
    if row is None or trade_count == 0:
        return {}

    total_trade_amount = row.get("total_trade_amount") or 0
    total_price_per_pyeong = row.get("total_price_per_pyeong") or 0
    total_pyeong = row.get("total_pyeong") or 0
    latest_trade_pyeong = row.get("latest_trade_pyeong")
    avg_deal_price = round(total_trade_amount / trade_count)
    avg_pyeong_price = round(total_price_per_pyeong / trade_count)
    avg_pyeong = round(total_pyeong / trade_count)

    return {
        "apt_name": row.get("apt_name"),
        "avg_deal_price": avg_deal_price,
        "avg_pyeong_price": avg_pyeong_price,
        "avg_pyeong": avg_pyeong,
        "latest_trade_pyeong": round(latest_trade_pyeong) if latest_trade_pyeong is not None else None,
        "deal_count": trade_count,
        "total_households": row.get("household_count"),
        "build_year": row.get("build_year"),
        "use_approval_date": row.get("use_approval_date"),
    }


def compare_region_apts(
    *,
    cgg_cd_1: str,
    bjd_cd_1: str,
    apt_nm_1: str,
    mno_1: str,
    sno_1: str,
    cgg_cd_2: str,
    bjd_cd_2: str,
    apt_nm_2: str,
    mno_2: str,
    sno_2: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """dm_apt_recent_trade 마트(최신 base_date 파티션, 최근 90일 실거래 사전집계)에서 아파트1/아파트2 각각을
    자치구코드+법정동코드+아파트명+지번 본번/부번(모두 필수)으로 특정해, 비교 지표(평균 매매가/평균 평당가/
    평균 전용면적/최근 거래 전용면적/거래건수)와 메타데이터(세대수/준공년도/사용승인일)를 조회한다. 두 단지
    조회는 서로 독립적이라 한쪽이 매칭되지 않아도(또는 최근 90일간 거래가 없어도, 빈 딕셔너리로) 나머지
    한쪽은 정상적으로 반환된다."""
    con = duckdb_client.get_connection()
    try:
        base_date = duckdb_client.resolve_base_date(con, MART_TABLE)
        row_1 = _fetch_apt_row(con, base_date, cgg_cd_1, bjd_cd_1, apt_nm_1, mno_1, sno_1)
        row_2 = _fetch_apt_row(con, base_date, cgg_cd_2, bjd_cd_2, apt_nm_2, mno_2, sno_2)
    finally:
        con.close()

    return _build_group(row_1), _build_group(row_2)
