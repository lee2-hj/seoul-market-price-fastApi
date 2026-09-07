import logging
from datetime import date, timedelta
from typing import Any

from app.core import duckdb_client
from app.core.cache import cached_call
from app.core.config import settings

MART_TABLE_BY_QUERY_TYPE: dict[str, str] = {
    "pyeong": "dm_apt_pyeong_price",
    "floor": "dm_apt_flr_price",
}

GRP_COLUMN_BY_QUERY_TYPE: dict[str, str] = {
    "pyeong": "pyeong_grp",
    "floor": "flr_grp",
}

# --- 실버(Iceberg fact) 레이어 Fallback -------------------------------------------------
# dm_apt_pyeong_price/dm_apt_flr_price도 apt_mkt_trends와 같은 종류의 문제를 갖고 있다 - 실측
# 확인 결과 이 두 마트의 recent_deal_date는 약 85~90일 폭의 롤링 구간(예: 2026-06-10~2026-09-04)
# 만 보존하고 있어, 특정 단지·특정 그룹(pyeong_grp/flr_grp)의 마지막 실거래가 그보다 오래되면
# 이 마트 안에서는 영영 찾을 수 없다(예: 강남구 개포동 '개포자이' 11680/10300/0012/0002 -
# 마지막 실거래 2026-05-15가 마트 보존 시작일보다 앞서 두 마트 모두에 아예 없음, 그러나
# fact_apt_transactions 원본에는 실거래 존재). 이 경우 원본 실거래 팩트 테이블
# (fact_apt_transactions, Iceberg)까지 온디맨드로 내려가 [해당 단지+그룹의 마지막 거래일 - 89일
# ~ 마지막 거래일] 구간을 집계한다.
#
# SUPPLY_AREA_FACTOR/PYEONG_DIVISOR와 grp 산정식은 실제 운영 마트 데이터와 fact_apt_transactions
# 원본을 교차 검증해 확인했다:
#   - pyeong_grp: supply_pyeong(=exclusive_area_m2 * 1.3 / 3.305785)을 반올림해 10 단위로
#     버킷팅하고(예: 22.77 -> 20, 45.15 -> 40+), 40 이상은 전부 "40+"로 표기한다
#     (region_apt_compare_service의 latest_trade_pyeong과 동일한 1.3배 공급면적 환산).
#   - flr_grp: floor <= 5 = LOW, 6~15 = MID, 16 이상 = HIGH(고정 전역 임계값. 실측으로
#     min/max(floor) per flr_grp를 집계해 건물별 상대 기준이 아니라 고정 임계값임을 확인했다).
#   - deal_cnt/total_thing_amt/total_pyeong_amt/recent_* 값은 base_date 파티션의 [base_date - 89일
#     ~ base_date] 구간 원본 거래 합계/최근값과 정확히 일치함을 확인했다(dm_apt_recent_trade와
#     동일한 관례). Fallback에서는 base_date 대신 "이 단지+그룹의 마지막 거래일"을 앵커로 쓴다.
#
# latitude/longitude/is_exact_location/updated_at/cgg_nm/stdg_nm은 fact_apt_transactions에 없는
# 값이다(지오코딩 결과는 이 프로젝트의 실버 계층에 존재하지 않음). 이 필드들은 스키마상 모두
# Optional이므로(AptCompareResponse), Fallback 시 cgg_nm/stdg_nm은 dim_apartment로 보완하고
# latitude/longitude/is_exact_location/updated_at은 None으로 둔다(값을 지어내지 않는다).
SILVER_TABLE = settings.silver_apt_transactions_table
SUPPLY_AREA_FACTOR = 1.3
PYEONG_DIVISOR = 3.305785
SILVER_WINDOW_DAYS = 90
CACHE_NAMESPACE = "apt_compare:silver_fallback"

logger = logging.getLogger(__name__)


def _build_where_clause(
    cgg_cd: str,
    stdg_cd: str,
    mno: str,
    sno: str,
    bldg_nm: str | None,
    grp_column: str | None,
    grp: str | None,
) -> tuple[str, dict[str, str]]:
    """자치구코드+법정동코드+지번 본번/부번(모두 필수) 조건에 건물명(선택, 부분일치 LIKE)과
    그룹(grp_column/grp, 선택) 조건을 동적으로 추가한다. base_date 매칭 여부 확인
    (resolve_base_date_for_filter)과 실제 데이터 조회가 동일한 조건을 재사용한다."""
    params: dict[str, str] = {"cgg_cd": cgg_cd, "stdg_cd": stdg_cd, "mno": mno, "sno": sno}
    where_clause = "WHERE cgg_cd = $cgg_cd AND stdg_cd = $stdg_cd AND mno = $mno AND sno = $sno"
    if bldg_nm:
        where_clause += " AND bldg_nm LIKE $bldg_nm"
        params["bldg_nm"] = f"%{bldg_nm}%"
    if grp_column and grp:
        where_clause += f" AND {grp_column} = $grp"
        params["grp"] = grp
    return where_clause, params


def _pyeong_grp_label(supply_pyeong: float) -> str:
    """공급면적 평(supply_pyeong)을 10평 단위로 버킷팅한다. dm_apt_pyeong_price의 pyeong_grp 컬럼과
    동일한 규칙(실측 확인): 반올림한 값을 10으로 나눠 버킷팅하고, 40 이상은 전부 "40+"로 표기한다."""
    bucket = (round(supply_pyeong) // 10) * 10
    if bucket >= 40:
        return "40+"
    return str(bucket) if bucket >= 10 else "10"


def _flr_grp_label(floor: int) -> str:
    """층수를 LOW/MID/HIGH로 버킷팅한다. dm_apt_flr_price의 flr_grp 컬럼과 동일한 고정 전역
    임계값(실측 확인: flr_grp별 MIN/MAX(floor)가 건물마다 다르지 않고 항상 이 경계와 일치)."""
    if floor <= 5:
        return "LOW"
    if floor <= 15:
        return "MID"
    return "HIGH"


def _fetch_silver_group_row(
    con,
    cgg_cd: str,
    stdg_cd: str,
    bldg_nm: str | None,
    mno: str,
    sno: str,
    query_type: str,
    grp: str,
) -> dict[str, Any] | None:
    """골드 마트(dm_apt_pyeong_price/dm_apt_flr_price)에 이 단지+그룹(grp)에 해당하는 row가 없을 때,
    실버(fact_apt_transactions, Iceberg) 원본에서 이 단지의 전체 이력을 스캔해 grp 조건에 맞는
    거래만 추려 [그 그룹의 마지막 거래일 - 89일 ~ 마지막 거래일] 구간을 집계한다. 그룹별로
    마지막 거래일이 서로 다를 수 있으므로(예: 20평형은 8월, 40평형대는 6월에 마지막 거래) 앵커는
    항상 "이 단지의 마지막 거래일"이 아니라 "이 단지+이 그룹의 마지막 거래일"이다(골드 마트에서도
    그룹별 recent_deal_date가 서로 다름을 실측으로 확인했다).

    반환 dict는 골드 row와 동일한 키(cgg_cd/stdg_cd/bldg_nm/mno/sno/pyeong_grp 또는 flr_grp/
    deal_cnt/total_thing_amt/total_pyeong_amt/recent_thing_amt/recent_pyeong_amt/
    recent_deal_date/recent_supply_pyeong 또는 recent_floor)를 담아, 호출자가 기존 응답 조립
    로직(엔드포인트의 _build_group)에 그대로 넘길 수 있게 한다. latitude/longitude/
    is_exact_location/updated_at은 원본에 없는 지오코딩 값이라 None으로 둔다(스키마상 Optional).

    이 단지에 매칭되는 거래 자체가 없거나, 있어도 이 grp에 해당하는 거래가 없으면 None을 반환한다."""
    if not bldg_nm or not grp:
        # bldg_nm 없이는 실버에서 단지를 정확히 특정할 수 없고(골드도 사실상 mno/sno로 이미
        # 특정되지만, apt_name 없이는 원본 조회 조건을 구성할 수 없다), grp 없이는 버킷 필터를
        # 적용할 수 없다.
        return None

    con.execute("INSTALL iceberg;")
    con.execute("LOAD iceberg;")

    path = duckdb_client.silver_base_path(SILVER_TABLE)
    query = """
        SELECT deal_date, price_ten_thousand, exclusive_area_m2, floor
        FROM iceberg_scan($path)
        WHERE sgg_cd = $sgg_cd AND dong_cd = $dong_cd AND apt_name ILIKE $apt_name
          AND mno = $mno AND sno = $sno
          AND (cancel_date IS NULL OR cancel_date = '')
    """
    params = {
        "path": path,
        "sgg_cd": cgg_cd,
        "dong_cd": stdg_cd,
        "apt_name": f"%{bldg_nm}%",
        "mno": mno,
        "sno": sno,
    }
    rows = duckdb_client.rows_to_dicts(con.execute(query, params))
    if not rows:
        return None

    matching: list[dict[str, Any]] = []
    for row in rows:
        supply_pyeong = row["exclusive_area_m2"] * SUPPLY_AREA_FACTOR / PYEONG_DIVISOR
        if query_type == "pyeong":
            label = _pyeong_grp_label(supply_pyeong)
        else:
            label = _flr_grp_label(row["floor"])
        if label == grp:
            row["supply_pyeong"] = supply_pyeong
            matching.append(row)
    if not matching:
        return None

    last_date = max(r["deal_date"] for r in matching)  # ISO 문자열, 사전식 비교 = 날짜순
    window_start = (date.fromisoformat(last_date) - timedelta(days=SILVER_WINDOW_DAYS - 1)).isoformat()
    windowed = [r for r in matching if window_start <= r["deal_date"] <= last_date]

    deal_cnt = len(windowed)
    total_thing_amt = round(sum(r["price_ten_thousand"] for r in windowed))
    total_pyeong_amt = round(sum(r["price_ten_thousand"] / r["supply_pyeong"] for r in windowed))
    latest = max(windowed, key=lambda r: r["deal_date"])

    result: dict[str, Any] = {
        "cgg_cd": cgg_cd,
        "cgg_nm": None,
        "stdg_cd": stdg_cd,
        "stdg_nm": None,
        "bldg_nm": bldg_nm,
        "latitude": None,
        "longitude": None,
        "is_exact_location": None,
        "mno": mno,
        "sno": sno,
        "updated_at": None,
        "deal_cnt": deal_cnt,
        "total_thing_amt": total_thing_amt,
        "total_pyeong_amt": total_pyeong_amt,
        "recent_thing_amt": round(latest["price_ten_thousand"]),
        "recent_pyeong_amt": round(latest["price_ten_thousand"] / latest["supply_pyeong"]),
        "recent_deal_date": latest["deal_date"],
    }
    if query_type == "pyeong":
        result["pyeong_grp"] = grp
        result["recent_supply_pyeong"] = round(latest["supply_pyeong"], 2)
    else:
        result["flr_grp"] = grp
        result["recent_floor"] = latest["floor"]

    name_rows = duckdb_client.rows_to_dicts(
        con.execute(
            "SELECT ANY_VALUE(sgg_nm) AS cgg_nm, ANY_VALUE(dong_nm) AS stdg_nm "
            "FROM iceberg_scan($path) WHERE sgg_cd = $sgg_cd AND dong_cd = $dong_cd",
            {
                "path": duckdb_client.silver_base_path("dim_apartment"),
                "sgg_cd": cgg_cd,
                "dong_cd": stdg_cd,
            },
        )
    )
    if name_rows:
        result["cgg_nm"] = name_rows[0]["cgg_nm"]
        result["stdg_nm"] = name_rows[0]["stdg_nm"]

    return result


def compare_apartments(
    *, cgg_cd: str, stdg_cd: str, bldg_nm: str | None, mno: str, sno: str, query_type: str, grp: str | None
) -> tuple[str, list[dict[str, Any]]]:
    """query_type(평단가/층별가)에 해당하는 마트에서 자치구코드(cgg_cd) + 법정동코드(stdg_cd) +
    지번 본번(mno) + 지번 부번(sno) + 건물명(bldg_nm, 선택, 부분일치 LIKE) + 그룹(grp, 선택,
    pyeong_grp 또는 flr_grp 컬럼)이 일치하는 row를 가공 없이 그대로 조회한다. base_date는
    이 조건에 매칭되는 데이터가 있는 가장 최근 파티션까지 소급 탐색한다.

    골드 마트 전체 파티션에서도 이 단지+그룹에 매칭되는 row가 없으면(bldg_nm/grp가 모두 주어진
    경우에 한해), 실버(fact_apt_transactions) 레이어에서 이 단지+그룹의 마지막 거래일 기준 과거
    90일 구간을 온디맨드로 집계해 대체한다(_fetch_silver_group_row). 결과는 최소 1시간 캐싱된다.
    실버에도 매칭이 없으면 빈 리스트를 그대로 반환한다(호출자가 기존 관례대로 처리)."""
    mart_table = MART_TABLE_BY_QUERY_TYPE[query_type]
    grp_column = GRP_COLUMN_BY_QUERY_TYPE[query_type]

    resolved_grp = grp
    if grp and query_type == "pyeong" and grp == "40":
        # 마트의 pyeong_grp 컬럼은 최상위 구간을 "40+"로 저장하므로, 입력값 "40"을 "40+"로 변환해 조회한다.
        resolved_grp = "40+"

    con = duckdb_client.get_connection()
    try:
        where_clause, params = _build_where_clause(
            cgg_cd, stdg_cd, mno, sno, bldg_nm, grp_column, resolved_grp
        )
        base_date = duckdb_client.resolve_base_date_for_filter(
            con, mart_table, where_clause, params
        ) or duckdb_client.resolve_base_date(con, mart_table)
        parquet_glob = f"{duckdb_client.mart_base_path(mart_table)}/base_date={base_date}/*.parquet"

        query = f"""
            SELECT *
            FROM read_parquet('{parquet_glob}', hive_partitioning = true)
            {where_clause}
        """
        result = con.execute(query, params)
        items = duckdb_client.rows_to_dicts(result)

        if not items and resolved_grp:
            cache_key = (cgg_cd, stdg_cd, bldg_nm, mno, sno, query_type, resolved_grp)
            silver_item = cached_call(
                CACHE_NAMESPACE,
                cache_key,
                lambda: _fetch_silver_group_row(
                    con, cgg_cd, stdg_cd, bldg_nm, mno, sno, query_type, resolved_grp
                ),
            )
            if silver_item is not None:
                items = [silver_item]
                base_date = silver_item["recent_deal_date"]
                logger.info(
                    "Silver fallback used for table=%s, cgg_cd=%s, stdg_cd=%s, bldg_nm=%s, "
                    "mno=%s, sno=%s, grp=%s, base_date=%s",
                    SILVER_TABLE,
                    cgg_cd,
                    stdg_cd,
                    bldg_nm,
                    mno,
                    sno,
                    resolved_grp,
                    base_date,
                )
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
        where_clause, params = _build_where_clause(cgg_cd, stdg_cd, mno, sno, bldg_nm, None, None)
        base_date = duckdb_client.resolve_base_date_for_filter(
            con, mart_table, where_clause, params
        ) or duckdb_client.resolve_base_date(con, mart_table)
        parquet_glob = f"{duckdb_client.mart_base_path(mart_table)}/base_date={base_date}/*.parquet"

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
