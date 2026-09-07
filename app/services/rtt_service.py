import logging
from collections import OrderedDict
from datetime import date, timedelta
from typing import Any

from app.core import duckdb_client
from app.core.cache import cached_call
from app.core.config import settings

MART_TABLE = "RTT"
PERIOD_DAYS = 90
HALF_PERIOD_DAYS = PERIOD_DAYS // 2
BIWEEKLY_BUCKET_COUNT = 6
RECENT_TRADES_LIMIT = 20
TOP_VOLUME_LIMIT = 5

# --- 실버(Iceberg fact) 레이어 Fallback -------------------------------------------------
# RTT 마트 자체가 실측 확인 결과 fact_apt_transactions의 1:1 행 단위 프로젝션이다(trade_count
# 컬럼은 모든 row에서 항상 1이고, trade_amount/pyeong/exclusive_area_m2가 원본 price_ten_thousand/
# exclusive_area_m2*PYEONG_DIVISOR와 정확히 일치 - 그룹 합산이 전혀 없다). 다만 RTT도 apt_mkt_trends와
# 마찬가지로 최근 ~103일(실측: 2026-05-24~2026-09-04)만 보존하는 롤링 마트라, 그 지역(sgg_cd,
# +dong_cd)의 마지막 실거래가 그보다 오래되면(예: 신당동 등 거래가 뜸한 법정동) resolve_recent_match_date로도
# 영원히 못 찾는다. 이 경우 fact_apt_transactions 원본까지 온디맨드로 내려가 [그 지역의 마지막 거래일 -
# 89일 ~ 마지막 거래일] 구간을 그대로 가져온다. RTT가 원본의 단순 재구성이므로, 실버 row를 RTT와
# 완전히 동일한 컬럼 구조로 매핑하면 기존 집계 함수(_build_totals 등)를 한 글자도 바꾸지 않고 재사용할
# 수 있다.
SILVER_TABLE = settings.silver_apt_transactions_table
PYEONG_DIVISOR = 3.305785
CACHE_NAMESPACE = "rtt:anchor_fallback"

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


def _build_avg_pyeong_amount(rows: list[dict[str, Any]], total_deal_cnt: int) -> int:
    """평균 평단가(만원/평) = 각 row의 평단가(trade_amount / pyeong) 합계를 total_deal_cnt로
    나눠 반올림한다(다른 dm_ 마트들의 avg_pyeong_amt/avg_pyeong_price와 동일한 계산 관례 -
    "전체 매매가 합계 / 전체 평 합계"가 아니라 "건별 평단가의 평균"이다)."""
    if not total_deal_cnt:
        return 0
    total_pyeong_amount = sum(r["trade_amount"] / r["pyeong"] for r in rows if r["pyeong"])
    return round(total_pyeong_amount / total_deal_cnt)


def _build_volume_change_rate(
    biweekly_trend: list[dict[str, Any]], data_end: date | None
) -> float | None:
    """biweekly_trend(응답에 그대로 노출되는 6구간 거래량 추이, "그래프"와 동일한 데이터)의
    첫 3구간(이전 45일) 평균 거래량 대비 마지막 3구간(최근 45일) 평균 거래량 증감률(%)을
    계산한다 - 그래프에 보이는 것과 항상 같은 숫자에서 파생되도록, 별도로 원본 rows를 다시
    필터링하지 않고 이미 계산된 biweekly_trend를 그대로 사용한다.

    RTT 마트는 지역에 따라 적재가 며칠~몇 주씩 지연될 수 있다(실측 확인: sgg_cd=11680은
    "오늘" 기준 실제 마지막 거래일이 여러 날~한 달 가까이 이전). 이 때문에 마지막 구간(들)의
    종료일이 실제 데이터가 존재하는 마지막 날짜(data_end)보다 미래이면, 그 구간은 아직 실거래
    신고/적재가 다 끝나지 않은 "불완전한" 구간이다. 이런 구간을 그대로 포함해 평균에 반영하면
    (그래프에서도 눈에 띄게 낮게 찍히는) 미완성 구간 때문에 감소폭이 실제보다 과장된다 -
    부분적으로 비중을 줄여 반영하는 대신, 완전히 채워지지 않은 구간은 비교에서 통째로
    제외한다(그래프를 보는 사람이 "이 구간은 아직 안 찼다"고 눈으로 판단할 만한 수준이면
    통계에서도 빼는 것이 더 정확하다).

    이전 3구간(항상 완결된 과거) 또는 완전한 최근 구간이 하나도 남지 않으면 None을 반환한다.
    data_end를 알 수 없으면(rows 자체가 없음) 모든 구간을 완전한 것으로 취급한다(기존 동작과
    동일 - 이 경우 마트 적재 지연 여부를 판단할 수 없기 때문)."""
    half = BIWEEKLY_BUCKET_COUNT // 2
    prior_buckets = biweekly_trend[:half]
    recent_buckets = biweekly_trend[half:]

    if data_end is not None:
        recent_buckets = [b for b in recent_buckets if b["end_date"] <= data_end]

    if not prior_buckets or not recent_buckets:
        return None

    prior_avg = sum(b["deal_cnt"] for b in prior_buckets) / len(prior_buckets)
    if prior_avg == 0:
        return None

    recent_avg = sum(b["deal_cnt"] for b in recent_buckets) / len(recent_buckets)
    return round((recent_avg - prior_avg) / prior_avg * 100, 2)


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


def _fetch_silver_rows(con, sgg_cd: str, dong_cd: str | None) -> list[dict[str, Any]] | None:
    """RTT 마트 자체의 앵커 폴백도 매칭 데이터를 찾지 못했을 때(=이 마트의 ~103일 보존 기간 자체를
    벗어난 지역, 모듈 상단 주석 참고) 마지막 수단으로 실버(fact_apt_transactions, Iceberg) 원본
    팩트 테이블에서 이 지역(sgg_cd, +dong_cd)의 [마지막 거래일 - 89일 ~ 마지막 거래일] 구간을
    온디맨드로 스캔한다.

    RTT는 fact_apt_transactions의 1:1 재구성이므로(trade_count 항상 1, 그룹 합산 없음), 취소된
    거래(cancel_date 존재)만 제외하고 원본 컬럼을 그대로 RTT와 동일한 키(sgg_cd/sgg_nm/dong_cd/
    dong_nm/apt_name/mno/sno/deal_date/floor/trade_amount/pyeong/exclusive_area_m2/trade_count)로
    매핑해 반환한다. sgg_nm/dong_nm은 fact_apt_transactions에 없어 dim_apartment에서 보완한다
    (dong_cd 미지정 시 자치구 내 여러 법정동이 섞일 수 있어 법정동코드별로 이름을 매핑한다).

    이 지역에 거래 이력이 fact_apt_transactions에도 전혀 없으면 None을 반환한다."""
    con.execute("INSTALL iceberg;")
    con.execute("LOAD iceberg;")

    conditions = ["sgg_cd = $sgg_cd", "(cancel_date IS NULL OR cancel_date = '')"]
    params: dict[str, Any] = {"sgg_cd": sgg_cd}
    if dong_cd:
        conditions.append("dong_cd = $dong_cd")
        params["dong_cd"] = dong_cd
    params["path"] = duckdb_client.silver_base_path(SILVER_TABLE)

    query = f"""
        WITH matched AS (
            SELECT deal_date, dong_cd, apt_name, mno, sno, floor, price_ten_thousand, exclusive_area_m2
            FROM iceberg_scan($path)
            WHERE {" AND ".join(conditions)}
        ),
        bounds AS (
            SELECT MAX(deal_date) AS last_date FROM matched
        )
        SELECT
            m.dong_cd, m.apt_name, m.mno, m.sno, m.deal_date, m.floor,
            CAST(ROUND(m.price_ten_thousand) AS BIGINT) AS trade_amount,
            ROUND(m.exclusive_area_m2 / {PYEONG_DIVISOR}, 2) AS pyeong,
            m.exclusive_area_m2,
            1 AS trade_count
        FROM matched m, bounds b
        WHERE b.last_date IS NOT NULL
          AND m.deal_date BETWEEN b.last_date - INTERVAL {PERIOD_DAYS - 1} DAY AND b.last_date
    """
    rows = duckdb_client.rows_to_dicts(con.execute(query, params))
    if not rows:
        return None

    name_query = """
        SELECT dong_cd, ANY_VALUE(sgg_nm) AS sgg_nm, ANY_VALUE(dong_nm) AS dong_nm
        FROM iceberg_scan($path)
        WHERE sgg_cd = $sgg_cd
        GROUP BY dong_cd
    """
    name_rows = duckdb_client.rows_to_dicts(
        con.execute(
            name_query,
            {"path": duckdb_client.silver_base_path("dim_apartment"), "sgg_cd": sgg_cd},
        )
    )
    names_by_dong = {r["dong_cd"]: r for r in name_rows}

    for row in rows:
        row["sgg_cd"] = sgg_cd
        names = names_by_dong.get(row["dong_cd"], {})
        row["sgg_nm"] = names.get("sgg_nm")
        row["dong_nm"] = names.get("dong_nm")
    return rows


def get_rtt_summary(*, sgg_cd: str, dong_cd: str | None = None) -> dict[str, Any]:
    """기본적으로 오늘 기준 최근 90일간 sgg_cd(+dong_cd, 선택) 조건의 RTT(실거래) 데이터를 집계하여 단일
    JSON으로 반환한다. dong_cd가 없으면 자치구 내 모든 법정동의 거래내역을 대상으로 동일한 로직을 그대로
    적용해 합산한다.

    이 90일 창(오늘 기준)에 조건에 맞는 거래가 하나도 없으면(예: 최근에 거래가 뜸한 지역), 파티션을 하나씩
    확인하는 대신 날짜 범위 제한 없이 RTT 마트 전체(단, ~103일만 보존되는 롤링 마트)에서 조건에 매칭되는
    가장 최근 base_date를 한 번에 찾아(`resolve_recent_match_date`), 그 날짜를 새 end_date로 삼아 90일
    창 전체를 그 시점으로 이동시켜 재조회한다("파티션 폴백"이 아니라 "조회 창의 기준일(anchor) 이동").
    이동된 시작일이 원래 창의 시작일보다 settings.max_base_date_lookback일 이상 더 과거이면 이동하지 않는다.

    RTT 마트 안에서도 매칭이 안 되면(=이 마트의 보존 기간 자체보다 오래된 지역), 마지막 수단으로 실버
    (fact_apt_transactions, Iceberg) 원본 팩트 테이블까지 온디맨드로 내려가 이 지역의 [마지막 거래일 -
    89일 ~ 마지막 거래일] 구간을 그대로 가져온다(_fetch_silver_rows - RTT 자체가 원본의 1:1 행 단위
    재구성이라 별도 집계식 변환 없이 동일한 컬럼 구조로 재사용 가능하다). 재조회/폴백된 결과는 지역
    식별자 키로 최소 1시간 캐싱된다. 그래도 거래 이력 자체가 전혀 없으면 창을 이동하지 않고 기존처럼
    빈 결과를 그대로 반환한다(에러 아님). 창이 실제로 이동된 경우 period_start/period_end는 "오늘 기준
    90일"이 아니라 이동된 실제 구간을 반영한다."""
    start_date, end_date = _period_range(date.today())
    con = duckdb_client.get_connection()
    try:
        rows = _fetch_rows(con, sgg_cd, dong_cd, start_date, end_date)

        if not rows:
            naive_start, naive_end = start_date, end_date

            def _recompute_shifted_window() -> tuple[list[dict[str, Any]], date, date] | None:
                """이 지역 조건에 매칭되는 가장 최근 base_date로 90일 창을 이동시켜 재조회한다.
                RTT 마트 안에서도 못 찾으면(마트 보존기간 밖) 마지막 수단으로 실버 원본
                (fact_apt_transactions)까지 온디맨드로 내려간다. 캐싱 대상은 이 함수의 반환값이다."""
                match_where = "WHERE sgg_cd = $sgg_cd" + (" AND dong_cd = $dong_cd" if dong_cd else "")
                match_params: dict[str, Any] = {
                    "sgg_cd": sgg_cd,
                    **({"dong_cd": dong_cd} if dong_cd else {}),
                }
                full_glob = f"{duckdb_client.mart_base_path(MART_TABLE)}/base_date=*/data.parquet"
                matched_date = duckdb_client.resolve_recent_match_date(
                    con, full_glob, "base_date", match_where, match_params
                )
                if matched_date is not None and matched_date >= naive_start - timedelta(
                    days=settings.max_base_date_lookback
                ):
                    shifted_end = matched_date
                    shifted_start = shifted_end - timedelta(days=PERIOD_DAYS - 1)
                    shifted_rows = _fetch_rows(con, sgg_cd, dong_cd, shifted_start, shifted_end)
                    logger.info(
                        "Anchor fallback used for table=%s, condition_summary=%s, "
                        "naive_window=%s~%s, matched_window=%s~%s",
                        MART_TABLE,
                        match_where[:100],
                        naive_start,
                        naive_end,
                        shifted_start,
                        shifted_end,
                    )
                    return shifted_rows, shifted_start, shifted_end

                # RTT 자체에서 못 찾았으면(마트 보존기간 밖으로 벗어난 지역) 마지막 수단으로 실버
                # 원본(fact_apt_transactions)까지 온디맨드로 내려간다.
                silver_rows = _fetch_silver_rows(con, sgg_cd, dong_cd)
                if silver_rows is None:
                    return None

                shifted_end = date.fromisoformat(max(r["deal_date"] for r in silver_rows))
                shifted_start = shifted_end - timedelta(days=PERIOD_DAYS - 1)
                logger.info(
                    "Silver fallback used for table=%s, condition_summary=%s, "
                    "naive_window=%s~%s, silver_window=%s~%s",
                    SILVER_TABLE,
                    match_where[:100],
                    naive_start,
                    naive_end,
                    shifted_start,
                    shifted_end,
                )
                return silver_rows, shifted_start, shifted_end

            # Fallback으로 계산된 결과(재조회 rows + 이동된 구간)는 지역 식별자 키로 최소 1시간
            # 캐싱되어, 동일 지역 반복 요청 시 resolve_recent_match_date/재조회 스캔을 다시
            # 수행하지 않는다("매칭 자체가 없다"는 None 결과도 함께 캐싱한다).
            cache_key = (sgg_cd, dong_cd)
            cached_result = cached_call(CACHE_NAMESPACE, cache_key, _recompute_shifted_window)
            if cached_result is not None:
                rows, start_date, end_date = cached_result
            # matched_date가 없거나 lookback 상한을 넘으면 rows/기간은 나이브 값 그대로 —
            # 기존과 동일하게 빈 결과 반환(에러 아님).
    finally:
        con.close()

    buckets = _generate_biweekly_buckets(start_date, end_date)
    biweekly_trend = _build_biweekly_trend(rows, buckets)
    total_deal_cnt, total_trade_amount, avg_trade_amount, max_trade_amount = _build_totals(rows)
    avg_pyeong_amount = _build_avg_pyeong_amount(rows, total_deal_cnt)
    sgg_nm = rows[0]["sgg_nm"] if rows else None
    dong_nm = rows[0]["dong_nm"] if (dong_cd and rows) else None
    data_end = max((date.fromisoformat(r["deal_date"]) for r in rows), default=None)

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
        "avg_pyeong_amount": avg_pyeong_amount,
        "max_trade_amount": max_trade_amount,
        "volume_change_rate": _build_volume_change_rate(biweekly_trend, data_end),
        "biweekly_trend": biweekly_trend,
        "pyeong_distribution": _build_pyeong_distribution(rows, total_deal_cnt),
        "recent_trades": _build_recent_trades(rows, include_location=not dong_cd),
        "top5_by_volume": _build_top5_by_volume(rows),
    }
