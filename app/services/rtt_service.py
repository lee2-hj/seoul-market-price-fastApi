import logging
from collections import OrderedDict
from datetime import date, timedelta
from typing import Any

from app.core import duckdb_client
from app.core.config import settings

MART_TABLE = "RTT"
PERIOD_DAYS = 90
HALF_PERIOD_DAYS = PERIOD_DAYS // 2
BIWEEKLY_BUCKET_COUNT = 6
RECENT_TRADES_LIMIT = 20
TOP_VOLUME_LIMIT = 5

logger = logging.getLogger(__name__)


def _period_range(today: date) -> tuple[date, date]:
    """오늘을 기준(anchor)으로 최근 90일(오늘 포함) 구간의 시작일/종료일을 반환한다. 이 나이브 구간에
    조건에 맞는 거래가 없으면 get_rtt_summary()가 anchor를 과거로 이동시킬 수 있으므로, 최종 응답의
    period_start/period_end가 항상 이 함수의 반환값(오늘 기준)과 같다고 가정하면 안 된다."""
    end_date = today
    start_date = end_date - timedelta(days=PERIOD_DAYS - 1)
    return start_date, end_date


def _fetch_rows(
    con, sgg_cd: str, dong_cd: str | None, start_date: date, end_date: date
) -> list[dict[str, Any]]:
    """RTT 마트(일자별 base_date 파티션)에서 sgg_cd(+dong_cd, 선택) 조건에 맞는 최근 90일 실거래 row를 조회한다.
    dong_cd가 없으면 자치구(sgg_cd) 내 모든 법정동의 거래내역을 그대로 가져온다."""
    parquet_glob = f"{duckdb_client.mart_base_path(MART_TABLE)}/base_date=*/data.parquet"
    params: dict[str, Any] = {
        "sgg_cd": sgg_cd,
        "start_date": start_date,
        "end_date": end_date,
    }
    where_clause = "WHERE sgg_cd = $sgg_cd AND base_date BETWEEN $start_date AND $end_date"
    if dong_cd:
        where_clause += " AND dong_cd = $dong_cd"
        params["dong_cd"] = dong_cd

    query = f"""
        SELECT *
        FROM read_parquet('{parquet_glob}', hive_partitioning = true)
        {where_clause}
    """
    result = con.execute(query, params)
    return duckdb_client.rows_to_dicts(result)


def _pyeong_grp(pyeong: float) -> str:
    """평형을 10평 단위 그룹으로 분류한다. 반올림 전 원본값을 그대로 버림(floor) 계산하면 19.5~19.99처럼
    반올림 시 다음 그룹으로 넘어가는 값이 한 단계 낮은 그룹으로 잘못 분류되므로, 반올림한 값을 기준으로
    그룹을 나눈다(예: 19.77평은 반올림하면 20평이므로 '20' 그룹). 10평 미만은 '10' 그룹에 포함하고, 그
    이상은 실제 데이터 범위에 맞춰 50/60/70... 등 상한 없이 동적으로 분류한다."""
    bucket = (round(pyeong) // 10) * 10
    return str(bucket) if bucket >= 10 else "10"


def _build_totals(rows: list[dict[str, Any]]) -> tuple[int, int, int, int]:
    """전체 거래건수/총 거래금액/평균 거래가/최고 거래가를 집계한다."""
    total_deal_cnt = sum(r["trade_count"] for r in rows)
    total_trade_amount = sum(r["trade_amount"] for r in rows)
    avg_trade_amount = round(total_trade_amount / total_deal_cnt) if total_deal_cnt else 0
    max_trade_amount = round(max((r["trade_amount"] for r in rows), default=0))
    return total_deal_cnt, round(total_trade_amount), avg_trade_amount, max_trade_amount


def _build_volume_change_rate(
    rows: list[dict[str, Any]], start_date: date, end_date: date
) -> float | None:
    """90일 구간을 이전 45일/최근 45일로 절반씩 나눠 거래량 증감률(%)을 계산한다."""
    prior_half_end = (start_date + timedelta(days=HALF_PERIOD_DAYS - 1)).isoformat()
    recent_half_start = (start_date + timedelta(days=HALF_PERIOD_DAYS)).isoformat()

    prior_cnt = sum(r["trade_count"] for r in rows if r["deal_date"] <= prior_half_end)
    recent_cnt = sum(r["trade_count"] for r in rows if r["deal_date"] >= recent_half_start)

    if prior_cnt == 0:
        return None
    return round((recent_cnt - prior_cnt) / prior_cnt * 100, 2)


def _generate_biweekly_buckets(start_date: date, end_date: date) -> list[tuple[date, date]]:
    """조회 구간(90일)을 BIWEEKLY_BUCKET_COUNT(6)개 구간으로 균등 분할해 (구간 시작일, 구간 종료일) 목록을
    만든다. 전체 일수가 6으로 나누어떨어지지 않으면 나머지 일수를 구간별로 최대한 고르게 배분한다."""
    total_days = (end_date - start_date).days + 1
    buckets: list[tuple[date, date]] = []
    for i in range(BIWEEKLY_BUCKET_COUNT):
        bucket_start = start_date + timedelta(days=round(i * total_days / BIWEEKLY_BUCKET_COUNT))
        bucket_end = start_date + timedelta(
            days=round((i + 1) * total_days / BIWEEKLY_BUCKET_COUNT) - 1
        )
        buckets.append((bucket_start, bucket_end))
    return buckets


def _build_biweekly_trend(
    rows: list[dict[str, Any]], buckets: list[tuple[date, date]]
) -> list[dict[str, Any]]:
    """90일 조회 구간을 6등분한 구간별로 거래량/평균 거래가를 집계한다."""
    trend: list[dict[str, Any]] = []
    for bucket_start, bucket_end in buckets:
        start_str, end_str = bucket_start.isoformat(), bucket_end.isoformat()
        bucket_rows = [r for r in rows if start_str <= r["deal_date"] <= end_str]
        deal_cnt = sum(r["trade_count"] for r in bucket_rows)
        total_amt = sum(r["trade_amount"] for r in bucket_rows)
        avg_amt = round(total_amt / deal_cnt) if deal_cnt else 0
        trend.append(
            {
                "period_label": f"{bucket_start.isoformat()}/{bucket_end.isoformat()}",
                "start_date": bucket_start,
                "end_date": bucket_end,
                "deal_cnt": deal_cnt,
                "avg_trade_amount": avg_amt,
            }
        )
    return trend


def _build_pyeong_distribution(rows: list[dict[str, Any]], total_deal_cnt: int) -> list[dict[str, Any]]:
    """평형 그룹(10평 단위, 상한 없이 실제 데이터 기준으로 동적 분류)별 거래건수와 전체 대비 비중(%)을 집계한다.
    거래가 없는(비중 0%) 그룹은 결과에 포함하지 않는다."""
    counts: dict[str, int] = {}
    for row in rows:
        grp = _pyeong_grp(row["pyeong"])
        counts[grp] = counts.get(grp, 0) + row["trade_count"]

    distribution: list[dict[str, Any]] = []
    for grp in sorted(counts, key=int):
        deal_cnt = counts[grp]
        if deal_cnt <= 0:
            continue
        ratio = round(deal_cnt / total_deal_cnt * 100, 2) if total_deal_cnt else 0.0
        distribution.append({"pyeong_grp": grp, "deal_cnt": deal_cnt, "ratio": ratio})
    return distribution


def _build_recent_trades(rows: list[dict[str, Any]], include_location: bool) -> list[dict[str, Any]]:
    """거래일 최신순으로 최근 실거래 데이터를 RECENT_TRADES_LIMIT건까지 반환한다. include_location=True면
    (dong_cd 미지정으로 여러 법정동 데이터가 섞이는 경우) 각 항목에 자치구명/법정동명을 함께 내려준다."""
    ordered = sorted(rows, key=lambda r: r["deal_date"], reverse=True)
    return [
        {
            "apt_name": r["apt_name"],
            "mno": r["mno"],
            "sno": r["sno"],
            "deal_date": r["deal_date"],
            "floor": r["floor"],
            "trade_amount": r["trade_amount"],
            "pyeong": r["pyeong"],
            "exclusive_area_m2": r["exclusive_area_m2"],
            "sgg_nm": r["sgg_nm"] if include_location else None,
            "dong_nm": r["dong_nm"] if include_location else None,
        }
        for r in ordered[:RECENT_TRADES_LIMIT]
    ]


def _build_top5_by_volume(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """단지(아파트명+지번 본번/부번) 기준으로 그룹화하여 거래건수 상위 TOP_VOLUME_LIMIT개를 집계한다."""
    groups: "OrderedDict[tuple[str, str, str], dict[str, Any]]" = OrderedDict()
    for row in rows:
        key = (row["apt_name"], row["mno"], row["sno"])
        group = groups.get(key)
        if group is None:
            group = {
                "apt_name": row["apt_name"],
                "mno": row["mno"],
                "sno": row["sno"],
                "_cnt": 0,
                "_amt": 0,
            }
            groups[key] = group
        group["_cnt"] += row["trade_count"]
        group["_amt"] += row["trade_amount"]

    ranked = sorted(groups.values(), key=lambda g: g["_cnt"], reverse=True)[:TOP_VOLUME_LIMIT]
    return [
        {
            "apt_name": g["apt_name"],
            "mno": g["mno"],
            "sno": g["sno"],
            "deal_cnt": g["_cnt"],
            "avg_trade_amount": round(g["_amt"] / g["_cnt"]) if g["_cnt"] else 0,
        }
        for g in ranked
    ]


def get_rtt_summary(*, sgg_cd: str, dong_cd: str | None = None) -> dict[str, Any]:
    """기본적으로 오늘 기준 최근 90일간 sgg_cd(+dong_cd, 선택) 조건의 RTT(실거래) 데이터를 집계하여 단일
    JSON으로 반환한다. dong_cd가 없으면 자치구 내 모든 법정동의 거래내역을 대상으로 동일한 로직을 그대로
    적용해 합산한다.

    이 90일 창(오늘 기준)에 조건에 맞는 거래가 하나도 없으면(예: 최근에 거래가 뜸한 지역), 파티션을 하나씩
    확인하는 대신 날짜 범위 제한 없이 전체 이력에서 조건에 매칭되는 가장 최근 base_date를 한 번에 찾아
    (`resolve_recent_match_date`), 그 날짜를 새 end_date로 삼아 90일 창 전체를 그 시점으로 이동시켜
    재조회한다("파티션 폴백"이 아니라 "조회 창의 기준일(anchor) 이동"). 이동된 시작일이 원래 창의
    시작일보다 settings.max_base_date_lookback일 이상 더 과거이거나, 애초에 그 조건의 거래가 이력 전체에
    없으면 창을 이동하지 않고 기존처럼 빈 결과를 그대로 반환한다(에러 아님). 창이 실제로 이동된 경우
    period_start/period_end는 "오늘 기준 90일"이 아니라 이동된 실제 구간을 반영한다."""
    start_date, end_date = _period_range(date.today())
    con = duckdb_client.get_connection()
    try:
        rows = _fetch_rows(con, sgg_cd, dong_cd, start_date, end_date)

        if not rows:
            naive_start, naive_end = start_date, end_date
            match_where = "WHERE sgg_cd = $sgg_cd" + (" AND dong_cd = $dong_cd" if dong_cd else "")
            match_params: dict[str, Any] = {"sgg_cd": sgg_cd, **({"dong_cd": dong_cd} if dong_cd else {})}
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
                    "Anchor fallback used for table=%s, condition_summary=%s, "
                    "naive_window=%s~%s, matched_window=%s~%s",
                    MART_TABLE,
                    match_where[:100],
                    naive_start,
                    naive_end,
                    start_date,
                    end_date,
                )
            # matched_date가 없거나 lookback 상한을 넘으면 rows/기간은 나이브 값 그대로 —
            # 기존과 동일하게 빈 결과 반환(에러 아님).
    finally:
        con.close()

    buckets = _generate_biweekly_buckets(start_date, end_date)
    total_deal_cnt, total_trade_amount, avg_trade_amount, max_trade_amount = _build_totals(rows)
    sgg_nm = rows[0]["sgg_nm"] if rows else None
    dong_nm = rows[0]["dong_nm"] if (dong_cd and rows) else None

    return {
        "sgg_cd": sgg_cd,
        "sgg_nm": sgg_nm,
        "dong_cd": dong_cd,
        "dong_nm": dong_nm,
        "period_start": start_date,
        "period_end": end_date,
        "total_deal_cnt": total_deal_cnt,
        "total_trade_amount": total_trade_amount,
        "avg_trade_amount": avg_trade_amount,
        "max_trade_amount": max_trade_amount,
        "volume_change_rate": _build_volume_change_rate(rows, start_date, end_date),
        "biweekly_trend": _build_biweekly_trend(rows, buckets),
        "pyeong_distribution": _build_pyeong_distribution(rows, total_deal_cnt),
        "recent_trades": _build_recent_trades(rows, include_location=not dong_cd),
        "top5_by_volume": _build_top5_by_volume(rows),
    }
