from collections import OrderedDict
from datetime import date, timedelta
from typing import Any

from app.core import duckdb_client

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
MIN_TRADE_COUNT = 3


def _period_range(today: date) -> tuple[date, date]:
    """오늘을 기준으로 (today - 90일) ~ 오늘 구간의 시작일/종료일을 반환한다."""
    end_date = today
    start_date = today - timedelta(days=PERIOD_DAYS)
    return start_date, end_date


def _build_where_clause(
    cgg_cd: str | None,
    stdg_cd: str | None,
    mno: str | None,
    sno: str | None,
    apt_name: str | None,
    start_date: date,
    end_date: date,
) -> tuple[str, dict[str, Any]]:
    conditions = ["deal_date BETWEEN $start_date AND $end_date"]
    params: dict[str, Any] = {"start_date": start_date, "end_date": end_date}
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
    return "WHERE " + " AND ".join(conditions), params


def _fetch_rows(
    con,
    cgg_cd: str | None,
    stdg_cd: str | None,
    mno: str | None,
    sno: str | None,
    apt_name: str | None,
    start_date: date,
    end_date: date,
) -> list[dict[str, Any]]:
    """apt_mkt_trends 마트(재귀 glob, base_date 파티션 전체) 에서 필터 조건에 맞는 row를 조회한다."""
    parquet_glob = f"{duckdb_client.mart_base_path(MART_TABLE)}/**/*.parquet"
    where_clause, params = _build_where_clause(cgg_cd, stdg_cd, mno, sno, apt_name, start_date, end_date)
    query = f"""
        SELECT
            cgg_cd, cgg_nm, stdg_cd, stdg_nm, apt_name, mno, sno,
            deal_date, floor, trade_amount, pyeong, trade_count
        FROM read_parquet('{parquet_glob}')
        {where_clause}
    """
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
    """인접한 2주 구간 간 deal_count 증감률을 순서대로 계산해, 오래된 스텝부터 1,2,3,...로 선형 증가하는
    가중치(최신 스텝일수록 가중치가 높음)로 가중평균한다. 스텝 양쪽 구간 중 하나라도 deal_count가
    MIN_TRADE_COUNT 미만이면 해당 스텝은 가중치 0으로 제외한다. 유효 스텝(가중치 > 0)이 하나도 없으면
    None을 반환한다."""
    step_count = len(biweekly_trend) - 1
    if step_count < 1:
        return None

    weighted_sum = 0.0
    weight_total = 0
    for i in range(step_count):
        prev_count = biweekly_trend[i]["deal_count"]
        curr_count = biweekly_trend[i + 1]["deal_count"]
        weight = 0 if (prev_count < MIN_TRADE_COUNT or curr_count < MIN_TRADE_COUNT) else i + 1
        if weight == 0:
            continue
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
    """오늘 기준 최근 90일간, 지정된(선택적) 조건에 맞는 apt_mkt_trends 실거래 데이터를 단지
    (cgg_cd+stdg_cd+apt_name) 단위로 집계하여 단일 JSON으로 반환한다. apt_name은 apt_mkt_trends의 실제
    컬럼이지만 전역 고유하지 않아(동명 단지가 여러 법정동에 존재) cgg_cd+stdg_cd와 함께 그룹 키로 사용한다.
    apt_name이 주어지면 실제 apt_name 컬럼을 SQL WHERE(ILIKE)에서 부분일치 필터링한다
    (다른 마트를 조인하지 않으며, 매칭되는 데이터가 없으면 빈 결과를 그대로 반환한다).
    count_change_rate는 다른 기간과 비교하거나 구간을 반으로 쪼개지 않고, biweekly_trend(90일을 6구간으로
    균등 분할한 거래량 전체)에 선형회귀로 추세선을 구해 시작 추정치 대비 끝 추정치 변화율(%)로 계산한다.
    여러 단지가 매칭되면 총 거래건수(total_deal_count) 내림차순으로 정렬한다."""
    start_date, end_date = _period_range(date.today())
    con = duckdb_client.get_connection()
    try:
        rows = _fetch_rows(con, cgg_cd, stdg_cd, mno, sno, apt_name, start_date, end_date)
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
