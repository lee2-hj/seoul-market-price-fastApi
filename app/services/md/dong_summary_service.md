# dong_summary_service.py 명세

## 1. 메타 정보

| 항목 | 값 |
|---|---|
| source_path | backend_fastApi/app/services/dong_summary_service.py |
| source_sha256 | ee83786b96f629a6f85061ec221d0b24a2d9d69dc2e85658da439a21f85eb0dd |
| source_lines | 82 |

## 2. 역할 요약

`dm_dong_pyeong_price_avg` 마트에서 자치구(cgg_cd) 또는 법정동(stdg_cd) 기준으로 그룹화한 집계(total_count/avg_thing_amt/avg_pyeong_amt)를 계산하는 `get_dong_summary`와 그 내부 헬퍼 함수들을 정의한다.

## 3. 외부 인터페이스

| 이름 | 종류 | 시그니처 | 반환 타입 |
|---|---|---|---|
| MART_TABLE | const | `MART_TABLE = "dm_dong_pyeong_price_avg"` | str |
| _build_where_clause | function | `def _build_where_clause(region_cgg: str \| None) -> tuple[str, dict[str, str]]` | tuple[str, dict[str, str]] |
| _fetch_rows | function | `def _fetch_rows(con, base_date: str, region_cgg: str \| None) -> list[dict[str, Any]]` | list[dict[str, Any]] |
| _group_rows | function | `def _group_rows(rows: list[dict[str, Any]], code_field: str, name_field: str) -> dict[str, dict[str, Any]]` | dict[str, dict[str, Any]] |
| get_dong_summary | function | `def get_dong_summary(*, region_cgg: str \| None) -> tuple[str, dict[str, dict[str, Any]]]` | tuple[str, dict[str, dict[str, Any]]] |

## 4. 의존성(imports)

- 표준 라이브러리:
  - `from collections import OrderedDict`
  - `from typing import Any`
- 서드파티: 없음
- 내부 모듈:
  - `from app.core import duckdb_client`

## 5. 로직 상세

### MART_TABLE

- 값: `"dm_dong_pyeong_price_avg"`.

### _build_where_clause

- 목적(원문 docstring): "자치구 조건(코드 또는 명칭)을 동적으로 추가한다."
- 파라미터: `region_cgg: str | None`.
- 처리 흐름:
  1. `if not region_cgg: return "", {}`.
  2. 아니면 `return "WHERE (cgg_cd = $region_cgg OR cgg_nm = $region_cgg)", {"region_cgg": region_cgg}`.
- 반환값: `region_cgg`가 없으면 `("", {})`. 있으면 `cgg_cd` 또는 `cgg_nm`이 일치하는 조건과 그 파라미터.

### _fetch_rows

- 목적: 지정된 base_date 파티션에서 (선택적) 자치구 조건에 맞는 전체 row를 조회.
- 파라미터: `con`, `base_date: str`, `region_cgg: str | None`.
- 처리 흐름:
  1. `parquet_glob = f"{duckdb_client.mart_base_path(MART_TABLE)}/base_date={base_date}/*.parquet"`.
  2. `where_clause, params = _build_where_clause(region_cgg)`.
  3. 쿼리(f-string, `{parquet_glob}`/`{where_clause}` 치환):
     ```python
     query = f"""
         SELECT *
         FROM read_parquet('{parquet_glob}', hive_partitioning = true)
         {where_clause}
     """
     ```
  4. `result = con.execute(query, params)`.
  5. `return duckdb_client.rows_to_dicts(result)`.
- 반환값: 조건에 맞는 row들을 JSON-safe 딕셔너리 리스트로 변환한 결과.

### _group_rows

- 목적(원문 docstring): "row 목록을 code_field(cgg_cd 또는 stdg_cd) 기준으로 그룹화하고, 그룹별 전체 거래건수(total_count = SUM(deal_cnt))와 평균 매매가(SUM(total_thing_amt) / total_count), 평균 평당가(SUM(total_pyeong_amt) / total_count)를 반올림하여 함께 집계한다. (compare.py의 _fetch_region_summary와 동일한 계산식)"
- 파라미터: `rows: list[dict[str, Any]]`, `code_field: str`, `name_field: str`.
- 처리 흐름:
  1. `groups: "OrderedDict[str, dict[str, Any]]" = OrderedDict()`.
  2. `rows`의 각 `row`에 대해:
     a. `code = row[code_field]`; `group = groups.get(code)`.
     b. `group`이 `None`이면 `group = {"code": code, "name": row[name_field], "_total_count": 0, "_sum_thing_amt": 0, "_sum_pyeong_amt": 0}`을 만들어 `groups[code] = group`.
     c. `group["_total_count"] += row["deal_cnt"]`; `group["_sum_thing_amt"] += row["total_thing_amt"]`; `group["_sum_pyeong_amt"] += row["total_pyeong_amt"]`.
  3. `groups.values()`의 각 `group`에 대해:
     a. `total_count = group.pop("_total_count")`; `sum_thing_amt = group.pop("_sum_thing_amt")`; `sum_pyeong_amt = group.pop("_sum_pyeong_amt")`.
     b. `group["total_count"] = total_count`.
     c. `group["avg_thing_amt"] = round(sum_thing_amt / total_count) if total_count else 0`.
     d. `group["avg_pyeong_amt"] = round(sum_pyeong_amt / total_count) if total_count else 0`.
  4. `return groups`.
- 반환값: `code_field` 값을 key로, `{code, name, total_count, avg_thing_amt, avg_pyeong_amt}`를 value로 하는 `OrderedDict`(row 최초 등장 순서 유지).

### get_dong_summary

- 목적(원문 docstring): "region_cgg가 없으면 cgg_cd끼리, 있으면 해당 자치구 내 데이터를 stdg_cd끼리 그룹화하여 그룹별 집계(total_count/avg_thing_amt/avg_pyeong_amt)를 반환한다. base_date는 최신 파티션만 보는 것이 아니라, 조건에 맞는 데이터가 있는 가장 최근 base_date까지 소급 조회한다."
- 파라미터: `region_cgg: str | None`(키워드 전용).
- 처리 흐름:
  1. `con = duckdb_client.get_connection()`.
  2. `try:` 블록:
     a. `where_clause, where_params = _build_where_clause(region_cgg)`.
     b. `base_date = duckdb_client.resolve_base_date_for_filter(con, MART_TABLE, where_clause, where_params) or duckdb_client.resolve_base_date(con, MART_TABLE)`.
     c. `rows = _fetch_rows(con, base_date, region_cgg)`.
     d. `if region_cgg: groups = _group_rows(rows, "stdg_cd", "stdg_nm")` / `else: groups = _group_rows(rows, "cgg_cd", "cgg_nm")`.
  3. `finally: con.close()`.
  4. `return base_date, groups`.
- 반환값: `(base_date, groups)` 튜플. `region_cgg`가 있으면 `stdg_cd` 기준, 없으면 `cgg_cd` 기준 그룹화 결과.

## 6. 모듈 레벨 상수/설정값

| 이름 | 값 |
|---|---|
| MART_TABLE | `"dm_dong_pyeong_price_avg"` |

## 7. 역참조(이 파일을 사용하는 곳)

- `app/api/v1/endpoints/dong_summary.py` — `from app.services import dong_summary_service` 후 `dong_summary_service.get_dong_summary(...)` 호출.

## 8. 재생성 지침

> 위 내용을 근거로 `backend_fastApi/app/services/dong_summary_service.py` 파일을 동일한 로직으로 재작성하라. 여기 명시되지 않은 세부 구현(변수명 스타일, 코드 포맷 등)은 기존 프로젝트 컨벤션(PEP 8, 저장소 내 동일 계층 파일들의 스타일)을 따른다.
