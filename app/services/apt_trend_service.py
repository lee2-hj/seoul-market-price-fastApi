import logging
from collections import OrderedDict
from datetime import date, timedelta
from typing import Any

from app.core import duckdb_client
from app.core.config import settings

# apt_mkt_trends 마트 실제 컬럼(DESCRIBE로 확인):
# cgg_cd, cgg_nm, stdg_cd, stdg_nm, apt_name, mno, sno, deal_date, floor,
# trade_amount(DECIMAL, 만원), pyeong(DOUBLE), trade_count(INTEGER), pyeong_amt(DOUBLE), base_date.
# apt_name은 실제 컬럼이며 항상 채워져 있다(NULL/빈값 없음 확인). 다만 apt_name은 전역 고유하지 않고
# (예: '현대'가 26개 서로 다른 법정동에 존재) 같은 법정동 안에서 한 단지가 여러 지번(mno/sno)에 걸쳐
# 있을 수 있어(예: 화곡동 '남광아파트' 2개 지번), 그룹 키는 반드시 (cgg_cd, stdg_cd, apt_name)로 잡아야 한다.
# 한 row는 (cgg_cd, stdg_cd, mno, sno, deal_date, floor, pyeong) 조합으로 유일하고,
# trade_amount/trade_count는 그 조합에 몰린 거래건들의 합계 금액/건수다(RTT 마트와 동일한 관례).
MART_TABLE = "apt_mkt_trends"
PERIOD_DAYS = 90
BIWEEKLY_BUCKET_COUNT = 6
PYEONG_DIVISOR = 3.305785

logger = logging.getLogger(__name__)


def _period_range(today: date) -> tuple[date, date]:
    """today(anchor)를 기준으로 (anchor - 90일) ~ anchor 구간의 시작일/종료일을 반환한다. 처음 호출 시
    anchor는 실제 오늘 날짜이지만, 그 구간에 조건에 맞는 거래가 없으면 get_apt_trend_summary()가 이
    anchor를 과거로 이동시킬 수 있다 — 즉 최종 응답의 search_period가 항상 "오늘 기준"이라고 가정하면
    안 된다."""
    end_date = today
    start_date = today - timedelta(days=PERIOD_DAYS)
    return start_date, end_date


def _build_entity_conditions(
    cgg_cd: str | None,
    stdg_cd: str | None,
    mno: str | None,
    sno: str | None,
    apt_name: str | None,
) -> tuple[list[str], dict[str, Any]]:
    """날짜 조건을 제외한, 단지 필터(cgg_cd/stdg_cd/mno/sno/apt_name) 조건 목록과 파라미터.
    날짜 조건(deal_date BETWEEN ...)이 항상 포함되는 _build_where_clause가 재사용한다."""
    conditions: list[str] = []
    params: dict[str, Any] = {}
    if cgg_cd:
        conditions.append("cgg_cd = $cgg_cd")
        params["cgg_cd"] = cgg_cd
    if stdg_cd:
        conditions.append("stdg_cd = $stdg_cd")
        params["stdg_cd"] = stdg_cd
    if mno:
        conditions.append("mno = $mno")
        params["mno"] = mno
    if sno:
        conditions.append("sno = $sno")
        params["sno"] = sno
    if apt_name and apt_name.strip():
        # apt_mkt_trends의 실제 apt_name 컬럼을 대소문자 무시 부분일치로 필터링한다.
        conditions.append("apt_name ILIKE $apt_name")
        params["apt_name"] = f"%{apt_name.strip()}%"
    return conditions, params


def _build_where_clause(
    cgg_cd: str | None,
    stdg_cd: str | None,
    mno: str | None,
    sno: str | None,
    apt_name: str | None,
    start_date: date,
    end_date: date,
) -> tuple[str, dict[str, Any]]:
    entity_conditions, entity_params = _build_entity_conditions(cgg_cd, stdg_cd, mno, sno, apt_name)
    conditions = ["deal_date BETWEEN $start_date AND $end_date", *entity_conditions]
    params: dict[str, Any] = {"start_date": start_date, "end_date": end_date, **entity_params}
    return "WHERE " + " AND ".join(conditions), params


def _log_explain_analyze(con, query: str, params: dict[str, Any]) -> None:
    """settings.apt_trend_explain_analyze가 켜져 있을 때만 이 쿼리를 EXPLAIN ANALYZE로 한 번 더
    실행해 실행계획+실측 소요시간(단계별 operator timing)을 로그로 남긴다 — 캐시 미스 시 49초
    가까이 걸리는 원인(예: read_parquet가 base_date 파티션 프루닝 없이 마트 전체 이력을 스캔한 뒤
    deal_date 필터를 뒤늦게 적용하는지 등)을 확인하기 위한 임시 진단 도구다.

    EXPLAIN ANALYZE는 실행계획만 보여주는 게 아니라 쿼리를 실제로 다시 한번 실행하므로, 상시
    켜두면 캐시 미스 시 응답 시간이 거의 2배가 된다 - 기본값 False로 두고, 진단이 필요할 때만
    APT_TREND_EXPLAIN_ANALYZE=true로 켜서 로그를 확인한 뒤 다시 꺼야 한다."""
    if not settings.apt_trend_explain_analyze:
        return
    try:
        plan_rows = con.execute(f"EXPLAIN ANALYZE {query}", params).fetchall()
        plan_text = "\n".join(str(cell) for row in plan_rows for cell in row)
        logger.info("[EXPLAIN ANALYZE] apt_trend_service._fetch_rows:\n%s", plan_text)
    except Exception:
        logger.exception("EXPLAIN ANALYZE 실행 중 오류 발생(진단 목적이므로 본 요청 조회는 계속 진행)")


def _fetch_rows(
    con,
    base_date: str,
    cgg_cd: str | None,
    stdg_cd: str | None,
    mno: str | None,
    sno: str | None,
    apt_name: str | None,
    start_date: date,
    end_date: date,
) -> list[dict[str, Any]]:
    """apt_mkt_trends 마트의 지정된 base_date 파티션 하나에서 필터 조건에 맞는 row를 조회한다. 과거에는
    base_date 파티션 전체를 재귀 glob(`/**/*.parquet`)으로 스캔했으나(캐시 미스 시 49초 가까이
    소요), 이 마트는 각 base_date 파티션 자체가 그 시점 기준 최근 90일치 롤링 윈도우를 담고
    있으므로 파티션 하나만 읽으면 충분하다. 어느 base_date를 읽을지는 호출부
    (get_apt_trend_summary)가 결정한다 - 최신 파티션에 매칭 데이터가 없으면 과거 base_date
    파티션으로 폴백해(resolve_base_date_for_filter) 이 함수를 다시 호출할 수 있다(이 함수 자체는
    폴백을 모른다)."""
    parquet_glob = f"{duckdb_client.mart_base_path(MART_TABLE)}/base_date={base_date}/*.parquet"
    where_clause, params = _build_where_clause(cgg_cd, stdg_cd, mno, sno, apt_name, start_date, end_date)
    query = f"""
        SELECT
            cgg_cd, cgg_nm, stdg_cd, stdg_nm, apt_name, mno, sno,
            deal_date, floor, trade_amount, pyeong, trade_count
        FROM read_parquet('{parquet_glob}')
        {where_clause}
    """
    _log_explain_analyze(con, query, params)
    result = con.execute(query, params)
    return duckdb_client.rows_to_dicts(result)


def _to_exclusive_area(pyeong: float) -> str:
    """마트에 전용면적(㎡) 컬럼이 없어, pyeong * 3.305785로 역산해 표시용 문자열을 만든다."""
    return f"{pyeong * PYEONG_DIVISOR:.2f}"


def _group_key(row: dict[str, Any]) -> tuple[str, str, str]:
    """단지 그룹 키. apt_name은 전역 고유하지 않으므로(동명 단지 다수 존재) 반드시
    (cgg_cd, stdg_cd, apt_name)로 묶어야 서로 다른 동의 동명 단지가 섞이지 않는다."""
    return row["cgg_cd"], row["stdg_cd"], row["apt_name"]


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
    trend: list[dict[str, Any]] = []
    for bucket_start, bucket_end in buckets:
        # duckdb_client.rows_to_dicts()가 date를 ISO 문자열로 변환하므로(rtt_service와 동일 관례),
        # 문자열끼리 비교한다(ISO 8601 형식은 사전식 비교 = 날짜순 비교).
        start_str, end_str = bucket_start.isoformat(), bucket_end.isoformat()
        bucket_rows = [r for r in rows if start_str <= r["deal_date"] <= end_str]
        deal_count = sum(r["trade_count"] for r in bucket_rows)
        total_amount = sum(r["trade_amount"] for r in bucket_rows)
        avg_price = round(total_amount / deal_count) if deal_count else 0
        trend.append(
            {
                "biweekly_period": f"{bucket_start.isoformat()}/{bucket_end.isoformat()}",
                "deal_count": deal_count,
                "avg_price": avg_price,
            }
        )
    return trend


def _build_count_change_rate(biweekly_trend: list[dict[str, Any]]) -> int | None:
    """거래가 있는(deal_count > 0) 구간끼리만 순서대로 짝지어 증감률을 계산해, 선형 증가하는
    가중치(최신 구간일수록 가중치가 높음)로 가중평균한다.

    거래가 아예 없는(0건) 구간은 짝짓기에서 완전히 제외한다(인접한 원래 순번끼리 비교하지
    않는다) — 그렇지 않으면 저거래량 단지에서 중간중간 0건 구간이 인접 구간과 그대로 짝지어져
    -100%에 가까운 왜곡된 증감률이 나올 수 있다. 예를 들어 6구간 거래량이 [5,0,0,0,0,3]이면
    "인접 구간끼리" 비교할 경우 첫 스텝(5->0)만으로 -100%가 나오지만, 실제로는 5건에서 3건으로
    완만히 줄어든 것뿐이다 - 거래가 있는 구간끼리(5와 3)만 비교하면 -40%로 정확히 계산된다.

    가중치는 "이 스텝의 뒤쪽(curr) 구간이 원래 biweekly_trend에서 몇 번째(0-based index)인가"를
    그대로 사용한다 - 사이에 낀 0건 구간을 건너뛰어도, 그 구간이 원래 얼마나 최근이었는지에 따른
    가중치 부여 원칙(최신일수록 높은 가중치)은 그대로 유지하기 위함이다.

    거래가 있는 구간이 2개 미만이면(=비교할 스텝 자체가 없음) None을 반환한다."""
    non_zero = [(i, trend["deal_count"]) for i, trend in enumerate(biweekly_trend) if trend["deal_count"] > 0]
    if len(non_zero) < 2:
        return None

    weighted_sum = 0.0
    weight_total = 0
    for (_, prev_count), (curr_index, curr_count) in zip(non_zero, non_zero[1:]):
        weight = curr_index  # 원래 biweekly_trend에서의 위치(0-based) - 최신일수록 큰 값.
        step_rate = (curr_count - prev_count) / prev_count * 100
        weighted_sum += step_rate * weight
        weight_total += weight

    if weight_total == 0:
        return None
    return round(weighted_sum / weight_total)


def _pyeong_grp(pyeong: float) -> str:
    """평형을 10평 단위 그룹으로 분류한다. area_deals/recent_deals의 표시용 pyeong과 동일하게 반올림한 값을
    기준으로 그룹을 나눠야 한다(예: 19.97평은 반올림하면 20평이므로 '20' 그룹이어야 하며, 반올림 전 원본값을
    그대로 버림(floor) 계산하면 '10' 그룹으로 잘못 분류된다). 10평 미만은 '10' 그룹에 포함하고, 그 이상은
    실제 데이터 범위에 맞춰 50/60/70... 등 상한 없이 동적으로 분류한다."""
    bucket = (round(pyeong) // 10) * 10
    return str(bucket) if bucket >= 10 else "10"


def _build_area_ratio(rows: list[dict[str, Any]], total_deal_count: int) -> list[dict[str, Any]]:
    """평형 그룹(10평 단위, 상한 없이 실제 데이터 기준으로 동적 분류)별 거래건수와 전체 대비 비중(%)을 집계한다.
    거래가 없는(비중 0%) 그룹은 결과에 포함하지 않는다."""
    counts: dict[str, int] = {}
    for row in rows:
        grp = _pyeong_grp(row["pyeong"])
        counts[grp] = counts.get(grp, 0) + row["trade_count"]

    result: list[dict[str, Any]] = []
    for grp in sorted(counts, key=int):
        deal_count = counts[grp]
        if deal_count <= 0:
            continue
        share_percentage = round(deal_count / total_deal_count * 100, 2) if total_deal_count else 0.0
        result.append({"pyeong_grp": grp, "deal_count": deal_count, "share_percentage": share_percentage})
    return result


def _build_recent_deals(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """개수 제한 없이 전체 거래 내역을 거래일자 최신순(내림차순)으로 반환한다."""
    ordered = sorted(rows, key=lambda r: r["deal_date"], reverse=True)
    return [
        {
            "deal_date": r["deal_date"],
            "exclusive_area": _to_exclusive_area(r["pyeong"]),
            "pyeong": round(r["pyeong"]),
            "floor": r["floor"],
            "deal_amount": round(r["trade_amount"] / r["trade_count"]) if r["trade_count"] else 0,
        }
        for r in ordered
    ]


def _build_area_deals(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: "OrderedDict[float, dict[str, Any]]" = OrderedDict()
    for row in rows:
        pyeong = row["pyeong"]
        group = groups.get(pyeong)
        if group is None:
            group = {"pyeong": pyeong, "_cnt": 0, "_amt": 0}
            groups[pyeong] = group
        group["_cnt"] += row["trade_count"]
        group["_amt"] += row["trade_amount"]

    return [
        {
            "exclusive_area": _to_exclusive_area(g["pyeong"]),
            "pyeong": round(g["pyeong"]),
            "deal_count": g["_cnt"],
            "avg_deal_price": round(g["_amt"] / g["_cnt"]) if g["_cnt"] else 0,
        }
        for g in sorted(groups.values(), key=lambda g: g["pyeong"])
    ]


def _build_apt_trend_item(
    key: tuple[str, str, str],
    rows: list[dict[str, Any]],
    buckets: list[tuple[date, date]],
) -> dict[str, Any]:
    cgg_cd, stdg_cd, apt_name = key
    first = rows[0]

    total_deal_count = sum(r["trade_count"] for r in rows)
    total_deal_amount = round(sum(r["trade_amount"] for r in rows))
    average_deal_price = round(total_deal_amount / total_deal_count) if total_deal_count else 0
    max_deal_price = round(
        max((r["trade_amount"] / r["trade_count"] for r in rows if r["trade_count"]), default=0)
    )
    biweekly_trend = _build_biweekly_trend(rows, buckets)

    return {
        "apt_name": apt_name,
        "cgg_cd": cgg_cd,
        "cgg_nm": first["cgg_nm"],
        "stdg_cd": stdg_cd,
        "stdg_nm": first["stdg_nm"],
        "total_deal_count": total_deal_count,
        "total_deal_amount": total_deal_amount,
        "average_deal_price": average_deal_price,
        "max_deal_price": max_deal_price,
        "count_change_rate": _build_count_change_rate(biweekly_trend),
        "biweekly_trend": biweekly_trend,
        "area_ratio": _build_area_ratio(rows, total_deal_count),
        "recent_deals": _build_recent_deals(rows),
        "area_deals": _build_area_deals(rows),
    }


def get_apt_trend_summary(
    *,
    cgg_cd: str | None,
    stdg_cd: str | None,
    mno: str | None,
    sno: str | None,
    apt_name: str | None = None,
) -> dict[str, Any]:
    """기본적으로 오늘 기준 최근 90일간, 지정된(선택적) 조건에 맞는 apt_mkt_trends 실거래 데이터를 단지
    (cgg_cd+stdg_cd+apt_name) 단위로 집계하여 단일 JSON으로 반환한다. apt_name은 apt_mkt_trends의 실제
    컬럼이지만 전역 고유하지 않아(동명 단지가 여러 법정동에 존재) cgg_cd+stdg_cd와 함께 그룹 키로 사용한다.
    apt_name이 주어지면 실제 apt_name 컬럼을 SQL WHERE(ILIKE)에서 부분일치 필터링한다(다른 마트를
    조인하지 않는다).

    최신 base_date 파티션(오늘 기준 최근 90일 롤링 윈도우)에 조건에 맞는 거래가 하나도 없으면,
    날짜 조건을 뺀 단지 필터(cgg_cd/stdg_cd/mno/sno/apt_name)만으로 과거 base_date 파티션들을
    최신순으로(최대 settings.max_base_date_lookback개) 훑어 조건에 매칭되는 가장 최근 파티션을
    찾는다(duckdb_client.resolve_base_date_for_filter - 파티션당 가벼운 EXISTS 쿼리 1회, 매칭되면
    즉시 조기 종료). 매칭되는 과거 파티션을 찾으면 그 base_date를 새 anchor로 삼아 90일 창 전체
    (그 base_date - 90일 ~ 그 base_date)를 다시 조회한다 - 이 마트는 각 base_date 파티션 자체가
    그 시점 기준 롤링 90일 윈도우이므로, 과거 파티션 폴백이 곧 "그 시점 기준 최근 90일" 재조회와
    같다. lookback 내에 매칭되는 파티션이 없으면(또는 최신 파티션과 동일하면) 폴백하지 않고
    기존처럼 빈 결과를 그대로 반환한다(에러 아님) - 실버(fact_apt_transactions, Iceberg)
    레이어까지 거슬러 올라가는 폴백은 없다. 폴백이 발생하면 search_period.start_date/end_date는
    "오늘 기준 90일"이 아니라 실제 사용된 base_date 기준 구간을 반영한다.

    count_change_rate는 biweekly_trend(90일을 6구간으로 균등 분할한 거래량)에서 거래가 있는
    구간끼리만 순서대로 짝지어(0건 구간은 짝짓기에서 제외) 증감률을 계산하고, 각 스텝 뒤쪽 구간의
    원래 위치가 최신일수록 높은 가중치로 가중평균한다(자세한 내용은 _build_count_change_rate 참고).
    여러 단지가 매칭되면 총 거래건수(total_deal_count) 내림차순으로 정렬한다."""
    start_date, end_date = _period_range(date.today())
    con = duckdb_client.get_connection()
    try:
        latest_base_date = duckdb_client.resolve_base_date_cached(con, MART_TABLE)
        rows = _fetch_rows(con, latest_base_date, cgg_cd, stdg_cd, mno, sno, apt_name, start_date, end_date)

        if not rows:
            naive_start, naive_end = start_date, end_date
            entity_conditions, entity_params = _build_entity_conditions(cgg_cd, stdg_cd, mno, sno, apt_name)
            entity_where = ("WHERE " + " AND ".join(entity_conditions)) if entity_conditions else ""
            fallback_base_date = duckdb_client.resolve_base_date_for_filter(
                con, MART_TABLE, entity_where, entity_params, max_lookback=settings.max_base_date_lookback
            )
            if fallback_base_date is not None and fallback_base_date != latest_base_date:
                end_date = date.fromisoformat(fallback_base_date)
                start_date = end_date - timedelta(days=PERIOD_DAYS)
                rows = _fetch_rows(
                    con, fallback_base_date, cgg_cd, stdg_cd, mno, sno, apt_name, start_date, end_date
                )
                logger.info(
                    "Base-date fallback used for table=%s, condition_summary=%s, "
                    "naive_window=%s~%s, matched_base_date=%s, matched_window=%s~%s",
                    MART_TABLE,
                    (entity_where or "(no filter)")[:100],
                    naive_start,
                    naive_end,
                    fallback_base_date,
                    start_date,
                    end_date,
                )
            elif fallback_base_date == latest_base_date:  # ← 여기서부터 추가
                parquet_glob = f"{duckdb_client.mart_base_path(MART_TABLE)}/base_date={latest_base_date}/*.parquet"
                latest_deal = duckdb_client.resolve_recent_match_date(
                    con, parquet_glob, "deal_date", entity_where, entity_params
                )
                if latest_deal is not None:
                    end_date = latest_deal
                    start_date = end_date - timedelta(days=PERIOD_DAYS)
                    rows = _fetch_rows(
                        con, latest_base_date, cgg_cd, stdg_cd, mno, sno, apt_name, start_date, end_date
                    )
                    logger.info(
                        "Deal-date window shifted: table=%s, latest_deal=%s, shifted_window=%s~%s",
                        MART_TABLE, latest_deal, start_date, end_date,
                    )
            # fallback_base_date가 None이거나(=lookback 내 매칭 파티션 없음) latest_base_date와
            # 같으면(이미 확인한 파티션) rows/기간은 나이브 값 그대로 - 빈 결과 반환(에러 아님).
    finally:
        con.close()

    buckets = _generate_biweekly_buckets(start_date, end_date)

    grouped: "OrderedDict[tuple[str, str, str], list[dict[str, Any]]]" = OrderedDict()
    for row in rows:
        grouped.setdefault(_group_key(row), []).append(row)

    items = [
        _build_apt_trend_item(key, group_rows, buckets)
        for key, group_rows in grouped.items()
    ]
    items.sort(key=lambda item: item["total_deal_count"], reverse=True)

    return {
        "status": "success",
        "search_period": {"start_date": start_date, "end_date": end_date},
        "count": len(items),
        "data": items,
    }
