# compare.py 명세

## 1. 메타 정보

| 항목 | 값 |
|---|---|
| source_path | backend_fastApi/app/api/v1/endpoints/compare.py |
| source_sha256 | 43145ae188943cec6485c9ad7f8899b938dd2bc28dddfcd92efacef5c604b890 |
| source_lines | 67 |

## 2. 역할 요약

`/compare` prefix 라우터를 정의하고, `GET /compare/dong-pyeong`에서 `mart_service.compare_dong_pyeong`을 호출해 두 지역의 동 단위 평균 시세를 `DongPyeongCompareResponse`로 반환한다.

## 3. 외부 인터페이스

| 이름 | 종류 | 시그니처 | 반환 타입 |
|---|---|---|---|
| router | const | `router = APIRouter(prefix="/compare", tags=["compare"])` | APIRouter |
| get_dong_pyeong_compare | function | `def get_dong_pyeong_compare(query: Annotated[DongPyeongCompareQuery, Query()]) -> DongPyeongCompareResponse` | DongPyeongCompareResponse |

## 4. 의존성(imports)

- 표준 라이브러리:
  - `from typing import Annotated`
- 서드파티:
  - `from fastapi import APIRouter, HTTPException, Query`
- 내부 모듈:
  - `from app.schemas.compare import (DongPyeongCompareQuery, DongPyeongCompareResponse, RegionCompareResult,)`
  - `from app.services import mart_service`

파일 최상단 주석(1행): `#동별/자치구별 비교 api`

## 5. 로직 상세

### router

- 목적: `/compare` prefix, `compare` 태그의 라우터 생성.
- 처리 흐름: `router = APIRouter(prefix="/compare", tags=["compare"])`.
- 반환값: 해당 없음.

### get_dong_pyeong_compare

- 목적(원문 docstring): "프론트가 선택한 지역1/지역2(자치구코드+법정동코드)의 동 단위 평균 시세를 MinIO Parquet에서 동적 조회한다."
- 데코레이터: `@router.get("/dong-pyeong", response_model=DongPyeongCompareResponse)`.
- 파라미터: `query: Annotated[DongPyeongCompareQuery, Query()]`.
- 처리 흐름:
  1. `try:` 블록에서 다음 7개 값을 언패킹: `(base_date, region1_base_date, region2_base_date, region1_items, region2_items, region1_summary, region2_summary) = mart_service.compare_dong_pyeong(region1_cgg_cd=query.region1_cgg_cd, region1_stdg_cd=query.region1_stdg_cd, region2_cgg_cd=query.region2_cgg_cd, region2_stdg_cd=query.region2_stdg_cd)`.
  2. `except FileNotFoundError as exc:` 이면 `raise HTTPException(status_code=404, detail=str(exc)) from exc`.
  3. `region1_total_count, region1_avg_thing_amt, region1_avg_pyeong_amt = region1_summary`.
  4. `region2_total_count, region2_avg_thing_amt, region2_avg_pyeong_amt = region2_summary`.
  5. `region1_first_row = region1_items[0] if region1_items else {}`.
  6. `region2_first_row = region2_items[0] if region2_items else {}`.
  7. `return DongPyeongCompareResponse(base_date=base_date, region1=RegionCompareResult(cgg_cd=query.region1_cgg_cd, stdg_cd=query.region1_stdg_cd, base_date=region1_base_date, total_count=region1_total_count, avg_thing_amt=region1_avg_thing_amt, avg_pyeong_amt=region1_avg_pyeong_amt, latitude=region1_first_row.get("latitude"), longitude=region1_first_row.get("longitude")), region2=RegionCompareResult(cgg_cd=query.region2_cgg_cd, stdg_cd=query.region2_stdg_cd, base_date=region2_base_date, total_count=region2_total_count, avg_thing_amt=region2_avg_thing_amt, avg_pyeong_amt=region2_avg_pyeong_amt, latitude=region2_first_row.get("latitude"), longitude=region2_first_row.get("longitude")))`.
- 반환값: 성공 시 `region1`/`region2`가 각각 `RegionCompareResult`인 `DongPyeongCompareResponse`(좌표는 각 지역 첫 row에서만 추출, row가 없으면 `latitude`/`longitude`는 `None`). 서비스에서 `FileNotFoundError` 발생 시 404, `detail`은 예외 메시지 문자열.

## 6. 모듈 레벨 상수/설정값

없음.

## 7. 역참조(이 파일을 사용하는 곳)

- `app/api/v1/router.py` — `from app.api.v1.endpoints import (compare, ...)` 후 `router.include_router(compare.router)`로 등록.

## 8. 재생성 지침

> 위 내용을 근거로 `backend_fastApi/app/api/v1/endpoints/compare.py` 파일을 동일한 로직으로 재작성하라. 여기 명시되지 않은 세부 구현(변수명 스타일, 코드 포맷 등)은 기존 프로젝트 컨벤션(PEP 8, 저장소 내 동일 계층 파일들의 스타일)을 따른다.
