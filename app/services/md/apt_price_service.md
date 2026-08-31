# apt_price_service.py 명세

## 1. 메타 정보

| 항목 | 값 |
|---|---|
| source_path | backend_fastApi/app/services/apt_price_service.py |
| source_sha256 | e3be343f21ac29aba39f5abff622d35a5822ce8afd239e468a204a8f60b2f5ae |
| source_lines | 140 |

## 2. 역할 요약

`dm_apt_price_avg` 마트에서 지역 조건(선택) 내 아파트별 metric_type 기준(평균 평당가/평균 거래가) 상위/하위 5개와 전체 집계(총 거래건수/평균 거래금액/평균 평당가)를 조회하는 `get_top_bottom` 함수와 내부 헬퍼들을 정의한다.

## 3. 외부 인터페이스

| 이름 | 종류 | 시그니처 | 반환 타입 |
|---|---|---|---|
| MART_TABLE | const | `MART_TABLE = "dm_apt_price_avg"` | str |
| TOP_BOTTOM_LIMIT | const | `TOP_BOTTOM_LIMIT = 5` | int |
| _build_where_clause | function | `def _build_where_clause(region_cgg_cd: str \| None, region_stdg_cd: str \| None) -> tuple[str, dict[str, str]]` | tuple[str, dict[str, str]] |
| _metric_column | function | `def _metric_column(metric_type: str) -> str` | str |
| _fetch_ranked | function | `def _fetch_ranked(con, base_date: str, region_cgg_cd: str \| None, region_stdg_cd: str \| None, metric_type: str, order: str, exclude_items: list[dict[str, Any]] \| None = None) -> list[dict[str, Any]]` | list[dict[str, Any]] |
| _count_rows | function | `def _count_rows(con, base_date: str, region_cgg_cd: str \| None, region_stdg_cd: str \| None) -> int` | int |
| _fetch_summary | function | `def _fetch_summary(con, base_date: str, region_cgg_cd: str \| None, region_stdg_cd: str \| None) -> tuple[int, int, int]` | tuple[int, int, int] |
| get_top_bottom | function | `def get_top_bottom(*, region_cgg_cd: str \| None, region_stdg_cd: str \| None, metric_type: str) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]], int, int, int]` | tuple[str, list[dict[str, Any]], list[dict[str, Any]], int, int, int] |

## 4. 의존성(imports)

- 표준 라이브러리:
  - `from typing import Any`
- 서드파티: 없음
- 내부 모듈:
  - `from app.core import duckdb_client`

## 5. 로직 상세

### MART_TABLE

- 값: `"dm_apt_price_avg"`.

### TOP_BOTTOM_LIMIT

- 값: `5`.

### _build_where_clause

- 목적(원문 docstring): "평당가/매매가가 유효한(0 초과) row만 대상으로 하고, 주어진 지역 조건을 동적으로 추가한다."
- 파라미터: `region_cgg_cd: str | None`, `region_stdg_cd: str | None`.
- 처리 흐름:
  1. `conditions = ["deal_cnt > 0", "total_pyeong_amt > 0", "total_thing_amt > 0"]`; `params: dict[str, str] = {}`.
  2. `if region_cgg_cd: conditions.append("cgg_cd = $cgg_cd"); params["cgg_cd"] = region_cgg_cd`.
  3. `if region_stdg_cd: conditions.append("stdg_cd = $stdg_cd"); params["stdg_cd"] = region_stdg_cd`.
  4. `return "WHERE " + " AND ".join(conditions), params`.
- 반환값: 항상 최소 3개 조건(`deal_cnt > 0`, `total_pyeong_amt > 0`, `total_thing_amt > 0`)을 포함하는 `WHERE` 절과 파라미터.

### _metric_column

- 목적(원문 docstring): "metric_type에 대응하는 정렬 기준 컬럼명을 반환한다."
- 파라미터: `metric_type: str`.
- 처리 흐름: `return "avg_pyeong_amt" if metric_type == "pyeong" else "avg_thing_amt"`.
- 반환값: `metric_type == "pyeong"`이면 `"avg_pyeong_amt"`, 그 외(예: `"thing_amt"`)는 `"avg_thing_amt"`.

### _fetch_ranked

- 목적(원문 docstring): "아파트별 평균 거래가/평균 평당가(각 total_*_amt / deal_cnt, 반올림)를 계산하고 metric_type 기준 컬럼으로 정렬하여 상위/하위 row를 추출한다. exclude_items가 주어지면 (cgg_cd, stdg_cd, bldg_nm) 키가 일치하는 row는 결과에서 제외한다(top/bottom 중복 방지)."
- 파라미터: `con`, `base_date: str`, `region_cgg_cd: str | None`, `region_stdg_cd: str | None`, `metric_type: str`, `order: str`, `exclude_items: list[dict[str, Any]] | None = None`.
- 처리 흐름:
  1. `parquet_glob = f"{duckdb_client.mart_base_path(MART_TABLE)}/base_date={base_date}/*.parquet"`.
  2. `where_clause, params = _build_where_clause(region_cgg_cd, region_stdg_cd)`.
  3. `metric_column = _metric_column(metric_type)`.
  4. `exclude_clause = ""`. `if exclude_items:` 이면:
     a. `tuples = []`.
     b. `exclude_items`를 `enumerate`하며 각 `(i, item)`에 대해 `tuples.append(f"($cgg_cd_ex{i}, $stdg_cd_ex{i}, $bldg_nm_ex{i})")`; `params[f"cgg_cd_ex{i}"] = item["cgg_cd"]`; `params[f"stdg_cd_ex{i}"] = item["stdg_cd"]`; `params[f"bldg_nm_ex{i}"] = item["bldg_nm"]`.
     c. `exclude_clause = f" AND (cgg_cd, stdg_cd, bldg_nm) NOT IN ({', '.join(tuples)})"`.
  5. 쿼리(f-string, `{where_clause}`/`{exclude_clause}`/`{metric_column}`/`{order}`/`{TOP_BOTTOM_LIMIT}` 치환):
     ```python
     query = f"""
         SELECT
             * EXCLUDE (total_thing_amt, total_pyeong_amt),
             CAST(ROUND(total_thing_amt::DOUBLE / deal_cnt) AS BIGINT) AS avg_thing_amt,
             CAST(ROUND(total_pyeong_amt::DOUBLE / deal_cnt) AS BIGINT) AS avg_pyeong_amt
         FROM read_parquet('{parquet_glob}', hive_partitioning = true)
         {where_clause}
         {exclude_clause}
         ORDER BY {metric_column} {order}
         LIMIT {TOP_BOTTOM_LIMIT}
     """
     ```
  6. `result = con.execute(query, params)`; `return duckdb_client.rows_to_dicts(result)`.
- 반환값: 조건에 맞고 exclude 조건에 걸리지 않는 row 중 `metric_column`을 `order` 방향으로 정렬한 상위 `TOP_BOTTOM_LIMIT`(5)개.

### _count_rows

- 목적(원문 docstring): "지정된 지역 조건에 해당하는 아파트(row) 개수를 센다."
- 파라미터: `con`, `base_date: str`, `region_cgg_cd: str | None`, `region_stdg_cd: str | None`.
- 처리 흐름:
  1. `parquet_glob = f"{duckdb_client.mart_base_path(MART_TABLE)}/base_date={base_date}/*.parquet"`.
  2. `where_clause, params = _build_where_clause(region_cgg_cd, region_stdg_cd)`.
  3. 쿼리(f-string):
     ```python
     query = f"""
         SELECT COUNT(*)
         FROM read_parquet('{parquet_glob}', hive_partitioning = true)
         {where_clause}
     """
     ```
  4. `(row_count,) = con.execute(query, params).fetchone()`.
  5. `return row_count or 0`.
- 반환값: 조건에 맞는 row 개수(정수, 0 이상).

### _fetch_summary

- 목적(원문 docstring): "지정된 지역 조건에 해당하는 전체 거래건수와 평균 거래금액/평균 평당가(반올림)를 집계한다."
- 파라미터: `con`, `base_date: str`, `region_cgg_cd: str | None`, `region_stdg_cd: str | None`.
- 처리 흐름:
  1. `parquet_glob = f"{duckdb_client.mart_base_path(MART_TABLE)}/base_date={base_date}/*.parquet"`.
  2. `where_clause, params = _build_where_clause(region_cgg_cd, region_stdg_cd)`.
  3. 쿼리(f-string):
     ```python
     query = f"""
         SELECT
             SUM(deal_cnt) AS total_count,
             SUM(total_thing_amt) AS sum_thing_amt,
             SUM(total_pyeong_amt) AS sum_pyeong_amt
         FROM read_parquet('{parquet_glob}', hive_partitioning = true)
         {where_clause}
     """
     ```
  4. `total_count, sum_thing_amt, sum_pyeong_amt = con.execute(query, params).fetchone()`.
  5. `total_count = total_count or 0`.
  6. `avg_thing_amt = round(sum_thing_amt / total_count) if total_count else 0`.
  7. `avg_pyeong_amt = round(sum_pyeong_amt / total_count) if total_count else 0`.
  8. `return total_count, avg_thing_amt, avg_pyeong_amt`.
- 반환값: `(total_count, avg_thing_amt, avg_pyeong_amt)` 3튜플.

### get_top_bottom

- 목적(원문 docstring): "지정된(선택적) 지역 조건 내 아파트별 metric_type 기준(평균 평당가 또는 평균 거래가) 상위/하위 5개와 전체 집계(총 거래건수/평균 거래금액/평균 평당가)를 MinIO Parquet에서 동적으로 조회한다. base_date는 최신 파티션만 보는 것이 아니라, 조건에 맞는 데이터가 있는 가장 최근 base_date까지 소급 조회한다."
- 파라미터(모두 키워드 전용): `region_cgg_cd: str | None`, `region_stdg_cd: str | None`, `metric_type: str`.
- 처리 흐름:
  1. `con = duckdb_client.get_connection()`.
  2. `try:` 블록:
     a. `where_clause, where_params = _build_where_clause(region_cgg_cd, region_stdg_cd)`.
     b. `base_date = duckdb_client.resolve_base_date_for_filter(con, MART_TABLE, where_clause, where_params) or duckdb_client.resolve_base_date(con, MART_TABLE)`.
     c. `row_count = _count_rows(con, base_date, region_cgg_cd, region_stdg_cd)`.
     d. `top_items = _fetch_ranked(con, base_date, region_cgg_cd, region_stdg_cd, metric_type, "DESC")`.
     e. `bottom_items = (_fetch_ranked(con, base_date, region_cgg_cd, region_stdg_cd, metric_type, "ASC", exclude_items=top_items) if row_count > TOP_BOTTOM_LIMIT else [])`.
     f. `total_count, avg_thing_amt, avg_pyeong_amt = _fetch_summary(con, base_date, region_cgg_cd, region_stdg_cd)`.
  3. `finally: con.close()`.
  4. `return base_date, top_items, bottom_items, total_count, avg_thing_amt, avg_pyeong_amt`.
- 반환값: 6-튜플 `(base_date, top_items, bottom_items, total_count, avg_thing_amt, avg_pyeong_amt)`. 전체 row 수가 `TOP_BOTTOM_LIMIT`(5) 이하이면 `bottom_items`는 `top_items`와의 중복을 피하기 위해 아예 빈 리스트(`[]`)로 반환됨(추가 쿼리 없음).

## 6. 모듈 레벨 상수/설정값

| 이름 | 값 |
|---|---|
| MART_TABLE | `"dm_apt_price_avg"` |
| TOP_BOTTOM_LIMIT | `5` |

## 7. 역참조(이 파일을 사용하는 곳)

- `app/api/v1/endpoints/apt_price.py` — `from app.services import apt_price_service` 후 `apt_price_service.get_top_bottom(...)` 호출.

## 8. 재생성 지침

> 위 내용을 근거로 `backend_fastApi/app/services/apt_price_service.py` 파일을 동일한 로직으로 재작성하라. 여기 명시되지 않은 세부 구현(변수명 스타일, 코드 포맷 등)은 기존 프로젝트 컨벤션(PEP 8, 저장소 내 동일 계층 파일들의 스타일)을 따른다.
