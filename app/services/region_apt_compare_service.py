import logging
import time
from typing import Any

from app.core import duckdb_client
from app.core.cache import cached_call
from app.core.config import settings

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

# --- 실버(Iceberg fact) 레이어 Fallback -------------------------------------------------
# dm_apt_recent_trade에 매칭 row가 없거나(단지 자체가 없음) 있어도 trade_count == 0이면(최근 90일
# 거래 0건), fact_apt_transactions(원본 실거래 팩트 테이블, Iceberg)에서 이 단지의
# [마지막 거래일 - 89일 ~ 마지막 거래일] 구간을 온디맨드로 스캔해 동일한 집계식으로 대체한다.
#
# fact_apt_transactions 실제 컬럼: deal_date, sgg_cd, dong_cd, apt_name, price_ten_thousand
# (DECIMAL, 만원), exclusive_area_m2(DECIMAL, 전용면적), price_per_m2, floor, deal_type,
# cancel_date, agent_sgg_nm, mno, sno, deal_date_day(파티션 컬럼). 스키마가 파일마다 진화하므로
# (예: 오래된 파일엔 mno/sno 컬럼이 없음) 반드시 iceberg_scan()으로 읽어야 한다(read_parquet 단순
# glob은 스키마 불일치로 실패한다).
#
# SUPPLY_AREA_FACTOR(전용면적 -> "평" 환산 시 곱하는 배수)는 dm_apt_recent_trade 운영 데이터와
# fact_apt_transactions 원본을 교차 검증해 역산했다(예: exclusive_area_m2=57.90 -> 실제 마트의
# latest_trade_pyeong=22.77 == round(57.90 * 1.3 / 3.305785, 2)). 여러 단지·여러 면적값에서
# total_trade_amount/latest_trade_amount/trade_count는 이 배수 없이도 원본 합계·건수만으로 마트
# 값과 정확히 일치했고, total_pyeong/total_price_per_pyeong/latest_trade_pyeong만 1.3배 차이가
# 나는 것을 확인해 이 상수를 얻었다. dataengineer ETL의 계산식이 바뀌면 이 상수도 함께 갱신해야 한다.
SILVER_TABLE = settings.silver_apt_transactions_table
SUPPLY_AREA_FACTOR = 1.3
PYEONG_DIVISOR = 3.305785
SILVER_WINDOW_DAYS = 90
SILVER_QUERY_RETRY_ATTEMPTS = 3
SILVER_QUERY_RETRY_DELAY_SECONDS = 0.5
CACHE_NAMESPACE = "region_apt_compare:silver_fallback"

logger = logging.getLogger(__name__)


def _build_where_clause(
    cgg_cd: str, bjd_cd: str, apt_nm: str, mno: str, sno: str
) -> tuple[str, dict[str, str]]:
    """자치구코드+법정동코드+아파트명+지번 본번/부번(모두 필수) 조건을 만든다.
    _fetch_apt_row의 WHERE 절과 동일한 조건이며, base_date 매칭 여부 확인
    (resolve_base_date_for_filter)과 실제 데이터 조회가 이 조건을 공유한다."""
    params: dict[str, str] = {
        "cgg_cd": cgg_cd,
        "bjd_cd": bjd_cd,
        "apt_nm": apt_nm,
        "mno": mno,
        "sno": sno,
    }
    where_clause = (
        "WHERE sgg_cd = $cgg_cd AND dong_cd = $bjd_cd AND apt_name = $apt_nm"
        " AND mno = $mno AND sno = $sno"
    )
    return where_clause, params


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


def _execute_with_retry(con, query: str, params: dict[str, Any]):
    """con.execute()를 최대 SILVER_QUERY_RETRY_ATTEMPTS회까지 재시도한다. fact_apt_transactions는
    운영 중에도 계속 새 데이터가 커밋되는 Iceberg 테이블이라, 조회 도중 메타데이터 포인터(snapshot)가
    바뀌어 일시적인 IO 에러가 나는 경우가 실제로 관측되었다(테이블 버전 회전 중 스냅샷/매니페스트
    파일을 못 찾는 경우). 이런 일시적 에러만 재시도로 흡수하고, 모든 시도가 실패하면 마지막 예외를
    그대로 올린다(호출자가 기존과 동일하게 처리)."""
    last_exc: Exception | None = None
    for attempt in range(SILVER_QUERY_RETRY_ATTEMPTS):
        try:
            return con.execute(query, params)
        except Exception as exc:  # noqa: BLE001 - 스토리지 IO 예외는 duckdb.Error 계열로 다양함
            last_exc = exc
            if attempt < SILVER_QUERY_RETRY_ATTEMPTS - 1:
                logger.warning(
                    "Silver fallback query failed (attempt %d/%d), retrying: %s",
                    attempt + 1,
                    SILVER_QUERY_RETRY_ATTEMPTS,
                    exc,
                )
                time.sleep(SILVER_QUERY_RETRY_DELAY_SECONDS)
    assert last_exc is not None
    raise last_exc


def _fetch_silver_aggregate(
    con, cgg_cd: str, bjd_cd: str, apt_nm: str, mno: str, sno: str
) -> dict[str, Any] | None:
    """골드 마트(dm_apt_recent_trade)에 매칭 row가 없는(=최근 90일 거래 0건) 단지에 대해, 실버
    (fact_apt_transactions, Iceberg) 레이어에서 이 단지의 [마지막 거래일 - 89일 ~ 마지막 거래일]
    구간 데이터를 온디맨드로 스캔해 dm_apt_recent_trade와 동일한 집계식으로 계산한다.

    한 번의 스캔(matched CTE)으로 이 단지의 전체 이력을 먼저 식별자 조건으로 좁힌 뒤, 그 결과
    안에서만 MAX(deal_date)(=Step 1: 기준일 탐색)와 90일 윈도우 슬라이싱(=Step 2)을 수행하므로
    fact_apt_transactions 전체를 여러 번 스캔하지 않는다. 단지 식별자는 파티션 키(deal_date_day)가
    아니므로 Iceberg 파티션 프루닝 대상은 아니지만, 이 단지 하나로 좁혀진 matched 결과 자체는
    소규모라 메모리에 안전하게 올릴 수 있다(대상 스토리지 전체 풀스캔/다운로드가 아니라, 이
    단지 조건에 매칭되는 컬럼만 프로젝션한 결과셋만 유지).

    반환 dict는 _fetch_apt_row()가 반환하는 gold row와 동일한 키(apt_name/household_count/
    build_year/use_approval_date/total_trade_amount/total_price_per_pyeong/total_pyeong/
    latest_trade_pyeong/trade_count)에 anchor_date(이 단지의 마지막 거래일)를 추가로 담아,
    호출자가 그대로 _build_group()에 넘길 수 있게 한다(Step 3: 기존 계산식 재사용).
    household_count/build_year/use_approval_date는 원시 거래 팩트 테이블에는 없는 단지
    메타데이터라 None으로 둔다(스키마상 선택 필드라 DTO를 깨지 않는다).

    이 단지의 거래 이력이 fact_apt_transactions에 아예 없으면(거래 이력 자체가 없는 단지) None을
    반환한다 - 호출자가 기존 관례대로 빈 객체({})를 반환해야 한다."""
    con.execute("INSTALL iceberg;")
    con.execute("LOAD iceberg;")

    path = duckdb_client.silver_base_path(SILVER_TABLE)
    query = f"""
        WITH matched AS (
            SELECT deal_date, price_ten_thousand, exclusive_area_m2
            FROM iceberg_scan($path)
            WHERE sgg_cd = $sgg_cd AND dong_cd = $dong_cd AND apt_name = $apt_name
              AND mno = $mno AND sno = $sno
        ),
        bounds AS (
            SELECT MAX(deal_date) AS last_date FROM matched
        ),
        windowed AS (
            SELECT
                m.deal_date,
                m.price_ten_thousand,
                m.exclusive_area_m2 * {SUPPLY_AREA_FACTOR} / {PYEONG_DIVISOR} AS pyeong
            FROM matched m, bounds b
            WHERE b.last_date IS NOT NULL
              AND m.deal_date BETWEEN b.last_date - INTERVAL {SILVER_WINDOW_DAYS - 1} DAY AND b.last_date
        )
        SELECT
            COUNT(*) AS trade_count,
            MAX(deal_date) AS anchor_date,
            CAST(ROUND(SUM(price_ten_thousand)) AS BIGINT) AS total_trade_amount,
            CAST(ROUND(SUM(price_ten_thousand / pyeong)) AS BIGINT) AS total_price_per_pyeong,
            ROUND(SUM(pyeong), 2) AS total_pyeong,
            CAST(ROUND(arg_max(price_ten_thousand, deal_date)) AS BIGINT) AS latest_trade_amount,
            ROUND(arg_max(pyeong, deal_date), 2) AS latest_trade_pyeong
        FROM windowed
    """
    params: dict[str, Any] = {
        "path": path,
        "sgg_cd": cgg_cd,
        "dong_cd": bjd_cd,
        "apt_name": apt_nm,
        "mno": mno,
        "sno": sno,
    }
    result = _execute_with_retry(con, query, params)
    rows = duckdb_client.rows_to_dicts(result)
    row = rows[0] if rows else None
    if row is None or not row.get("trade_count"):
        return None

    row["apt_name"] = apt_nm
    row["household_count"] = None
    row["build_year"] = None
    row["use_approval_date"] = None
    return row


def _resolve_with_silver_fallback(
    con,
    row: dict[str, Any] | None,
    base_date: str,
    cgg_cd: str,
    bjd_cd: str,
    apt_nm: str,
    mno: str,
    sno: str,
) -> tuple[dict[str, Any] | None, str]:
    """골드 조회 결과(row, base_date)가 "매칭 없음"이거나 "매칭됐지만 최근 90일 거래 0건"이면,
    실버 레이어 Fallback(_fetch_silver_aggregate)으로 대체를 시도한다. 계산 결과는
    settings.silver_fallback_cache_ttl_seconds(기본 1시간) 동안 (cgg_cd, bjd_cd, apt_nm, mno,
    sno) 키로 캐싱되어, 동일 단지 반복 요청 시 스토리지 I/O를 다시 하지 않는다("이 단지는 실버에도
    이력이 없다"는 None 결과도 함께 캐싱한다).

    실버 레이어에도 거래 이력이 전혀 없으면 골드 조회 결과를 그대로 반환한다(호출자가 기존
    관례대로 빈 객체 {}를 반환한다)."""
    trade_count = (row or {}).get("trade_count") or 0
    if row is not None and trade_count > 0:
        return row, base_date

    cache_key = (cgg_cd, bjd_cd, apt_nm, mno, sno)
    silver_row = cached_call(
        CACHE_NAMESPACE,
        cache_key,
        lambda: _fetch_silver_aggregate(con, cgg_cd, bjd_cd, apt_nm, mno, sno),
    )
    if silver_row is None:
        return row, base_date

    anchor_date = silver_row["anchor_date"]
    logger.info(
        "Silver fallback used for table=%s, apt=%s/%s/%s/%s/%s, anchor_date=%s, trade_count=%s",
        MART_TABLE,
        cgg_cd,
        bjd_cd,
        apt_nm,
        mno,
        sno,
        anchor_date,
        silver_row.get("trade_count"),
    )
    return silver_row, str(anchor_date)


def _build_group(row: dict[str, Any] | None, base_date: str) -> dict[str, Any]:
    """row를 응답용 비교 지표로 가공한다. avg_deal_price/avg_pyeong_price/avg_pyeong은 각각
    total_trade_amount/total_price_per_pyeong/total_pyeong을 trade_count로 나눠 반올림한 정수다.
    latest_trade_pyeong도 원본 값을 반올림한 정수로 전달한다. 매칭되는 row가 없거나(단지 자체를 못 찾음)
    trade_count가 0이면(최근 90일간 거래 없음) 빈 딕셔너리({})를 반환한다(이 경우 base_date도
    포함하지 않는다)."""
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
        "base_date": base_date,
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
    조회는 서로 독립적이라 한쪽이 매칭되지 않아도(또는 최근 90일간 거래가 없어도) 나머지 한쪽은 정상적으로
    반환된다. base_date 또한 단지1/단지2가 서로 독립적으로 폴백 탐색하므로(한쪽만 최신 파티션에 거래가
    없으면 그 단지만 과거로 소급), 두 단지가 서로 다른 base_date를 가질 수 있다(정상 동작).

    골드 마트에 매칭 row가 없거나 있어도 trade_count == 0이면(최근 90일 거래 0건), 각 단지별로
    독립적으로 실버(fact_apt_transactions) 레이어 Fallback을 시도한다(_resolve_with_silver_fallback).
    이 단지의 마지막 거래일 기준 과거 90일 구간을 온디맨드로 집계해 동일한 계산식(_build_group)으로
    가공하며, 그 결과는 최소 1시간 캐싱된다. 실버 레이어에도 거래 이력이 전혀 없어야만 비로소 빈
    딕셔너리({})가 반환된다."""
    con = duckdb_client.get_connection()
    try:
        where_1, params_1 = _build_where_clause(cgg_cd_1, bjd_cd_1, apt_nm_1, mno_1, sno_1)
        where_2, params_2 = _build_where_clause(cgg_cd_2, bjd_cd_2, apt_nm_2, mno_2, sno_2)
        base_date_1 = duckdb_client.resolve_base_date_for_filter(
            con, MART_TABLE, where_1, params_1
        ) or duckdb_client.resolve_base_date(con, MART_TABLE)
        base_date_2 = duckdb_client.resolve_base_date_for_filter(
            con, MART_TABLE, where_2, params_2
        ) or duckdb_client.resolve_base_date(con, MART_TABLE)
        row_1 = _fetch_apt_row(con, base_date_1, cgg_cd_1, bjd_cd_1, apt_nm_1, mno_1, sno_1)
        row_2 = _fetch_apt_row(con, base_date_2, cgg_cd_2, bjd_cd_2, apt_nm_2, mno_2, sno_2)
        row_1, base_date_1 = _resolve_with_silver_fallback(
            con, row_1, base_date_1, cgg_cd_1, bjd_cd_1, apt_nm_1, mno_1, sno_1
        )
        row_2, base_date_2 = _resolve_with_silver_fallback(
            con, row_2, base_date_2, cgg_cd_2, bjd_cd_2, apt_nm_2, mno_2, sno_2
        )
    finally:
        con.close()

    return _build_group(row_1, base_date_1), _build_group(row_2, base_date_2)
