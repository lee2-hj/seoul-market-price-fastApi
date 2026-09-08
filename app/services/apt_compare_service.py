import logging
import time
from typing import Any

from app.core import duckdb_client

# fetch_recent_supply_pyeong()은 MinIO/GCS 스토리지에 의존하는데, 실측으로 일시적인 IO 에러
# (예: "Could not connect to server error for HTTP GET to ...")가 관측되었다. 이 함수는 부가
# 정보(query_type='floor' 조회 시 recent_supply_pyeong 보완)만 조회하므로, 일시적 오류만
# 재시도로 흡수한다(모든 시도가 실패하면 호출부가 감지해 None으로 대체할 수 있도록 마지막
# 예외를 그대로 올린다).
GOLD_QUERY_RETRY_ATTEMPTS = 3
GOLD_QUERY_RETRY_DELAY_SECONDS = 0.5

MART_TABLE_BY_QUERY_TYPE: dict[str, str] = {
    "pyeong": "dm_apt_pyeong_price",
    "floor": "dm_apt_flr_price",
}

GRP_COLUMN_BY_QUERY_TYPE: dict[str, str] = {
    "pyeong": "pyeong_grp",
    "floor": "flr_grp",
}

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


def _fetch_gold_items_with_retry(
    mart_table: str, where_clause: str, params: dict[str, Any]
) -> tuple[str, list[dict[str, Any]], Any]:
    """골드 마트에서 base_date 소급 탐색 + 실제 row 조회까지 전체를 스토리지 일시적 IO 오류에
    대비해 최대 GOLD_QUERY_RETRY_ATTEMPTS회까지 재시도한다(매 시도마다 새 커넥션 사용 - 실패한
    커넥션이 불완전한 상태로 남아있을 수 있어서). 성공하면 (base_date, items, con)을 반환하며,
    반환된 con은 호출자가 반드시 닫아야 한다."""
    last_exc: Exception | None = None
    for attempt in range(GOLD_QUERY_RETRY_ATTEMPTS):
        con = duckdb_client.get_connection()
        try:
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
            return base_date, items, con
        except Exception as exc:  # noqa: BLE001 - 스토리지 IO 예외는 duckdb.Error 계열로 다양함
            last_exc = exc
            con.close()
            if attempt < GOLD_QUERY_RETRY_ATTEMPTS - 1:
                logger.warning(
                    "compare_apartments gold fetch failed (attempt %d/%d), retrying: %s",
                    attempt + 1,
                    GOLD_QUERY_RETRY_ATTEMPTS,
                    exc,
                )
                time.sleep(GOLD_QUERY_RETRY_DELAY_SECONDS)

    assert last_exc is not None
    raise last_exc


def compare_apartments(
    *, cgg_cd: str, stdg_cd: str, bldg_nm: str | None, mno: str, sno: str, query_type: str, grp: str | None
) -> tuple[str, list[dict[str, Any]]]:
    """query_type(평단가/층별가)에 해당하는 마트에서 자치구코드(cgg_cd) + 법정동코드(stdg_cd) +
    지번 본번(mno) + 지번 부번(sno) + 건물명(bldg_nm, 선택, 부분일치 LIKE) + 그룹(grp, 선택,
    pyeong_grp 또는 flr_grp 컬럼)이 일치하는 row를 가공 없이 그대로 조회한다. base_date는
    이 조건에 매칭되는 데이터가 있는 가장 최근 파티션까지 소급 탐색한다.

    골드 마트 전체 파티션에서도 이 단지+그룹에 매칭되는 row가 없으면 빈 리스트를 그대로
    반환한다(과거에는 실버(fact_apt_transactions) 레이어까지 온디맨드로 내려가 대체값을
    집계했으나, 항상 최신 base_date 데이터만 사용하도록 이 실버 폴백은 제거되었다)."""
    mart_table = MART_TABLE_BY_QUERY_TYPE[query_type]
    grp_column = GRP_COLUMN_BY_QUERY_TYPE[query_type]

    resolved_grp = grp
    if grp and query_type == "pyeong" and grp == "40":
        # 마트의 pyeong_grp 컬럼은 최상위 구간을 "40+"로 저장하므로, 입력값 "40"을 "40+"로 변환해 조회한다.
        resolved_grp = "40+"

    where_clause, params = _build_where_clause(
        cgg_cd, stdg_cd, mno, sno, bldg_nm, grp_column, resolved_grp
    )
    base_date, items, con = _fetch_gold_items_with_retry(mart_table, where_clause, params)
    con.close()
    return base_date, items


def fetch_recent_supply_pyeong(
    *, cgg_cd: str, stdg_cd: str, bldg_nm: str | None, mno: str, sno: str
) -> float | None:
    """dm_apt_pyeong_price 마트에는 있지만 dm_apt_flr_price 마트에는 없는 recent_supply_pyeong을 보완하기 위해,
    자치구코드+법정동코드+지번 본번(mno)+지번 부번(sno)(+건물명, 선택)이 일치하는 row 중 recent_deal_date가 가장
    최근인 row의 recent_supply_pyeong 값을 조회한다. query_type='floor' 조회 시 사용.

    스토리지(MinIO/GCS) 일시적 IO 오류를 흡수하기 위해 base_date 탐색부터 실제 조회까지
    전체를 최대 GOLD_QUERY_RETRY_ATTEMPTS회까지 재시도한다(매 시도마다 새 커넥션을 사용한다 -
    실패한 커넥션이 불완전한 상태로 남아있을 수 있어서). 모든 시도가 실패하면 마지막 예외를
    그대로 올린다 - 이 함수는 부가 정보(recent_supply_pyeong)만 제공하므로, 호출부(엔드포인트)가
    이 예외를 잡아 None으로 대체해 전체 응답이 실패하지 않도록 처리한다."""
    mart_table = MART_TABLE_BY_QUERY_TYPE["pyeong"]
    where_clause, params = _build_where_clause(cgg_cd, stdg_cd, mno, sno, bldg_nm, None, None)

    last_exc: Exception | None = None
    for attempt in range(GOLD_QUERY_RETRY_ATTEMPTS):
        con = duckdb_client.get_connection()
        try:
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
            return row[0] if row else None
        except Exception as exc:  # noqa: BLE001 - 스토리지 IO 예외는 duckdb.Error 계열로 다양함
            last_exc = exc
            if attempt < GOLD_QUERY_RETRY_ATTEMPTS - 1:
                logger.warning(
                    "fetch_recent_supply_pyeong failed (attempt %d/%d), retrying: %s",
                    attempt + 1,
                    GOLD_QUERY_RETRY_ATTEMPTS,
                    exc,
                )
                time.sleep(GOLD_QUERY_RETRY_DELAY_SECONDS)
        finally:
            con.close()

    assert last_exc is not None
    raise last_exc
