import logging
from collections import OrderedDict
from datetime import date, timedelta
from typing import Any

from app.core import duckdb_client
from app.core.cache import cached_call
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

# --- 실버(Iceberg fact) 레이어 Fallback -------------------------------------------------
# apt_mkt_trends는 "전체 이력"이 아니라 최근 ~100여 일만 보존하는 롤링 마트다(실측 확인: 특정
# 시점 기준 MIN(deal_date)~MAX(deal_date) 범위가 약 100일 폭으로 계속 밀려 있음). 그래서
# resolve_recent_match_date로 이 마트 전체를 뒤져도, 단지의 마지막 실거래가 그 보존 기간보다
# 오래됐으면(예: 마지막 거래가 100일도 더 전) 영원히 매칭되지 않는다 - 이 마트 자체가 "골드
# 레이어에 데이터가 누락된 단지" 상태다. 이 경우 원본 실거래 팩트 테이블(fact_apt_transactions,
# Iceberg)까지 온디맨드로 내려가 [마지막 거래일 - 89일 ~ 마지막 거래일] 구간을 집계한다.
SILVER_TABLE = settings.silver_apt_transactions_table

# 앵커(조회 창 기준일) 이동으로 재조회한 결과(apt_mkt_trends 재스캔이든 fact_apt_transactions
# Fallback이든)는 단지 식별자 키로 최소 1시간 캐싱해 동일 단지 반복 요청 시 스토리지 I/O를
# 원천 차단한다.
CACHE_NAMESPACE = "apt_trend:anchor_fallback"

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
    range-앵커 폴백(resolve_recent_match_date)은 날짜 범위 없이 이 조건만으로 이력 전체를
    조회해야 하므로, 날짜 조건이 항상 포함되는 _build_where_clause와 분리했다."""
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


def _build_silver_entity_conditions(
    cgg_cd: str | None,
    stdg_cd: str | None,
    mno: str | None,
    sno: str | None,
    apt_name: str | None,
) -> tuple[list[str], dict[str, Any]]:
    """_build_entity_conditions()의 실버(fact_apt_transactions) 버전. 조건 의미는 완전히
    동일하지만(자치구/법정동/지번/아파트명 부분일치), 컬럼명이 다르다
    (cgg_cd/stdg_cd -> sgg_cd/dong_cd). 취소된 거래(cancel_date가 채워진 행)는 항상 제외한다
    (apt_mkt_trends는 이미 취소 반영 후 적재된 마트라 이 필터가 필요 없지만, 원본 팩트
    테이블은 취소 여부를 그대로 갖고 있다)."""
    conditions: list[str] = ["(cancel_date IS NULL OR cancel_date = '')"]
    params: dict[str, Any] = {}
    if cgg_cd:
        conditions.append("sgg_cd = $sgg_cd")
        params["sgg_cd"] = cgg_cd
    if stdg_cd:
        conditions.append("dong_cd = $dong_cd")
        params["dong_cd"] = stdg_cd
    if mno:
        conditions.append("mno = $mno")
        params["mno"] = mno
    if sno:
        conditions.append("sno = $sno")
        params["sno"] = sno
    if apt_name and apt_name.strip():
        conditions.append("apt_name ILIKE $apt_name")
        params["apt_name"] = f"%{apt_name.strip()}%"
    return conditions, params


def _fetch_silver_rows(
    con,
    cgg_cd: str | None,
    stdg_cd: str | None,
    mno: str | None,
    sno: str | None,
    apt_name: str | None,
) -> list[dict[str, Any]] | None:
    """apt_mkt_trends 마트 자체의 앵커 폴백(_recompute_shifted_window)도 매칭 데이터를 찾지
    못했을 때(=이 마트의 ~100여 일 보존 기간 자체를 벗어난 단지, 모듈 상단 주석 참고) 마지막
    수단으로 실버(fact_apt_transactions, Iceberg) 원본 팩트 테이블에서 이 단지의
    [마지막 거래일 - 89일 ~ 마지막 거래일] 구간을 온디맨드로 스캔한다.

    한 번의 스캔(matched CTE)으로 이 단지 조건(및 취소 제외)으로 먼저 좁힌 뒤, 그 결과 안에서만
    MAX(deal_date)와 90일 윈도우 슬라이싱을 수행한다. apt_mkt_trends와 동일한 그룹 키
    (deal_date, floor, pyeong)로 합산해(같은 조합에 몰린 거래건을 하나로 묶는 apt_mkt_trends의
    기존 관례와 동일) trade_count/trade_amount를 만들고, pyeong은 apt_mkt_trends와 동일하게
    순수 전용면적 환산(exclusive_area_m2 / PYEONG_DIVISOR, 소수 둘째 자리 반올림)이다 -
    region_apt_compare_service(dm_apt_recent_trade)에서 쓰인 공급면적 배수(1.3)는 여기 적용하지
    않는다(실측 교차검증: apt_mkt_trends 자체가 이 배수 없이 저장돼 있음을 확인했다).

    반환 row는 기존 _fetch_rows()와 완전히 동일한 키 구조(cgg_cd/cgg_nm/stdg_cd/stdg_nm/
    apt_name/mno/sno/deal_date/floor/trade_amount/pyeong/trade_count)라, 이후의 그룹화·집계
    로직(_build_apt_trend_item 등)을 한 글자도 바꾸지 않고 그대로 재사용한다(cgg_nm/stdg_nm은
    fact_apt_transactions에 없는 지역명이라 dim_apartment에서 보완한다).

    이 단지의 거래 이력이 fact_apt_transactions에도 전혀 없으면 None을 반환한다."""
    con.execute("INSTALL iceberg;")
    con.execute("LOAD iceberg;")

    conditions, params = _build_silver_entity_conditions(cgg_cd, stdg_cd, mno, sno, apt_name)
    params["path"] = duckdb_client.silver_base_path(SILVER_TABLE)
    query = f"""
        WITH matched AS (
            SELECT sgg_cd, dong_cd, apt_name, mno, sno, deal_date, floor, price_ten_thousand, exclusive_area_m2
            FROM iceberg_scan($path)
            WHERE {" AND ".join(conditions)}
        ),
        bounds AS (
            SELECT MAX(deal_date) AS last_date FROM matched
        ),
        windowed AS (
            SELECT
                m.sgg_cd, m.dong_cd, m.apt_name, m.mno, m.sno, m.deal_date, m.floor,
                ROUND(m.exclusive_area_m2 / {PYEONG_DIVISOR}, 2) AS pyeong,
                m.price_ten_thousand
            FROM matched m, bounds b
            WHERE b.last_date IS NOT NULL
              AND m.deal_date BETWEEN b.last_date - INTERVAL {PERIOD_DAYS} DAY AND b.last_date
        )
        SELECT
            sgg_cd AS cgg_cd, dong_cd AS stdg_cd, apt_name, mno, sno, deal_date, floor, pyeong,
            CAST(ROUND(SUM(price_ten_thousand)) AS BIGINT) AS trade_amount,
            COUNT(*) AS trade_count
        FROM windowed
        GROUP BY sgg_cd, dong_cd, apt_name, mno, sno, deal_date, floor, pyeong
    """
    rows = duckdb_client.rows_to_dicts(con.execute(query, params))
    if not rows:
        return None

    name_query = """
        SELECT ANY_VALUE(sgg_nm) AS cgg_nm, ANY_VALUE(dong_nm) AS stdg_nm
        FROM iceberg_scan($path)
        WHERE sgg_cd = $sgg_cd AND dong_cd = $dong_cd
    """
    name_params = {
        "path": duckdb_client.silver_base_path("dim_apartment"),
        "sgg_cd": cgg_cd,
        "dong_cd": stdg_cd,
    }
    name_rows = duckdb_client.rows_to_dicts(con.execute(name_query, name_params))
    cgg_nm = name_rows[0]["cgg_nm"] if name_rows else None
    stdg_nm = name_rows[0]["stdg_nm"] if name_rows else None
    for row in rows:
        row["cgg_nm"] = cgg_nm
        row["stdg_nm"] = stdg_nm
    return rows


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

    이 90일 창(오늘 기준)에 조건에 맞는 거래가 하나도 없으면, 날짜 범위 제한 없이 apt_mkt_trends
    전체(단, ~100여 일만 보존되는 롤링 마트)에서 조건에 매칭되는 가장 최근 deal_date를 한 번에
    찾아(`resolve_recent_match_date`) 그 날짜를 새 end_date로 삼아 90일 창 전체를 그 시점으로
    이동시켜 재조회한다("파티션 폴백"이 아니라 "조회 창의 기준일(anchor) 이동"). 이동된 시작일이
    원래 창의 시작일보다 settings.max_base_date_lookback일 이상 더 과거이면 이동하지 않는다.

    apt_mkt_trends 안에서도 매칭이 안 되면(=이 마트의 보존 기간 자체보다 오래된 단지), 마지막
    수단으로 실버(fact_apt_transactions, Iceberg) 원본 팩트 테이블까지 온디맨드로 내려가 이 단지의
    [마지막 거래일 - 89일 ~ 마지막 거래일] 구간을 집계한다(_fetch_silver_rows). 이렇게 재조회/폴백된
    결과는 단지 식별자 키로 최소 1시간 캐싱된다. 그래도 거래 이력 자체가 전혀 없으면 창을 이동하지
    않고 기존처럼 빈 결과를 그대로 반환한다(에러 아님). 창이 실제로 이동된 경우
    search_period.start_date/end_date는 "오늘 기준 90일"이 아니라 이동된 실제 구간을 반영한다.

    count_change_rate는 biweekly_trend(90일을 6구간으로 균등 분할한 거래량)에서 거래가 있는
    구간끼리만 순서대로 짝지어(0건 구간은 짝짓기에서 제외) 증감률을 계산하고, 각 스텝 뒤쪽 구간의
    원래 위치가 최신일수록 높은 가중치로 가중평균한다(자세한 내용은 _build_count_change_rate 참고).
    여러 단지가 매칭되면 총 거래건수(total_deal_count) 내림차순으로 정렬한다."""
    start_date, end_date = _period_range(date.today())
    con = duckdb_client.get_connection()
    try:
        rows = _fetch_rows(con, cgg_cd, stdg_cd, mno, sno, apt_name, start_date, end_date)

        if not rows:
            naive_start, naive_end = start_date, end_date

            def _recompute_shifted_window() -> tuple[list[dict[str, Any]], date, date] | None:
                """이 단지 조건에 매칭되는 가장 최근 deal_date로 90일 창을 이동시켜 재조회한다.
                이동할 수 없으면(매칭 자체가 없거나 lookback 상한을 넘으면) None을 반환해
                호출자가 나이브 빈 결과를 그대로 쓰게 한다. 캐싱 대상은 이 함수의 반환값
                (재조회된 rows + 이동된 실제 구간)이다."""
                entity_conditions, entity_params = _build_entity_conditions(
                    cgg_cd, stdg_cd, mno, sno, apt_name
                )
                match_where = ("WHERE " + " AND ".join(entity_conditions)) if entity_conditions else ""
                full_glob = f"{duckdb_client.mart_base_path(MART_TABLE)}/**/*.parquet"
                matched_date = duckdb_client.resolve_recent_match_date(
                    con, full_glob, "deal_date", match_where, entity_params
                )
                if matched_date is not None and matched_date >= naive_start - timedelta(
                    days=settings.max_base_date_lookback
                ):
                    shifted_end = matched_date
                    shifted_start = shifted_end - timedelta(days=PERIOD_DAYS)
                    shifted_rows = _fetch_rows(
                        con, cgg_cd, stdg_cd, mno, sno, apt_name, shifted_start, shifted_end
                    )
                    logger.info(
                        "Anchor fallback used for table=%s, condition_summary=%s, "
                        "naive_window=%s~%s, matched_window=%s~%s",
                        MART_TABLE,
                        (match_where or "(no filter)")[:100],
                        naive_start,
                        naive_end,
                        shifted_start,
                        shifted_end,
                    )
                    return shifted_rows, shifted_start, shifted_end

                # apt_mkt_trends 자체에서 못 찾았으면(마트 보존기간 밖으로 벗어난 단지) 마지막
                # 수단으로 실버 원본(fact_apt_transactions)까지 온디맨드로 내려간다.
                silver_rows = _fetch_silver_rows(con, cgg_cd, stdg_cd, mno, sno, apt_name)
                if silver_rows is None:
                    return None

                shifted_end = date.fromisoformat(max(r["deal_date"] for r in silver_rows))
                shifted_start = shifted_end - timedelta(days=PERIOD_DAYS)
                logger.info(
                    "Silver fallback used for table=%s, condition_summary=%s, "
                    "naive_window=%s~%s, silver_window=%s~%s",
                    SILVER_TABLE,
                    (match_where or "(no filter)")[:100],
                    naive_start,
                    naive_end,
                    shifted_start,
                    shifted_end,
                )
                return silver_rows, shifted_start, shifted_end

            # Fallback으로 계산된 결과(재조회 rows + 이동된 구간)는 단지 식별자 키로 최소 1시간
            # 캐싱되어, 동일 단지 반복 요청 시 resolve_recent_match_date/재조회 스캔을 다시
            # 수행하지 않는다("매칭 자체가 없다"는 None 결과도 함께 캐싱한다).
            cache_key = (cgg_cd, stdg_cd, mno, sno, apt_name)
            cached_result = cached_call(CACHE_NAMESPACE, cache_key, _recompute_shifted_window)
            if cached_result is not None:
                rows, start_date, end_date = cached_result
            # matched_date가 없거나 lookback 상한을 넘으면 rows/기간은 나이브 값 그대로 —
            # 기존과 동일하게 빈 결과 반환(에러 아님).
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
