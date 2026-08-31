# apt_compare_service.py 명세

## 1. 메타 정보

| 항목 | 값 |
|---|---|
| source_path | backend_fastApi/app/services/apt_compare_service.py |
| source_sha256 | da620c69239aa109bde4cf55e16c9cadf8272d47670013e2e6c457ff52f23000 |
| source_lines | 101 |

## 2. 역할 요약

`query_type`(평단가/층별가)에 대응하는 마트(`dm_apt_pyeong_price`/`dm_apt_flr_price`)에서 자치구+법정동+지번+건물명(선택)+그룹(선택) 조건에 맞는 단지 row를 조회하는 `compare_apartments`와, 층별가 조회 시 평단가 마트에서 최근 공급면적을 보완 조회하는 `fetch_recent_supply_pyeong`을 정의한다.

## 3. 외부 인터페이스

| 이름 | 종류 | 시그니처 | 반환 타입 |
|---|---|---|---|
| MART_TABLE_BY_QUERY_TYPE | const | `MART_TABLE_BY_QUERY_TYPE: dict[str, str] = {"pyeong": "dm_apt_pyeong_price", "floor": "dm_apt_flr_price"}` | dict[str, str] |
| GRP_COLUMN_BY_QUERY_TYPE | const | `GRP_COLUMN_BY_QUERY_TYPE: dict[str, str] = {"pyeong": "pyeong_grp", "floor": "flr_grp"}` | dict[str, str] |
| _build_where_clause | function | `def _build_where_clause(cgg_cd: str, stdg_cd: str, mno: str, sno: str, bldg_nm: str \| None, grp_column: str \| None, grp: str \| None) -> tuple[str, dict[str, str]]` | tuple[str, dict[str, str]] |
| compare_apartments | function | `def compare_apartments(*, cgg_cd: str, stdg_cd: str, bldg_nm: str \| None, mno: str, sno: str, query_type: str, grp: str \| None) -> tuple[str, list[dict[str, Any]]]` | tuple[str, list[dict[str, Any]]] |
| fetch_recent_supply_pyeong | function | `def fetch_recent_supply_pyeong(*, cgg_cd: str, stdg_cd: str, bldg_nm: str \| None, mno: str, sno: str) -> float \| None` | float \| None |

## 4. 의존성(imports)

- 표준 라이브러리:
  - `from typing import Any`
- 서드파티: 없음
- 내부 모듈:
  - `from app.core import duckdb_client`

## 5. 로직 상세

### MART_TABLE_BY_QUERY_TYPE

- 값: `{"pyeong": "dm_apt_pyeong_price", "floor": "dm_apt_flr_price"}`.

### GRP_COLUMN_BY_QUERY_TYPE

- 값: `{"pyeong": "pyeong_grp", "floor": "flr_grp"}`.

### _build_where_clause

- 목적(원문 docstring): "자치구코드+법정동코드+지번 본번/부번(모두 필수) 조건에 건물명(선택, 부분일치 LIKE)과 그룹(grp_column/grp, 선택) 조건을 동적으로 추가한다. base_date 매칭 여부 확인(resolve_base_date_for_filter)과 실제 데이터 조회가 동일한 조건을 재사용한다."
- 파라미터: `cgg_cd: str`, `stdg_cd: str`, `mno: str`, `sno: str`, `bldg_nm: str | None`, `grp_column: str | None`, `grp: str | None`.
- 처리 흐름:
  1. `params: dict[str, str] = {"cgg_cd": cgg_cd, "stdg_cd": stdg_cd, "mno": mno, "sno": sno}`.
  2. `where_clause = "WHERE cgg_cd = $cgg_cd AND stdg_cd = $stdg_cd AND mno = $mno AND sno = $sno"`.
  3. `if bldg_nm:` 이면 `where_clause += " AND bldg_nm LIKE $bldg_nm"`; `params["bldg_nm"] = f"%{bldg_nm}%"`.
  4. `if grp_column and grp:` 이면 `where_clause += f" AND {grp_column} = $grp"`; `params["grp"] = grp`.
  5. `return where_clause, params`.
- 반환값: 조립된 `where_clause` 문자열과 파라미터 딕셔너리.

### compare_apartments

- 목적(원문 docstring): "query_type(평단가/층별가)에 해당하는 마트에서 자치구코드(cgg_cd) + 법정동코드(stdg_cd) + 지번 본번(mno) + 지번 부번(sno) + 건물명(bldg_nm, 선택, 부분일치 LIKE) + 그룹(grp, 선택, pyeong_grp 또는 flr_grp 컬럼)이 일치하는 row를 가공 없이 그대로 조회한다. base_date는 이 조건에 매칭되는 데이터가 있는 가장 최근 파티션까지 소급 탐색한다."
- 파라미터(모두 키워드 전용): `cgg_cd: str`, `stdg_cd: str`, `bldg_nm: str | None`, `mno: str`, `sno: str`, `query_type: str`, `grp: str | None`.
- 처리 흐름:
  1. `mart_table = MART_TABLE_BY_QUERY_TYPE[query_type]`; `grp_column = GRP_COLUMN_BY_QUERY_TYPE[query_type]`.
  2. `resolved_grp = grp`.
  3. `if grp and query_type == "pyeong" and grp == "40":` 이면 `resolved_grp = "40+"`(주석 원문: "마트의 pyeong_grp 컬럼은 최상위 구간을 \"40+\"로 저장하므로, 입력값 \"40\"을 \"40+\"로 변환해 조회한다.").
  4. `con = duckdb_client.get_connection()`.
  5. `try:` 블록:
     a. `where_clause, params = _build_where_clause(cgg_cd, stdg_cd, mno, sno, bldg_nm, grp_column, resolved_grp)`.
     b. `base_date = duckdb_client.resolve_base_date_for_filter(con, mart_table, where_clause, params) or duckdb_client.resolve_base_date(con, mart_table)`.
     c. `parquet_glob = f"{duckdb_client.mart_base_path(mart_table)}/base_date={base_date}/*.parquet"`.
     d. 쿼리(f-string):
        ```python
        query = f"""
            SELECT *
            FROM read_parquet('{parquet_glob}', hive_partitioning = true)
            {where_clause}
        """
        ```
     e. `result = con.execute(query, params)`; `items = duckdb_client.rows_to_dicts(result)`.
  6. `finally: con.close()`.
  7. `return base_date, items`.
- 반환값: `(base_date, items)`. `items`는 조건에 맞는 row 전체(가공 없음).

### fetch_recent_supply_pyeong

- 목적(원문 docstring): "dm_apt_pyeong_price 마트에는 있지만 dm_apt_flr_price 마트에는 없는 recent_supply_pyeong을 보완하기 위해, 자치구코드+법정동코드+지번 본번(mno)+지번 부번(sno)(+건물명, 선택)이 일치하는 row 중 recent_deal_date가 가장 최근인 row의 recent_supply_pyeong 값을 조회한다. query_type='floor' 조회 시 사용."
- 파라미터(모두 키워드 전용): `cgg_cd: str`, `stdg_cd: str`, `bldg_nm: str | None`, `mno: str`, `sno: str`.
- 처리 흐름:
  1. `mart_table = MART_TABLE_BY_QUERY_TYPE["pyeong"]`.
  2. `con = duckdb_client.get_connection()`.
  3. `try:` 블록:
     a. `where_clause, params = _build_where_clause(cgg_cd, stdg_cd, mno, sno, bldg_nm, None, None)`(grp_column/grp는 항상 `None`).
     b. `base_date = duckdb_client.resolve_base_date_for_filter(con, mart_table, where_clause, params) or duckdb_client.resolve_base_date(con, mart_table)`.
     c. `parquet_glob = f"{duckdb_client.mart_base_path(mart_table)}/base_date={base_date}/*.parquet"`.
     d. 쿼리(f-string):
        ```python
        query = f"""
            SELECT recent_supply_pyeong
            FROM read_parquet('{parquet_glob}', hive_partitioning = true)
            {where_clause}
            ORDER BY recent_deal_date DESC
            LIMIT 1
        """
        ```
     e. `row = con.execute(query, params).fetchone()`.
  4. `finally: con.close()`.
  5. `return row[0] if row else None`.
- 반환값: 매칭 row가 있으면 그 `recent_supply_pyeong` 값, 없으면 `None`.

## 6. 모듈 레벨 상수/설정값

| 이름 | 값 |
|---|---|
| MART_TABLE_BY_QUERY_TYPE | `{"pyeong": "dm_apt_pyeong_price", "floor": "dm_apt_flr_price"}` |
| GRP_COLUMN_BY_QUERY_TYPE | `{"pyeong": "pyeong_grp", "floor": "flr_grp"}` |

## 7. 역참조(이 파일을 사용하는 곳)

- `app/api/v1/endpoints/apt_compare.py` — `from app.services import apt_compare_service` 후 `apt_compare_service.compare_apartments(...)`, `apt_compare_service.fetch_recent_supply_pyeong(...)` 호출.

## 8. 재생성 지침

> 위 내용을 근거로 `backend_fastApi/app/services/apt_compare_service.py` 파일을 동일한 로직으로 재작성하라. 여기 명시되지 않은 세부 구현(변수명 스타일, 코드 포맷 등)은 기존 프로젝트 컨벤션(PEP 8, 저장소 내 동일 계층 파일들의 스타일)을 따른다.
