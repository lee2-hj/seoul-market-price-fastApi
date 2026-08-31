# mart_service.py 명세

## 1. 메타 정보

| 항목 | 값 |
|---|---|
| source_path | backend_fastApi/app/services/mart_service.py |
| source_sha256 | 0e896114ac7f2a7d9e42758c89c473293254cb11d98e26ab0d30a054d8c00b2a |
| source_lines | 112 |

## 2. 역할 요약

`dm_dong_pyeong_price_avg` 마트에서 두 지역(자치구코드 필수 + 법정동코드 선택)의 동 단위 시세 row와 집계(total_count/avg_thing_amt/avg_pyeong_amt)를 각각 독립적인 base_date 폴백으로 조회하는 `compare_dong_pyeong` 함수와 내부 헬퍼들을 정의한다.

## 3. 외부 인터페이스

| 이름 | 종류 | 시그니처 | 반환 타입 |
|---|---|---|---|
| MART_TABLE | const | `MART_TABLE = "dm_dong_pyeong_price_avg"` | str |
| _build_where_clause | function | `def _build_where_clause(cgg_cd: str, stdg_cd: str \| None) -> tuple[str, dict[str, str]]` | tuple[str, dict[str, str]] |
| _fetch_region_rows | function | `def _fetch_region_rows(con, base_date: str, cgg_cd: str, stdg_cd: str \| None) -> list[dict[str, Any]]` | list[dict[str, Any]] |
| _fetch_region_summary | function | `def _fetch_region_summary(con, base_date: str, cgg_cd: str, stdg_cd: str \| None) -> tuple[int, int, int]` | tuple[int, int, int] |
| compare_dong_pyeong | function | `def compare_dong_pyeong(*, region1_cgg_cd: str, region1_stdg_cd: str \| None, region2_cgg_cd: str, region2_stdg_cd: str \| None) -> tuple[str, str, str, list[dict[str, Any]], list[dict[str, Any]], tuple[int, int, int], tuple[int, int, int]]` | tuple[str, str, str, list[dict[str, Any]], list[dict[str, Any]], tuple[int, int, int], tuple[int, int, int]] |

## 4. 의존성(imports)

- 표준 라이브러리:
  - `from typing import Any`
- 서드파티: 없음
- 내부 모듈:
  - `from app.core import duckdb_client`

## 5. 로직 상세

### MART_TABLE

- 값: `"dm_dong_pyeong_price_avg"`.

### _build_where_clause

- 목적: `cgg_cd`(필수 취급)와 `stdg_cd`(선택) 조건을 AND로 동적 결합.
- 파라미터: `cgg_cd: str`, `stdg_cd: str | None`.
- 처리 흐름:
  1. `conditions: list[str] = []`; `params: dict[str, str] = {}`.
  2. `if cgg_cd: conditions.append("cgg_cd = $cgg_cd"); params["cgg_cd"] = cgg_cd`.
  3. `if stdg_cd: conditions.append("stdg_cd = $stdg_cd"); params["stdg_cd"] = stdg_cd`.
  4. `where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""`.
  5. `return where_clause, params`.
- 반환값: 조건이 하나도 없으면 `("", {})`. 있으면 `"WHERE ..."` 절과 파라미터 딕셔너리.

### _fetch_region_rows

- 목적(원문 docstring): "선택된 base_date 파티션에서 자치구코드(필수) + 법정동코드(선택) 조건에 맞는 row를 동적으로 추출한다."
- 파라미터: `con`, `base_date: str`, `cgg_cd: str`, `stdg_cd: str | None`.
- 처리 흐름:
  1. `parquet_glob = f"{duckdb_client.mart_base_path(MART_TABLE)}/base_date={base_date}/*.parquet"`.
  2. `where_clause, params = _build_where_clause(cgg_cd, stdg_cd)`.
  3. 쿼리(f-string):
     ```python
     query = f"""
         SELECT *
         FROM read_parquet('{parquet_glob}', hive_partitioning = true)
         {where_clause}
     """
     ```
  4. `result = con.execute(query, params)`; `return duckdb_client.rows_to_dicts(result)`.
- 반환값: 조건에 맞는 row들의 JSON-safe 딕셔너리 리스트.

### _fetch_region_summary

- 목적(원문 docstring): "선택된 base_date 파티션에서 자치구코드(필수) + 법정동코드(선택) 조건에 맞는 전체 거래건수(total_count)와 평균 매매가(SUM(total_thing_amt) / 전체 거래건수), 평균 평당가(SUM(total_pyeong_amt) / 전체 거래건수)를 반올림하여 집계한다."
- 파라미터: `con`, `base_date: str`, `cgg_cd: str`, `stdg_cd: str | None`.
- 처리 흐름:
  1. `parquet_glob = f"{duckdb_client.mart_base_path(MART_TABLE)}/base_date={base_date}/*.parquet"`.
  2. `where_clause, params = _build_where_clause(cgg_cd, stdg_cd)`.
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
- 반환값: `(total_count, avg_thing_amt, avg_pyeong_amt)` 3튜플. 매칭 row가 없으면 `total_count=0`, 평균값들도 `0`.

### compare_dong_pyeong

- 목적(원문 docstring): "프론트에서 선택한 두 지역(자치구코드 필수 + 법정동코드 선택)의 동 단위 시세 데이터와 지역별 집계(그룹별 데이터 개수/평균 매매가/평균 평당가)를 MinIO Parquet에서 동적으로 필터링한다. 지역1/지역2는 서로 독립적으로 base_date 폴백을 탐색한다(한쪽만 데이터가 없어 과거로 소급될 수 있고, 이는 정상 동작이다). 반환되는 최상위 base_date는 하위 호환을 위한 값으로 region1_base_date/region2_base_date 중 더 최신인 날짜다."
- 파라미터(모두 키워드 전용): `region1_cgg_cd: str`, `region1_stdg_cd: str | None`, `region2_cgg_cd: str`, `region2_stdg_cd: str | None`.
- 처리 흐름:
  1. `con = duckdb_client.get_connection()`.
  2. `try:` 블록:
     a. `region1_where, region1_params = _build_where_clause(region1_cgg_cd, region1_stdg_cd)`.
     b. `region2_where, region2_params = _build_where_clause(region2_cgg_cd, region2_stdg_cd)`.
     c. `region1_base_date = duckdb_client.resolve_base_date_for_filter(con, MART_TABLE, region1_where, region1_params) or duckdb_client.resolve_base_date(con, MART_TABLE)`.
     d. `region2_base_date = duckdb_client.resolve_base_date_for_filter(con, MART_TABLE, region2_where, region2_params) or duckdb_client.resolve_base_date(con, MART_TABLE)`.
     e. `region1_items = _fetch_region_rows(con, region1_base_date, region1_cgg_cd, region1_stdg_cd)`.
     f. `region2_items = _fetch_region_rows(con, region2_base_date, region2_cgg_cd, region2_stdg_cd)`.
     g. `region1_summary = _fetch_region_summary(con, region1_base_date, region1_cgg_cd, region1_stdg_cd)`.
     h. `region2_summary = _fetch_region_summary(con, region2_base_date, region2_cgg_cd, region2_stdg_cd)`.
  3. `finally: con.close()`.
  4. `base_date = max(region1_base_date, region2_base_date)`.
  5. `return (base_date, region1_base_date, region2_base_date, region1_items, region2_items, region1_summary, region2_summary)`.
- 반환값: 7-튜플 `(base_date, region1_base_date, region2_base_date, region1_items, region2_items, region1_summary, region2_summary)`. `base_date`는 두 지역 base_date 중 문자열 비교 기준 더 큰(최신) 값.

## 6. 모듈 레벨 상수/설정값

| 이름 | 값 |
|---|---|
| MART_TABLE | `"dm_dong_pyeong_price_avg"` |

## 7. 역참조(이 파일을 사용하는 곳)

- `app/api/v1/endpoints/compare.py` — `from app.services import mart_service` 후 `mart_service.compare_dong_pyeong(...)` 호출.

## 8. 재생성 지침

> 위 내용을 근거로 `backend_fastApi/app/services/mart_service.py` 파일을 동일한 로직으로 재작성하라. 여기 명시되지 않은 세부 구현(변수명 스타일, 코드 포맷 등)은 기존 프로젝트 컨벤션(PEP 8, 저장소 내 동일 계층 파일들의 스타일)을 따른다.
