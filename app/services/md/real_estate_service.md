# real_estate_service.py 명세

## 1. 메타 정보

| 항목 | 값 |
|---|---|
| source_path | backend_fastApi/app/services/real_estate_service.py |
| source_sha256 | 67493639c3e24168325b6e8bbfa0550c6ab5994cee7300a4ba19f845b17a672b |
| source_lines | 74 |

## 2. 역할 요약

RAW `real_estate` 데이터셋에서 최신(또는 매칭되는 가장 최근) year/month/day 파티션의 아파트 실거래 목록을 조회하고, 건물별 매매가/평당가 평균과 직전 대비 가격 변동(price_change)을 계산하는 `get_latest_listings` 함수를 정의한다.

## 3. 외부 인터페이스

| 이름 | 종류 | 시그니처 | 반환 타입 |
|---|---|---|---|
| DATASET | const | `DATASET = "real_estate"` | str |
| PYEONG_DIVISOR | const | `PYEONG_DIVISOR = 3.305785` | float |
| get_latest_listings | function | `def get_latest_listings() -> tuple[str, list[dict[str, Any]]]` | tuple[str, list[dict[str, Any]]] |

## 4. 의존성(imports)

- 표준 라이브러리:
  - `from typing import Any`
- 서드파티: 없음
- 내부 모듈:
  - `from app.core import duckdb_client`

## 5. 로직 상세

### DATASET

- 값: `"real_estate"`.

### PYEONG_DIVISOR

- 값: `3.305785`(㎡ → 평 환산 계수).

### get_latest_listings

- 목적(원문 docstring): "RAW 버킷의 real_estate 데이터셋에서, BLDG_USG = '아파트' 조건에 매칭되는 row가 있는 가장 최근 (year, month, day) 파티션의 아파트별 최신 실거래 목록을 조회한다(오늘 파티션에 아파트 거래가 없으면 조건에 맞는 데이터가 있는 과거 파티션까지 소급). 같은 날 동일 건물(자치구+법정동+지번+건물명)의 거래가 여러 건이면 매매가/평당가는 평균값으로 집계한다. price_change는 같은 건물의 가장 최근 이전 거래일(과거 전체 파티션 중, 아파트 거래만) 대비 매매가 변동(만원)이다."
- 파라미터: 없음.
- 처리 흐름:
  1. `con = duckdb_client.get_connection()`.
  2. `try:` 블록:
     a. `apt_only_where = "WHERE BLDG_USG = $bldg_usg"`; `apt_only_params = {"bldg_usg": "아파트"}`.
     b. `year, month, day = duckdb_client.resolve_latest_date_partition_for_filter(con, DATASET, apt_only_where, apt_only_params) or duckdb_client.resolve_latest_date_partition(con, DATASET)`.
     c. `history_glob = f"{duckdb_client.raw_base_path(DATASET)}/**/*.parquet"`.
     d. 쿼리(f-string, `{PYEONG_DIVISOR}` 치환):
        ```python
        query = f"""
            WITH daily AS (
                SELECT
                    CGG_CD AS cgg_cd,
                    ANY_VALUE(CGG_NM) AS cgg_nm,
                    STDG_CD AS stdg_cd,
                    ANY_VALUE(STDG_NM) AS stdg_nm,
                    BLDG_NM AS bldg_nm,
                    MNO AS mno,
                    SNO AS sno,
                    CAST(year AS VARCHAR) AS year,
                    month,
                    day,
                    AVG(TRY_CAST(THING_AMT AS DOUBLE)) AS avg_thing_amt,
                    AVG(TRY_CAST(THING_AMT AS DOUBLE) / NULLIF(ARCH_AREA / {PYEONG_DIVISOR}, 0)) AS avg_pyeong_amt
                FROM read_parquet($history_glob, hive_partitioning = true)
                WHERE BLDG_USG = '아파트'
                GROUP BY CGG_CD, STDG_CD, BLDG_NM, MNO, SNO, year, month, day
            ),
            with_prev AS (
                SELECT
                    *,
                    LAG(avg_thing_amt) OVER (
                        PARTITION BY cgg_cd, stdg_cd, mno, sno, bldg_nm
                        ORDER BY year, month, day
                    ) AS prev_avg_thing_amt
                FROM daily
            )
            SELECT
                bldg_nm AS apt_name,
                cgg_nm,
                stdg_nm,
                CAST(ROUND(avg_thing_amt) AS BIGINT) AS thing_amt,
                CAST(ROUND(avg_pyeong_amt) AS BIGINT) AS pyeong_amt,
                CASE
                    WHEN prev_avg_thing_amt IS NULL THEN NULL
                    ELSE CAST(ROUND(avg_thing_amt - prev_avg_thing_amt) AS BIGINT)
                END AS price_change,
                make_date(CAST(year AS INT), CAST(month AS INT), CAST(day AS INT)) AS update_date
            FROM with_prev
            WHERE year = $year AND month = $month AND day = $day
            ORDER BY apt_name
        """
        ```
     e. `params = {"history_glob": history_glob, "year": year, "month": month, "day": day}`.
     f. `result = con.execute(query, params)`; `items = duckdb_client.rows_to_dicts(result)`.
  3. `finally: con.close()`.
  4. `base_date = f"{year}-{month}-{day}"`.
  5. `return base_date, items`.
- 반환값: `(base_date, items)`. `base_date`는 `"YYYY-MM-DD"` 형식 문자열. `items`는 건물별 최신 실거래 항목 리스트(자치구/법정동/건물명/매매가/평당가/가격변동/업데이트일자). 파티션 자체가 없으면 `duckdb_client.resolve_latest_date_partition_for_filter`/`resolve_latest_date_partition`이 던지는 `FileNotFoundError`가 전파됨(이 함수는 별도로 잡지 않음).

## 6. 모듈 레벨 상수/설정값

| 이름 | 값 |
|---|---|
| DATASET | `"real_estate"` |
| PYEONG_DIVISOR | `3.305785` |

## 7. 역참조(이 파일을 사용하는 곳)

- `app/api/v1/endpoints/real_estate.py` — `from app.services import real_estate_service` 후 `real_estate_service.get_latest_listings()` 호출.

## 8. 재생성 지침

> 위 내용을 근거로 `backend_fastApi/app/services/real_estate_service.py` 파일을 동일한 로직으로 재작성하라. 여기 명시되지 않은 세부 구현(변수명 스타일, 코드 포맷 등)은 기존 프로젝트 컨벤션(PEP 8, 저장소 내 동일 계층 파일들의 스타일)을 따른다.
