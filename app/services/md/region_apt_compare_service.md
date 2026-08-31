# region_apt_compare_service.py 명세

## 1. 메타 정보

| 항목 | 값 |
|---|---|
| source_path | backend_fastApi/app/services/region_apt_compare_service.py |
| source_sha256 | e1a86b7a066b04eaa7a32883aa3ba062421bdf7393be92a1ee32df7e4efa7ca8 |
| source_lines | 139 |

## 2. 역할 요약

`dm_apt_recent_trade` 마트(최신 base_date 파티션, 최근 90일 실거래 사전집계)에서 두 아파트를 각각 자치구+법정동+아파트명+지번(모두 필수)으로 특정해 비교 지표를 조회하는 `compare_region_apts`와 내부 헬퍼들을 정의한다.

## 3. 외부 인터페이스

| 이름 | 종류 | 시그니처 | 반환 타입 |
|---|---|---|---|
| MART_TABLE | const | `MART_TABLE = "dm_apt_recent_trade"` | str |
| _build_where_clause | function | `def _build_where_clause(cgg_cd: str, bjd_cd: str, apt_nm: str, mno: str, sno: str) -> tuple[str, dict[str, str]]` | tuple[str, dict[str, str]] |
| _fetch_apt_row | function | `def _fetch_apt_row(con, base_date: str, cgg_cd: str, bjd_cd: str, apt_nm: str, mno: str, sno: str) -> dict[str, Any] \| None` | dict[str, Any] \| None |
| _build_group | function | `def _build_group(row: dict[str, Any] \| None, base_date: str) -> dict[str, Any]` | dict[str, Any] |
| compare_region_apts | function | `def compare_region_apts(*, cgg_cd_1: str, bjd_cd_1: str, apt_nm_1: str, mno_1: str, sno_1: str, cgg_cd_2: str, bjd_cd_2: str, apt_nm_2: str, mno_2: str, sno_2: str) -> tuple[dict[str, Any], dict[str, Any]]` | tuple[dict[str, Any], dict[str, Any]] |

## 4. 의존성(imports)

- 표준 라이브러리:
  - `from typing import Any`
- 서드파티: 없음
- 내부 모듈:
  - `from app.core import duckdb_client`

파일 최상단 주석(1~13행, `MART_TABLE` 선언 직전): `dm_apt_recent_trade 마트 실제 컬럼(DESCRIBE로 확인): apt_id, apt_name, sgg_cd, sgg_nm, dong_cd, dong_nm, build_year, mno, sno, total_trade_amount(BIGINT, 만원 합계), total_price_per_pyeong(BIGINT, 평당가 합계), total_pyeong(DOUBLE, 전용면적(평) 합계), latest_trade_amount, latest_trade_pyeong(DOUBLE, 최근 거래 전용면적(평)), trade_count(INTEGER), household_count(INTEGER), use_approval_date, use_approval_year, base_date. total_trade_amount/total_price_per_pyeong/total_pyeong은 다른 dm_ 마트(예: dm_apt_price_avg의 total_thing_amt/total_pyeong_amt)와 동일한 관례로 trade_count건의 합계이므로, 평균값은 각각을 trade_count로 나눠 계산한다. 이 마트는 이미 "최근" 실거래를 base_date 파티션 단위로 사전집계해 두므로, 최신 base_date 파티션만 읽으면 최근 90일 조회 조건을 만족한다(다른 dm_ 마트와 동일).`

## 5. 로직 상세

### MART_TABLE

- 값: `"dm_apt_recent_trade"`.

### _build_where_clause

- 목적(원문 docstring): "자치구코드+법정동코드+아파트명+지번 본번/부번(모두 필수) 조건을 만든다. _fetch_apt_row의 WHERE 절과 동일한 조건이며, base_date 매칭 여부 확인(resolve_base_date_for_filter)과 실제 데이터 조회가 이 조건을 공유한다."
- 파라미터: `cgg_cd: str`, `bjd_cd: str`, `apt_nm: str`, `mno: str`, `sno: str`.
- 처리 흐름:
  1. `params: dict[str, str] = {"cgg_cd": cgg_cd, "bjd_cd": bjd_cd, "apt_nm": apt_nm, "mno": mno, "sno": sno}`.
  2. `where_clause = ("WHERE sgg_cd = $cgg_cd AND dong_cd = $bjd_cd AND apt_name = $apt_nm" " AND mno = $mno AND sno = $sno")`(두 문자열 리터럴이 이어붙여짐).
  3. `return where_clause, params`.
- 반환값: 위 `where_clause` 문자열과 `params` 딕셔너리(항상 동일 형태, 조건부 분기 없음).

### _fetch_apt_row

- 목적(원문 docstring): "자치구코드(sgg_cd)+법정동코드(dong_cd)+아파트명(apt_name)+지번 본번(mno)/부번(sno)이 모두 일치하는 단지 row 하나를 dm_apt_recent_trade 마트의 최신 base_date 파티션에서 조회한다. 같은 법정동 안에 동명 단지가 존재할 수 있어(예: 같은 dong_cd 안에 apt_name이 중복되는 경우) 다섯 조건 모두 필수로 AND 결합해야 단지 하나로 정확히 특정된다."
- 파라미터: `con`, `base_date: str`, `cgg_cd: str`, `bjd_cd: str`, `apt_nm: str`, `mno: str`, `sno: str`.
- 처리 흐름:
  1. `parquet_glob = f"{duckdb_client.mart_base_path(MART_TABLE)}/base_date={base_date}/*.parquet"`.
  2. `params: dict[str, str] = {"cgg_cd": cgg_cd, "bjd_cd": bjd_cd, "apt_nm": apt_nm, "mno": mno, "sno": sno}`.
  3. 쿼리(f-string):
     ```python
     query = f"""
         SELECT
             apt_name, household_count, build_year, use_approval_date,
             total_trade_amount, total_price_per_pyeong, total_pyeong,
             latest_trade_pyeong, trade_count
         FROM read_parquet('{parquet_glob}', hive_partitioning = true)
         WHERE sgg_cd = $cgg_cd AND dong_cd = $bjd_cd AND apt_name = $apt_nm
           AND mno = $mno AND sno = $sno
     """
     ```
  4. `result = con.execute(query, params)`; `rows = duckdb_client.rows_to_dicts(result)`.
  5. `return rows[0] if rows else None`.
- 반환값: 매칭 row가 있으면 첫 번째 row(dict), 없으면 `None`.

### _build_group

- 목적(원문 docstring): "row를 응답용 비교 지표로 가공한다. avg_deal_price/avg_pyeong_price/avg_pyeong은 각각 total_trade_amount/total_price_per_pyeong/total_pyeong을 trade_count로 나눠 반올림한 정수다. latest_trade_pyeong도 원본 값을 반올림한 정수로 전달한다. 매칭되는 row가 없거나(단지 자체를 못 찾음) trade_count가 0이면(최근 90일간 거래 없음) 빈 딕셔너리({})를 반환한다(이 경우 base_date도 포함하지 않는다)."
- 파라미터: `row: dict[str, Any] | None`, `base_date: str`.
- 처리 흐름:
  1. `trade_count = (row or {}).get("trade_count") or 0`.
  2. `if row is None or trade_count == 0: return {}`.
  3. `total_trade_amount = row.get("total_trade_amount") or 0`; `total_price_per_pyeong = row.get("total_price_per_pyeong") or 0`; `total_pyeong = row.get("total_pyeong") or 0`; `latest_trade_pyeong = row.get("latest_trade_pyeong")`.
  4. `avg_deal_price = round(total_trade_amount / trade_count)`.
  5. `avg_pyeong_price = round(total_price_per_pyeong / trade_count)`.
  6. `avg_pyeong = round(total_pyeong / trade_count)`.
  7. `return {"apt_name": row.get("apt_name"), "base_date": base_date, "avg_deal_price": avg_deal_price, "avg_pyeong_price": avg_pyeong_price, "avg_pyeong": avg_pyeong, "latest_trade_pyeong": round(latest_trade_pyeong) if latest_trade_pyeong is not None else None, "deal_count": trade_count, "total_households": row.get("household_count"), "build_year": row.get("build_year"), "use_approval_date": row.get("use_approval_date")}`.
- 반환값: `row`가 `None`이거나 `trade_count == 0`이면 `{}`(빈 딕셔너리, `base_date` 키조차 없음). 아니면 위 9개 키를 가진 딕셔너리.

### compare_region_apts

- 목적(원문 docstring): "dm_apt_recent_trade 마트(최신 base_date 파티션, 최근 90일 실거래 사전집계)에서 아파트1/아파트2 각각을 자치구코드+법정동코드+아파트명+지번 본번/부번(모두 필수)으로 특정해, 비교 지표(평균 매매가/평균 평당가/평균 전용면적/최근 거래 전용면적/거래건수)와 메타데이터(세대수/준공년도/사용승인일)를 조회한다. 두 단지 조회는 서로 독립적이라 한쪽이 매칭되지 않아도(또는 최근 90일간 거래가 없어도, 빈 딕셔너리로) 나머지 한쪽은 정상적으로 반환된다. base_date 또한 단지1/단지2가 서로 독립적으로 폴백 탐색하므로(한쪽만 최신 파티션에 거래가 없으면 그 단지만 과거로 소급), 두 단지가 서로 다른 base_date를 가질 수 있다(정상 동작)."
- 파라미터(모두 키워드 전용): `cgg_cd_1: str`, `bjd_cd_1: str`, `apt_nm_1: str`, `mno_1: str`, `sno_1: str`, `cgg_cd_2: str`, `bjd_cd_2: str`, `apt_nm_2: str`, `mno_2: str`, `sno_2: str`.
- 처리 흐름:
  1. `con = duckdb_client.get_connection()`.
  2. `try:` 블록:
     a. `where_1, params_1 = _build_where_clause(cgg_cd_1, bjd_cd_1, apt_nm_1, mno_1, sno_1)`.
     b. `where_2, params_2 = _build_where_clause(cgg_cd_2, bjd_cd_2, apt_nm_2, mno_2, sno_2)`.
     c. `base_date_1 = duckdb_client.resolve_base_date_for_filter(con, MART_TABLE, where_1, params_1) or duckdb_client.resolve_base_date(con, MART_TABLE)`.
     d. `base_date_2 = duckdb_client.resolve_base_date_for_filter(con, MART_TABLE, where_2, params_2) or duckdb_client.resolve_base_date(con, MART_TABLE)`.
     e. `row_1 = _fetch_apt_row(con, base_date_1, cgg_cd_1, bjd_cd_1, apt_nm_1, mno_1, sno_1)`.
     f. `row_2 = _fetch_apt_row(con, base_date_2, cgg_cd_2, bjd_cd_2, apt_nm_2, mno_2, sno_2)`.
  3. `finally: con.close()`.
  4. `return _build_group(row_1, base_date_1), _build_group(row_2, base_date_2)`.
- 반환값: `(group_1, group_2)` 튜플. 각 그룹은 `_build_group` 결과(매칭 없거나 거래 0건이면 `{}`).

## 6. 모듈 레벨 상수/설정값

| 이름 | 값 |
|---|---|
| MART_TABLE | `"dm_apt_recent_trade"` |

## 7. 역참조(이 파일을 사용하는 곳)

- `app/api/v1/endpoints/region_apt_compare.py` — `from app.services import region_apt_compare_service` 후 `region_apt_compare_service.compare_region_apts(...)` 호출.

## 8. 재생성 지침

> 위 내용을 근거로 `backend_fastApi/app/services/region_apt_compare_service.py` 파일을 동일한 로직으로 재작성하라. 여기 명시되지 않은 세부 구현(변수명 스타일, 코드 포맷 등)은 기존 프로젝트 컨벤션(PEP 8, 저장소 내 동일 계층 파일들의 스타일)을 따른다.
