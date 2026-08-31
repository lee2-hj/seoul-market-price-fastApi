# dong_summary.py 명세

## 1. 메타 정보

| 항목 | 값 |
|---|---|
| source_path | backend_fastApi/app/api/v1/endpoints/dong_summary.py |
| source_sha256 | 46793c3bb595931ef8faec5e284adbf75411ebfdb093fef12cf6736094221261 |
| source_lines | 23 |

## 2. 역할 요약

`/dong` prefix 라우터를 정의하고, `GET /dong/list`에서 `dong_summary_service.get_dong_summary`를 호출해 동/자치구별 집계 결과를 `DongSummaryResponse`로 반환한다.

## 3. 외부 인터페이스

| 이름 | 종류 | 시그니처 | 반환 타입 |
|---|---|---|---|
| router | const | `router = APIRouter(prefix="/dong", tags=["dong"])` | APIRouter |
| get_dong_list | function | `def get_dong_list(query: Annotated[DongSummaryQuery, Query()]) -> DongSummaryResponse` | DongSummaryResponse |

## 4. 의존성(imports)

- 표준 라이브러리:
  - `from typing import Annotated`
- 서드파티:
  - `from fastapi import APIRouter, HTTPException, Query`
- 내부 모듈:
  - `from app.schemas.dong_summary import DongSummaryQuery, DongSummaryResponse`
  - `from app.services import dong_summary_service`

파일 최상단 주석(1행): `# 동별 데이터 그룹 집계 조회 api`

## 5. 로직 상세

### router

- 목적: `/dong` prefix, `dong` 태그의 라우터 생성.
- 처리 흐름: `router = APIRouter(prefix="/dong", tags=["dong"])`.
- 반환값: 해당 없음.

### get_dong_list

- 목적(원문 docstring): "region_cgg 미지정 시 자치구(cgg_cd)별로, 지정 시 해당 자치구 내 법정동(stdg_cd)별로 그룹화하여 그룹별 평균 매매가/평균 평당가/total_count를 조회한다."
- 데코레이터: `@router.get("/list", response_model=DongSummaryResponse)`.
- 파라미터: `query: Annotated[DongSummaryQuery, Query()]` — FastAPI Query 파라미터로 바인딩되는 `DongSummaryQuery` 스키마.
- 처리 흐름:
  1. `try:` 블록에서 `base_date, groups = dong_summary_service.get_dong_summary(region_cgg=query.region_cgg)` 호출.
  2. `except FileNotFoundError as exc:` 이면 `raise HTTPException(status_code=404, detail=str(exc)) from exc`.
  3. `return DongSummaryResponse(base_date=base_date, groups=groups)`.
- 반환값: 성공 시 `DongSummaryResponse(base_date=base_date, groups=groups)`. 서비스가 `FileNotFoundError`를 던지면 상태코드 404, `detail`은 예외 메시지 문자열.

## 6. 모듈 레벨 상수/설정값

없음.

## 7. 역참조(이 파일을 사용하는 곳)

- `app/api/v1/router.py` — `from app.api.v1.endpoints import (..., dong_summary, ...)` 후 `router.include_router(dong_summary.router)`로 등록.

## 8. 재생성 지침

> 위 내용을 근거로 `backend_fastApi/app/api/v1/endpoints/dong_summary.py` 파일을 동일한 로직으로 재작성하라. 여기 명시되지 않은 세부 구현(변수명 스타일, 코드 포맷 등)은 기존 프로젝트 컨벤션(PEP 8, 저장소 내 동일 계층 파일들의 스타일)을 따른다.
