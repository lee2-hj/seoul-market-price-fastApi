import logging
from datetime import date, timedelta
from typing import Any

from app.core import duckdb_client
from app.core.config import settings

# RTT 마트(rtt_service.py와 동일 소스)를 재사용한다. RTT는 개별 거래 단위(1건=1행)로 apt_name/
# floor/exclusive_area_m2/pyeong/trade_amount를 그대로 갖고 있어, 이 API가 요구하는 5개 필드를
# 추가 조인/계산 없이 직접 제공한다(dm_main은 구+동+단지+거래일+면적 단위로 이미 합산돼 있어
# floor 컬럼 자체가 없다 — docs/specs/backend-apt-recent-trade-rank-spec.md 2절, 사용자 확인 완료).
MART_TABLE = "RTT"
PERIOD_DAYS = 90
TOP_BOTTOM_LIMIT = 5

logger = logging.getLogger(__name__)


def _period_range(today: date) -> tuple[date, date]:
    """오늘을 기준(anchor)으로 최근 90일(오늘 포함) 구간의 시작일/종료일을 반환한다. 이 나이브 구간에
    조건에 맞는 거래가 없으면 get_apt_recent_rank()가 anchor를 과거로 이동시킬 수 있으므로, 최종
    응답의 period_start/period_end가 항상 이 함수의 반환값(오늘 기준)과 같다고 가정하면 안 된다."""
    end_date = today
    start_date = end_date - timedelta(days=PERIOD_DAYS - 1)
    return start_date, end_date


def _fetch_rows(con, sgg_cd: str, dong_cd: str, start_date: date, end_date: date) -> list[dict[str, Any]]:
    """RTT 마트(일자별 base_date 파티션)에서 sgg_cd+dong_cd(둘 다 필수) 조건에 맞는 최근 90일 개별
    실거래 row를 조회한다. rtt_service.py의 _fetch_rows와 동일한 글롭/파티션 패턴이지만, 이 API는
    "법정동 내"로 범위가 고정돼 dong_cd가 항상 필수라 조건부 분기 없이 고정 WHERE로 구성한다."""
    parquet_glob = f"{duckdb_client.mart_base_path(MART_TABLE)}/base_date=*/data.parquet"
    params: dict[str, Any] = {
        "sgg_cd": sgg_cd,
        "dong_cd": dong_cd,
        "start_date": start_date,
        "end_date": end_date,
    }
    query = f"""
        SELECT *
        FROM read_parquet('{parquet_glob}', hive_partitioning = true)
        WHERE sgg_cd = $sgg_cd AND dong_cd = $dong_cd AND base_date BETWEEN $start_date AND $end_date
    """
    result = con.execute(query, params)
    return duckdb_client.rows_to_dicts(result)


def _build_rank_item(row: dict[str, Any]) -> dict[str, Any]:
    """RTT row에서 응답에 필요한 5개 필드를 추출한다. exclusive_area_m2/trade_amount는 원본 값 그대로
    통과시키고(재계산 없음), pyeong만 반올림해 소수점을 제거한 정수로 내려준다."""
    return {
        "apt_name": row["apt_name"],
        "exclusive_area_m2": row["exclusive_area_m2"],
        "pyeong": round(row["pyeong"]),
        "floor": row["floor"],
        "trade_amount": row["trade_amount"],
    }


def get_apt_recent_rank(*, sgg_cd: str, dong_cd: str) -> dict[str, Any]:
    """기본적으로 오늘 기준 최근 90일간 sgg_cd+dong_cd(법정동, 둘 다 필수) 조건의 RTT 개별 실거래
    데이터를 trade_amount 기준으로 정렬해 상위 5건(top)/하위 5건(bottom)을 반환한다.

    이 90일 창(오늘 기준)에 조건에 맞는 거래가 하나도 없으면(예: 최근에 거래가 뜸한 법정동), 날짜
    범위 제한 없이 전체 이력에서 조건에 매칭되는 가장 최근 base_date를 한 번에 찾아
    (`resolve_recent_match_date`), 그 날짜를 새 end_date로 삼아 90일 창 전체를 그 시점으로
    이동시켜 재조회한다("파티션 폴백"이 아니라 "조회 창의 기준일(anchor) 이동" - rtt_service.py의
    동일 로직을 그대로 재사용). 이동된 시작일이 원래 창의 시작일보다 settings.max_base_date_lookback일
    이상 더 과거이거나, 애초에 그 조건의 거래가 이력 전체에 없으면 창을 이동하지 않고 기존처럼 빈
    결과를 그대로 반환한다(에러 아님).

    매칭 행이 5건 이하면 bottom은 빈 리스트로 반환한다(top과 완전히 겹치는 것을 방지 -
    apt_price_service.get_top_bottom과 동일한 원칙)."""
    start_date, end_date = _period_range(date.today())
    con = duckdb_client.get_connection()
    try:
        rows = _fetch_rows(con, sgg_cd, dong_cd, start_date, end_date)

        if not rows:
            naive_start, naive_end = start_date, end_date
            match_where = "WHERE sgg_cd = $sgg_cd AND dong_cd = $dong_cd"
            match_params: dict[str, Any] = {"sgg_cd": sgg_cd, "dong_cd": dong_cd}
            full_glob = f"{duckdb_client.mart_base_path(MART_TABLE)}/base_date=*/data.parquet"
            matched_date = duckdb_client.resolve_recent_match_date(
                con, full_glob, "base_date", match_where, match_params
            )
            if matched_date is not None and matched_date >= start_date - timedelta(
                days=settings.max_base_date_lookback
            ):
                end_date = matched_date
                start_date = end_date - timedelta(days=PERIOD_DAYS - 1)
                rows = _fetch_rows(con, sgg_cd, dong_cd, start_date, end_date)
                logger.info(
                    "Anchor fallback used for sgg_cd=%s, dong_cd=%s: end_date moved to %s "
                    "(naive_window=%s~%s, matched_window=%s~%s)",
                    sgg_cd,
                    dong_cd,
                    end_date,
                    naive_start,
                    naive_end,
                    start_date,
                    end_date,
                )
            # matched_date가 없거나 lookback 상한을 넘으면 rows/기간은 나이브 값 그대로 —
            # 기존과 동일하게 빈 결과 반환(에러 아님).
    finally:
        con.close()

    rows_sorted_desc = sorted(rows, key=lambda r: r["trade_amount"], reverse=True)
    top = [_build_rank_item(r) for r in rows_sorted_desc[:TOP_BOTTOM_LIMIT]]
    bottom = (
        [_build_rank_item(r) for r in sorted(rows, key=lambda r: r["trade_amount"])[:TOP_BOTTOM_LIMIT]]
        if len(rows) > TOP_BOTTOM_LIMIT
        else []
    )
    sgg_nm = rows[0]["sgg_nm"] if rows else None
    dong_nm = rows[0]["dong_nm"] if rows else None

    return {
        "sgg_cd": sgg_cd,
        "sgg_nm": sgg_nm,
        "dong_cd": dong_cd,
        "dong_nm": dong_nm,
        "period_start": start_date,
        "period_end": end_date,
        "top": top,
        "bottom": bottom,
    }
