# dashboard_service.py 명세

## 1. 메타 정보

| 항목 | 값 |
|---|---|
| source_path | backend_fastApi/app/services/dashboard_service.py |
| source_sha256 | 24e1b541b63d90f0dd8046ee1d85c63e5c94a4b960fff62c3882aa317b8567d1 |
| source_lines | 248 |

## 2. 역할 요약

`dm_main` 마트(매일 갱신되는 단일 최신 파티션, 최근 90일치 개별 거래)를 기준으로 대시보드 6개 위젯(자치구별 평균 매매가 Top5, 가격 상승/하락 Top5, 선호지역 실거래가 추이, 선호지역 거래량 상위 법정동 Top5, 선호지역 인기 법정동, 선호지역 아파트 거래량 Top5)을 단일 JSON으로 조립하는 `get_dashboard`와 내부 헬퍼들을 정의한다.

## 3. 외부 인터페이스

| 이름 | 종류 | 시그니처 | 반환 타입 |
|---|---|---|---|
| MART_TABLE | const | `MART_TABLE = "dm_main"` | str |
| PERIOD_DAYS | const | `PERIOD_DAYS = 90` | int |
| DEFAULT_CGG_CD | const | `DEFAULT_CGG_CD = "11140"` | str |
| TOP5_LIMIT | const | `TOP5_LIMIT = 5` | int |
| MIN_TRADE_COUNT | const | `MIN_TRADE_COUNT = 3` | int |
| MAX_CHANGE_RATE_ABS | const | `MAX_CHANGE_RATE_ABS = 30.0` | float |
| TREND_BUCKET_OFFSETS | const | `TREND_BUCKET_OFFSETS: list[tuple[int, int]] = [(90, 68), (67, 46), (45, 23), (22, 0)]` | list[tuple[int, int]] |
| _period_range | function | `def _period_range(today: date) -> tuple[date, date]` | tuple[date, date] |
| _partition_glob | function | `def _partition_glob(base_date: str) -> str` | str |
| _build_seoul_top5_districts | function | `def _build_seoul_top5_districts(con, latest_base_date: str) -> list[dict[str, Any]]` | list[dict[str, Any]] |
| _build_price_change_top5 | function | `def _build_price_change_top5(con, latest_base_date: str) -> dict[str, Any]` | dict[str, Any] |
| _build_preference_price_trend | function | `def _build_preference_price_trend(con, latest_base_date: str, cgg_cd: str, today: date) -> list[dict[str, Any]]` | list[dict[str, Any]] |
| _build_top_trading_dongs | function | `def _build_top_trading_dongs(con, latest_base_date: str, cgg_cd: str) -> list[dict[str, Any]]` | list[dict[str, Any]] |
| _build_top_trading_apts | function | `def _build_top_trading_apts(con, latest_base_date: str, cgg_cd: str) -> list[dict[str, Any]]` | list[dict[str, Any]] |
| _build_preference_where_clause | function | `def _build_preference_where_clause(cgg_cd: str) -> tuple[str, dict[str, str]]` | tuple[str, dict[str, str]] |
| get_dashboard | function | `def get_dashboard(*, cgg_cd: str \| None) -> dict[str, Any]` | dict[str, Any] |

## 4. 의존성(imports)

- 표준 라이브러리:
  - `from datetime import date, timedelta`
  - `from typing import Any`
- 서드파티: 없음
- 내부 모듈:
  - `from app.core import duckdb_client`

파일 최상단 주석(6~12행, `MART_TABLE` 선언 직전): `dm_main 마트 스키마: base_date, cgg_cd, cgg_nm, stdg_cd, stdg_nm, bldg_nm, deal_date(실제 거래일), area, mno, sno, latitude, longitude, deal_cnt(거래건수), total_thing_amt(매매가 합계), total_pyeong_amt(평당가 합계). base_date=YYYY-MM-DD hive 파티션으로 저장되지만, dm_apt_price_avg와 달리 매일 갱신되는 단일 최신 파티션(현재 시점 기준 최근 90일치 개별 거래를 deal_date별로 그대로 담고 있음)만 존재한다. dm_apt_price_avg에 있던 recent_thing_amt/recent_pyeong_amt(최근 실거래가/평단가) 컬럼은 없어, 단지별로 deal_date가 가장 최신인 행의 (total_thing_amt/deal_cnt), (total_pyeong_amt/deal_cnt)를 arg_max로 구해 대체한다.`

주석(18~20행, `MIN_TRADE_COUNT`/`MAX_CHANGE_RATE_ABS` 선언 직전): `price_change_top5 신뢰도 보정 파라미터` / `MIN_TRADE_COUNT` 옆: "90일간 거래건수가 이 값 미만인 단지는 표본 부족으로 제외" / `MAX_CHANGE_RATE_ABS` 옆: "절대값이 이 범위를 벗어나는 변동률은 이상치로 제외".

주석(22~23행, `TREND_BUCKET_OFFSETS` 선언 직전): `최근 90일을 4구간으로 분할하는 (구간 시작 오프셋, 구간 종료 오프셋) 목록. 오늘로부터의 일수 차이(offset)이며, D-90~D-68 / D-67~D-46 / D-45~D-23 / D-22~D-0 순서로 오래된 구간부터 나열한다.`

## 5. 로직 상세

### MART_TABLE / PERIOD_DAYS / DEFAULT_CGG_CD / TOP5_LIMIT / MIN_TRADE_COUNT / MAX_CHANGE_RATE_ABS / TREND_BUCKET_OFFSETS

- 값은 6항 표 참조.

### _period_range

- 목적(원문 docstring): "오늘을 기준으로 최근 90일(오늘 포함) 구간의 시작일/종료일을 반환한다."
- 파라미터: `today: date`.
- 처리 흐름: `end_date = today`; `start_date = end_date - timedelta(days=PERIOD_DAYS)`; `return start_date, end_date`.
- 반환값: `(start_date, end_date)`. `end_date`는 `today`와 동일(가공 없음), `start_date`는 `today - 90일`.

### _partition_glob

- 목적: 지정 base_date 파티션의 parquet glob 경로 생성.
- 파라미터: `base_date: str`.
- 처리 흐름: `return f"{duckdb_client.mart_base_path(MART_TABLE)}/base_date={base_date}/*.parquet"`.
- 반환값: glob 경로 문자열.

### _build_seoul_top5_districts

- 목적(원문 docstring): "서울시 전체(자치구 필터 없음) 기준, 자치구별 평균 매매가 Top5. dm_main은 매일 갱신되는 단일 최신 파티션에 최근 90일치 개별 거래가 deal_date별로 담겨 있으므로, 최신 파티션 하나만 읽어 그 안에서 같은 자치구에 속한 여러 단지(bldg_nm)·거래일(deal_date)의 deal_cnt/total_thing_amt를 합산한다."
- 파라미터: `con`, `latest_base_date: str`.
- 처리 흐름:
  1. 쿼리(f-string, `{_partition_glob(latest_base_date)}`/`{TOP5_LIMIT}` 치환):
     ```python
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
     ```
  2. `rows = duckdb_client.rows_to_dicts(con.execute(query))`.
  3. `return [{"cgg_nm": r["cgg_nm"], "avg_deal_price": round(r["total_thing_amt"] / r["deal_cnt"]), "avg_pyeong_price": round(r["total_pyeong_amt"] / r["deal_cnt"])} for r in rows]`.
- 반환값: 자치구별 `{cgg_nm, avg_deal_price, avg_pyeong_price}` 리스트, 평균 매매가(=SUM(total_thing_amt)/SUM(deal_cnt)) 내림차순 상위 5개.

### _build_price_change_top5

- 목적(원문 docstring): "전체 데이터 기준, 단지(cgg_nm+stdg_nm+bldg_nm)별 최신 평당가 vs 90일 평균 평당가 변동률 상승/하락 Top5. 최신 파티션 하나만 읽어 그 안의 deal_cnt/total_pyeong_amt를 합산하고, 최근 평당가는 dm_main에 단지별로 여러 deal_date(실제 거래일) 행이 있으므로 그중 deal_date가 가장 최신인 행의 (total_pyeong_amt/deal_cnt)를 arg_max로 구해 사용한다. 동명 단지가 다른 지역에 있을 수 있어 (cgg_nm, stdg_nm, bldg_nm) 복합 키로 묶고, 표본이 적은(deal_cnt < MIN_TRADE_COUNT) 단지와 이상치(|change_rate| > MAX_CHANGE_RATE_ABS)를 제외한 뒤, 거래량이 많은 대단지에 우선순위를 주는 가중치 스코어(change_rate * ln(1 + deal_cnt))로 정렬한다."
- 파라미터: `con`, `latest_base_date: str`.
- 처리 흐름:
  1. `filtered_cte`(f-string, `{_partition_glob(latest_base_date)}`/`{MIN_TRADE_COUNT}` 치환)를 다음과 같이 조립:
     ```python
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
     ```
  2. `rising_top5 = duckdb_client.rows_to_dicts(con.execute(f"{filtered_cte} SELECT bldg_nm, ROUND(change_rate, 2) AS change_rate FROM filtered ORDER BY score DESC LIMIT {TOP5_LIMIT}"))`.
  3. `falling_top5 = duckdb_client.rows_to_dicts(con.execute(f"{filtered_cte} SELECT bldg_nm, ROUND(change_rate, 2) AS change_rate FROM filtered ORDER BY score ASC LIMIT {TOP5_LIMIT}"))`.
  4. `return {"rising_top5": rising_top5, "falling_top5": falling_top5}`.
- 반환값: `{"rising_top5": [...], "falling_top5": [...]}`. 각 항목은 `{bldg_nm, change_rate}`(소수 둘째 자리 반올림).

### _build_preference_price_trend

- 목적(원문 docstring): "선호 자치구(cgg_cd) 기준, 최근 90일을 4개 구간으로 나눈 구간별 평균 거래가/평단가/거래량 추이. 최신 파티션 하나만 읽고(base_date 자체로는 구간을 나눌 수 없음 — dm_main은 파티션이 갱신 시점 기준 단일 스냅샷 하나뿐), 그 안의 실제 거래일(deal_date)을 기준으로 4구간을 나눈다."
- 파라미터: `con`, `latest_base_date: str`, `cgg_cd: str`, `today: date`.
- 처리 흐름:
  1. `partition_glob = _partition_glob(latest_base_date)`; `trend: list[dict[str, Any]] = []`.
  2. `TREND_BUCKET_OFFSETS`의 각 `(start_offset, end_offset)`에 대해:
     a. `bucket_start = today - timedelta(days=start_offset)`; `bucket_end = today - timedelta(days=end_offset)`.
     b. 쿼리(f-string, `{partition_glob}` 치환):
        ```python
        query = f"""
            SELECT
                COALESCE(SUM(deal_cnt), 0) AS deal_cnt,
                COALESCE(SUM(total_thing_amt), 0) AS total_thing_amt,
                COALESCE(SUM(total_pyeong_amt), 0) AS total_pyeong_amt
            FROM read_parquet('{partition_glob}', hive_partitioning = true)
            WHERE cgg_cd = $cgg_cd AND deal_date BETWEEN $bucket_start AND $bucket_end
        """
        ```
     c. `deal_cnt, total_thing_amt, total_pyeong_amt = con.execute(query, {"cgg_cd": cgg_cd, "bucket_start": bucket_start, "bucket_end": bucket_end}).fetchone()`.
     d. `trend.append({"period_label": f"D-{start_offset}~D-{end_offset}", "start_date": bucket_start, "end_date": bucket_end, "avg_deal_price": round(total_thing_amt / deal_cnt) if deal_cnt else 0, "avg_pyeong_price": round(total_pyeong_amt / deal_cnt) if deal_cnt else 0, "deal_cnt": deal_cnt})`.
  3. `return trend`.
- 반환값: `TREND_BUCKET_OFFSETS` 순서(오래된 구간→최신 구간)대로 4개 항목의 리스트. 거래가 없는 구간은 `avg_deal_price`/`avg_pyeong_price`가 `0`, `deal_cnt`는 `COALESCE`로 `0`.

### _build_top_trading_dongs

- 목적(원문 docstring): "선호 자치구(cgg_cd) 내 법정동별 거래량 Top5. 최신 파티션 하나만 읽어, 그 안에서 같은 법정동에 속한 여러 단지(bldg_nm)·거래일(deal_date)의 deal_cnt를 합산한다."
- 파라미터: `con`, `latest_base_date: str`, `cgg_cd: str`.
- 처리 흐름:
  1. 쿼리(f-string, `{_partition_glob(latest_base_date)}`/`{TOP5_LIMIT}` 치환):
     ```python
     query = f"""
         SELECT
             any_value(cgg_nm) AS cgg_nm,
             stdg_nm,
             SUM(deal_cnt) AS deal_cnt
         FROM read_parquet('{_partition_glob(latest_base_date)}', hive_partitioning = true)
         WHERE cgg_cd = $cgg_cd
         GROUP BY stdg_nm
         HAVING SUM(deal_cnt) > 0
         ORDER BY deal_cnt DESC
         LIMIT {TOP5_LIMIT}
     """
     ```
  2. `return duckdb_client.rows_to_dicts(con.execute(query, {"cgg_cd": cgg_cd}))`.
- 반환값: `{cgg_nm, stdg_nm, deal_cnt}` 리스트, 거래량(SUM(deal_cnt)) 내림차순 상위 5개.

### _build_top_trading_apts

- 목적(원문 docstring): "선호 자치구(cgg_cd) 내 아파트(stdg_cd+bldg_nm)별 거래량 Top5. dm_main의 최신 파티션 하나만 읽어(단지별로 deal_date마다 여러 행이 있을 수 있음) deal_cnt를 합산한다. 최근 매매가는 recent_thing_amt 컬럼이 없어, deal_date가 가장 최신인 행의 (total_thing_amt/deal_cnt)를 arg_max로 구해 반올림한 값을 사용한다. bldg_nm만으로 묶으면 같은 자치구 안의 다른 법정동에 있는 동명 단지(예: '래미안', '자이' 등 흔한 이름)가 하나로 합쳐지므로 stdg_cd를 함께 그룹 키로 사용한다."
- 파라미터: `con`, `latest_base_date: str`, `cgg_cd: str`.
- 처리 흐름:
  1. 쿼리(f-string, `{_partition_glob(latest_base_date)}`/`{TOP5_LIMIT}` 치환):
     ```python
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
     ```
  2. `return duckdb_client.rows_to_dicts(con.execute(query, {"cgg_cd": cgg_cd}))`.
- 반환값: `{bldg_nm, deal_cnt, recent_thing_amt}` 리스트, 거래량 내림차순 상위 5개.

### _build_preference_where_clause

- 목적(원문 docstring): "선호지역 필터 3개 위젯(가격 추이/거래량 상위 법정동/거래량 상위 아파트)이 공통으로 쓰는 cgg_cd 조건. resolve_base_date_for_filter로 이 지역에 실제 매칭 데이터가 있는 base_date를 찾을 때 재사용한다."
- 파라미터: `cgg_cd: str`.
- 처리 흐름: `return "WHERE cgg_cd = $cgg_cd", {"cgg_cd": cgg_cd}`.
- 반환값: 고정 형태의 `WHERE` 절과 파라미터(분기 없음).

### get_dashboard

- 목적(원문 docstring): "dm_main 마트(최근 90일)를 기준으로 대시보드 6개 위젯을 단일 JSON으로 반환한다. cgg_cd가 없거나 빈 값이면 '서울시 중구'(11140)로 대체한다. 6개 위젯 중 필터가 없는 2개(seoul_top5_districts/price_change_top5)는 latest_base_date(파티션 존재 여부 폴백)를 그대로 쓰고, resolved_cgg_cd로 필터링하는 3개(preference_price_trend/preference_top_trading_dongs/preference_top_trading_apts)만 그 지역 조건 기준으로 별도 폴백한 preference_base_date를 사용한다 — 최신 파티션엔 그 지역 데이터가 없어도 과거 파티션엔 있을 수 있기 때문이다(compare 계열 비교형 API와 동일한 "위젯 그룹별로 다른 base_date를 가질 수 있다"는 원리)."
- 파라미터: `cgg_cd: str | None`(키워드 전용).
- 처리 흐름:
  1. `resolved_cgg_cd = cgg_cd.strip() if cgg_cd and cgg_cd.strip() else DEFAULT_CGG_CD`.
  2. `today = date.today()`; `start_date, end_date = _period_range(today)`.
  3. `con = duckdb_client.get_connection()`.
  4. `try:` 블록:
     a. `latest_base_date = duckdb_client.resolve_base_date(con, MART_TABLE)`.
     b. `preference_where, preference_params = _build_preference_where_clause(resolved_cgg_cd)`.
     c. `preference_base_date = duckdb_client.resolve_base_date_for_filter(con, MART_TABLE, preference_where, preference_params) or latest_base_date`.
     d. `seoul_top5_districts = _build_seoul_top5_districts(con, latest_base_date)`.
     e. `price_change_top5 = _build_price_change_top5(con, latest_base_date)`.
     f. `preference_price_trend = _build_preference_price_trend(con, preference_base_date, resolved_cgg_cd, today)`.
     g. `preference_top_trading_dongs = _build_top_trading_dongs(con, preference_base_date, resolved_cgg_cd)`.
     h. `preference_top_trading_apts = _build_top_trading_apts(con, preference_base_date, resolved_cgg_cd)`.
  5. `finally: con.close()`.
  6. `preference_popular_dong = ({"cgg_nm": preference_top_trading_dongs[0]["cgg_nm"], "stdg_nm": preference_top_trading_dongs[0]["stdg_nm"]} if preference_top_trading_dongs else None)`.
  7. `return {...}` (아래 9개 키).
- 반환값: 딕셔너리 `{"cgg_cd": resolved_cgg_cd, "period_start": start_date, "period_end": end_date, "preference_base_date": preference_base_date, "seoul_top5_districts": seoul_top5_districts, "price_change_top5": price_change_top5, "preference_price_trend": preference_price_trend, "preference_top_trading_dongs": preference_top_trading_dongs, "preference_popular_dong": preference_popular_dong, "preference_top_trading_apts": preference_top_trading_apts}`. `preference_popular_dong`은 `preference_top_trading_dongs`가 비어있으면 `None`.

## 6. 모듈 레벨 상수/설정값

| 이름 | 값 |
|---|---|
| MART_TABLE | `"dm_main"` |
| PERIOD_DAYS | `90` |
| DEFAULT_CGG_CD | `"11140"` |
| TOP5_LIMIT | `5` |
| MIN_TRADE_COUNT | `3` |
| MAX_CHANGE_RATE_ABS | `30.0` |
| TREND_BUCKET_OFFSETS | `[(90, 68), (67, 46), (45, 23), (22, 0)]` |

## 7. 역참조(이 파일을 사용하는 곳)

- `app/api/v1/endpoints/dashboard.py` — `from app.services import dashboard_service` 후 `dashboard_service.get_dashboard(...)` 호출.

## 8. 재생성 지침

> 위 내용을 근거로 `backend_fastApi/app/services/dashboard_service.py` 파일을 동일한 로직으로 재작성하라. 여기 명시되지 않은 세부 구현(변수명 스타일, 코드 포맷 등)은 기존 프로젝트 컨벤션(PEP 8, 저장소 내 동일 계층 파일들의 스타일)을 따른다.
