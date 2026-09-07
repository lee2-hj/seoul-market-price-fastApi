from datetime import date, timedelta
from typing import Any

from app.core import duckdb_client
from app.services import apt_recent_rank_service

# dm_main 마트 스키마: base_date, cgg_cd, cgg_nm, stdg_cd, stdg_nm, bldg_nm, deal_date(실제 거래일),
# area, mno, sno, latitude, longitude, deal_cnt(거래건수), total_thing_amt(매매가 합계),
# total_pyeong_amt(평당가 합계). base_date=YYYY-MM-DD hive 파티션으로 저장되지만, dm_apt_price_avg와 달리
# 매일 갱신되는 단일 최신 파티션(현재 시점 기준 최근 90일치 개별 거래를 deal_date별로 그대로 담고 있음)만
# 존재한다. dm_apt_price_avg에 있던 recent_thing_amt/recent_pyeong_amt(최근 실거래가/평단가) 컬럼은 없어,
# 단지별로 deal_date가 가장 최신인 행의 (total_thing_amt/deal_cnt), (total_pyeong_amt/deal_cnt)를
# arg_max로 구해 대체한다.
MART_TABLE = "dm_main"
PERIOD_DAYS = 90
DEFAULT_CGG_CD = "11140"  # 서울시 중구
TOP5_LIMIT = 5

# price_change_top5 신뢰도 보정 파라미터
MIN_TRADE_COUNT = 3  # 90일간 거래건수가 이 값 미만인 단지는 표본 부족으로 제외
MAX_CHANGE_RATE_ABS = 30.0  # 절대값이 이 범위를 벗어나는 변동률은 이상치로 제외

# 최근 90일을 4구간으로 분할하는 (구간 시작 오프셋, 구간 종료 오프셋) 목록. 오늘로부터의 일수 차이(offset)이며,
# D-90~D-68 / D-67~D-46 / D-45~D-23 / D-22~D-0 순서로 오래된 구간부터 나열한다.
TREND_BUCKET_OFFSETS: list[tuple[int, int]] = [(90, 68), (67, 46), (45, 23), (22, 0)]


def _period_range(today: date) -> tuple[date, date]:
    """오늘을 기준으로 최근 90일(오늘 포함) 구간의 시작일/종료일을 반환한다."""
    end_date = today
    start_date = end_date - timedelta(days=PERIOD_DAYS)
    return start_date, end_date


def _partition_glob(base_date: str) -> str:
    return f"{duckdb_client.mart_base_path(MART_TABLE)}/base_date={base_date}/*.parquet"


def _build_seoul_top5_districts(con, latest_base_date: str) -> list[dict[str, Any]]:
    """서울시 전체(자치구 필터 없음) 기준, 자치구별 평균 매매가 Top5. dm_main은 매일 갱신되는 단일 최신
    파티션에 최근 90일치 개별 거래가 deal_date별로 담겨 있으므로, 최신 파티션 하나만 읽어 그 안에서 같은
    자치구에 속한 여러 단지(bldg_nm)·거래일(deal_date)의 deal_cnt/total_thing_amt를 합산한다."""
    query = f"""
        SELECT
            cgg_nm,
            SUM(deal_cnt) AS deal_cnt,
            SUM(total_thing_amt) AS total_thing_amt,
            SUM(total_pyeong_amt) AS total_pyeong_amt
        FROM read_parquet('{_partition_glob(latest_base_date)}', hive_partitioning = true)
        GROUP BY cgg_nm
        HAVING SUM(deal_cnt) > 0
        ORDER BY SUM(total_thing_amt)::DOUBLE / SUM(deal_cnt) DESC
        LIMIT {TOP5_LIMIT}
    """
    rows = duckdb_client.rows_to_dicts(con.execute(query))
    return [
        {
            "cgg_nm": r["cgg_nm"],
            "avg_deal_price": round(r["total_thing_amt"] / r["deal_cnt"]),
            "avg_pyeong_price": round(r["total_pyeong_amt"] / r["deal_cnt"]),
        }
        for r in rows
    ]


def _build_price_change_top5(con, latest_base_date: str) -> dict[str, Any]:
    """전체 데이터 기준, 단지(cgg_nm+stdg_nm+bldg_nm)별 최신 평당가 vs 90일 평균 평당가 변동률 상승/하락 Top5.
    최신 파티션 하나만 읽어 그 안의 deal_cnt/total_pyeong_amt를 합산하고, 최근 평당가는 dm_main에 단지별로
    여러 deal_date(실제 거래일) 행이 있으므로 그중 deal_date가 가장 최신인 행의
    (total_pyeong_amt/deal_cnt)를 arg_max로 구해 사용한다. 동명 단지가 다른 지역에 있을 수 있어
    (cgg_nm, stdg_nm, bldg_nm) 복합 키로 묶고, 표본이 적은(deal_cnt < MIN_TRADE_COUNT) 단지와 이상치
    (|change_rate| > MAX_CHANGE_RATE_ABS)를 제외한 뒤, 거래량이 많은 대단지에 우선순위를 주는 가중치
    스코어(change_rate * ln(1 + deal_cnt))로 정렬한다."""
    filtered_cte = f"""
        WITH agg AS (
            SELECT
                cgg_nm,
                stdg_nm,
                bldg_nm,
                SUM(deal_cnt) AS deal_cnt,
                SUM(total_pyeong_amt) AS total_pyeong_amt,
                arg_max(total_pyeong_amt::DOUBLE / deal_cnt, deal_date) AS recent_pyeong_amt
            FROM read_parquet('{_partition_glob(latest_base_date)}', hive_partitioning = true)
            GROUP BY cgg_nm, stdg_nm, bldg_nm
            HAVING SUM(deal_cnt) >= {MIN_TRADE_COUNT} AND SUM(total_pyeong_amt) > 0
        ),
        rated AS (
            SELECT
                bldg_nm,
                deal_cnt,
                (recent_pyeong_amt - total_pyeong_amt::DOUBLE / deal_cnt)
                    / (total_pyeong_amt::DOUBLE / deal_cnt) * 100 AS change_rate
            FROM agg
        ),
        filtered AS (
            SELECT
                bldg_nm,
                change_rate,
                change_rate * ln(1 + deal_cnt) AS score
            FROM rated
            WHERE ABS(change_rate) <= {MAX_CHANGE_RATE_ABS}
        )
    """
    rising_top5 = duckdb_client.rows_to_dicts(
        con.execute(
            f"{filtered_cte} SELECT bldg_nm, ROUND(change_rate, 2) AS change_rate "
            f"FROM filtered ORDER BY score DESC LIMIT {TOP5_LIMIT}"
        )
    )
    falling_top5 = duckdb_client.rows_to_dicts(
        con.execute(
            f"{filtered_cte} SELECT bldg_nm, ROUND(change_rate, 2) AS change_rate "
            f"FROM filtered ORDER BY score ASC LIMIT {TOP5_LIMIT}"
        )
    )
    return {"rising_top5": rising_top5, "falling_top5": falling_top5}


def _build_preference_price_trend(
    con, latest_base_date: str, cgg_cd: str, today: date
) -> list[dict[str, Any]]:
    """선호 자치구(cgg_cd) 기준, 최근 90일을 4개 구간으로 나눈 구간별 평균 거래가/평단가/거래량 추이.
    최신 파티션 하나만 읽고(base_date 자체로는 구간을 나눌 수 없음 — dm_main은 파티션이 갱신 시점 기준
    단일 스냅샷 하나뿐), 그 안의 실제 거래일(deal_date)을 기준으로 4구간을 나눈다."""
    partition_glob = _partition_glob(latest_base_date)
    trend: list[dict[str, Any]] = []
    for start_offset, end_offset in TREND_BUCKET_OFFSETS:
        bucket_start = today - timedelta(days=start_offset)
        bucket_end = today - timedelta(days=end_offset)
        query = f"""
            SELECT
                COALESCE(SUM(deal_cnt), 0) AS deal_cnt,
                COALESCE(SUM(total_thing_amt), 0) AS total_thing_amt,
                COALESCE(SUM(total_pyeong_amt), 0) AS total_pyeong_amt
            FROM read_parquet('{partition_glob}', hive_partitioning = true)
            WHERE cgg_cd = $cgg_cd AND deal_date BETWEEN $bucket_start AND $bucket_end
        """
        deal_cnt, total_thing_amt, total_pyeong_amt = con.execute(
            query, {"cgg_cd": cgg_cd, "bucket_start": bucket_start, "bucket_end": bucket_end}
        ).fetchone()
        trend.append(
            {
                "period_label": f"D-{start_offset}~D-{end_offset}",
                "start_date": bucket_start,
                "end_date": bucket_end,
                "avg_deal_price": round(total_thing_amt / deal_cnt) if deal_cnt else 0,
                "avg_pyeong_price": round(total_pyeong_amt / deal_cnt) if deal_cnt else 0,
                "deal_cnt": deal_cnt,
            }
        )
    return trend


def _build_top_trading_dongs(con, latest_base_date: str, cgg_cd: str) -> list[dict[str, Any]]:
    """선호 자치구(cgg_cd) 내 법정동별 거래량 Top5. 최신 파티션 하나만 읽어, 그 안에서 같은 법정동에 속한
    여러 단지(bldg_nm)·거래일(deal_date)의 deal_cnt를 합산한다."""
    query = f"""
        SELECT
            any_value(cgg_nm) AS cgg_nm,
            stdg_cd,
            stdg_nm,
            SUM(deal_cnt) AS deal_cnt
        FROM read_parquet('{_partition_glob(latest_base_date)}', hive_partitioning = true)
        WHERE cgg_cd = $cgg_cd
        GROUP BY stdg_cd, stdg_nm
        HAVING SUM(deal_cnt) > 0
        ORDER BY deal_cnt DESC
        LIMIT {TOP5_LIMIT}
    """
    return duckdb_client.rows_to_dicts(con.execute(query, {"cgg_cd": cgg_cd}))


def _build_top_trading_apts(con, latest_base_date: str, cgg_cd: str) -> list[dict[str, Any]]:
    """선호 자치구(cgg_cd) 내 아파트(stdg_cd+bldg_nm)별 거래량 Top5. dm_main의 최신 파티션 하나만 읽어(단지별로
    deal_date마다 여러 행이 있을 수 있음) deal_cnt를 합산한다. 최근 매매가는 recent_thing_amt 컬럼이 없어,
    deal_date가 가장 최신인 행의 (total_thing_amt/deal_cnt)를 arg_max로 구해 반올림한 값을 사용한다.
    bldg_nm만으로 묶으면 같은 자치구 안의 다른 법정동에 있는 동명 단지(예: '래미안', '자이' 등 흔한 이름)가
    하나로 합쳐지므로 stdg_cd를 함께 그룹 키로 사용한다."""
    query = f"""
        SELECT
            bldg_nm,
            SUM(deal_cnt) AS deal_cnt,
            ROUND(arg_max(total_thing_amt::DOUBLE / deal_cnt, deal_date)) AS recent_thing_amt
        FROM read_parquet('{_partition_glob(latest_base_date)}', hive_partitioning = true)
        WHERE cgg_cd = $cgg_cd
        GROUP BY stdg_cd, bldg_nm
        HAVING SUM(deal_cnt) > 0
        ORDER BY deal_cnt DESC
        LIMIT {TOP5_LIMIT}
    """
    return duckdb_client.rows_to_dicts(con.execute(query, {"cgg_cd": cgg_cd}))


def _build_preference_where_clause(cgg_cd: str) -> tuple[str, dict[str, str]]:
    """선호지역 필터 3개 위젯(가격 추이/거래량 상위 법정동/거래량 상위 아파트)이 공통으로 쓰는
    cgg_cd 조건. resolve_base_date_for_filter로 이 지역에 실제 매칭 데이터가 있는 base_date를
    찾을 때 재사용한다."""
    return "WHERE cgg_cd = $cgg_cd", {"cgg_cd": cgg_cd}


def get_dashboard(*, cgg_cd: str | None) -> dict[str, Any]:
    """dm_main 마트(최근 90일)를 기준으로 대시보드 6개 위젯을 단일 JSON으로 반환한다.
    cgg_cd가 없거나 빈 값이면 '서울시 중구'(11140)로 대체한다. 6개 위젯 중 필터가 없는 2개
    (seoul_top5_districts/price_change_top5)는 latest_base_date(파티션 존재 여부 폴백)를 그대로
    쓰고, resolved_cgg_cd로 필터링하는 3개(preference_price_trend/preference_top_trading_dongs/
    preference_top_trading_apts)만 그 지역 조건 기준으로 별도 폴백한 preference_base_date를
    사용한다 — 최신 파티션엔 그 지역 데이터가 없어도 과거 파티션엔 있을 수 있기 때문이다(compare
    계열 비교형 API와 동일한 "위젯 그룹별로 다른 base_date를 가질 수 있다"는 원리).

    추가로 apt_recent_rank_service.get_apt_recent_rank()를 별도 엔드포인트로 노출하지 않고 그대로
    호출해, resolved_cgg_cd(=sgg_cd)와 preference_popular_dong.stdg_cd(=dong_cd, 이 대시보드에서
    방금 계산한 가장 인기있는 법정동)를 이용한 법정동 내 최근 90일 개별 실거래 Top5/Bottom5 전체
    응답을 apt_recent_rank 키에 그대로 담아 함께 반환한다. 인기 법정동 자체가 없으면(선호지역에
    거래 데이터가 없음) apt_recent_rank는 null이다."""
    resolved_cgg_cd = cgg_cd.strip() if cgg_cd and cgg_cd.strip() else DEFAULT_CGG_CD
    today = date.today()
    start_date, end_date = _period_range(today)

    con = duckdb_client.get_connection()
    try:
        latest_base_date = duckdb_client.resolve_base_date(con, MART_TABLE)

        preference_where, preference_params = _build_preference_where_clause(resolved_cgg_cd)
        preference_base_date = duckdb_client.resolve_base_date_for_filter(
            con, MART_TABLE, preference_where, preference_params
        ) or latest_base_date

        seoul_top5_districts = _build_seoul_top5_districts(con, latest_base_date)
        price_change_top5 = _build_price_change_top5(con, latest_base_date)
        preference_price_trend = _build_preference_price_trend(con, preference_base_date, resolved_cgg_cd, today)
        preference_top_trading_dongs = _build_top_trading_dongs(con, preference_base_date, resolved_cgg_cd)
        preference_top_trading_apts = _build_top_trading_apts(con, preference_base_date, resolved_cgg_cd)
    finally:
        con.close()

    preference_popular_dong = (
        {
            "cgg_nm": preference_top_trading_dongs[0]["cgg_nm"],
            "stdg_cd": preference_top_trading_dongs[0]["stdg_cd"],
            "stdg_nm": preference_top_trading_dongs[0]["stdg_nm"],
        }
        if preference_top_trading_dongs
        else None
    )

    # apt-recent-rank(법정동 내 최근 90일 개별 실거래 Top5/Bottom5)를 별도 엔드포인트로 노출하지
    # 않고, 대시보드의 파라미터(resolved_cgg_cd)와 방금 계산한 "가장 인기있는 법정동"
    # (preference_popular_dong.stdg_cd)을 그대로 이용해 조회한 뒤 전체 리턴값을 그대로 함께
    # 내려준다. 인기 법정동 자체가 없으면(=선호지역에 거래 데이터가 없음) 조회할 법정동이 없으므로
    # None을 반환한다.
    apt_recent_rank = (
        apt_recent_rank_service.get_apt_recent_rank(
            sgg_cd=resolved_cgg_cd, dong_cd=preference_popular_dong["stdg_cd"]
        )
        if preference_popular_dong
        else None
    )

    return {
        "cgg_cd": resolved_cgg_cd,
        "period_start": start_date,
        "period_end": end_date,
        "preference_base_date": preference_base_date,
        "seoul_top5_districts": seoul_top5_districts,
        "price_change_top5": price_change_top5,
        "preference_price_trend": preference_price_trend,
        "preference_top_trading_dongs": preference_top_trading_dongs,
        "preference_popular_dong": preference_popular_dong,
        "preference_top_trading_apts": preference_top_trading_apts,
        "apt_recent_rank": apt_recent_rank,
    }
