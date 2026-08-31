# dashboard.py 명세

## 1. 메타 정보

| 항목 | 값 |
|---|---|
| source_path | backend_fastApi/app/api/v1/endpoints/dashboard.py |
| source_sha256 | 4aa580a3923b7b91328ff3d636edda6db738623092669e04a40f05e61221006c |
| source_lines | 23 |

## 2. 역할 요약

`/dashboard` prefix 라우터를 정의하고, `GET /dashboard`에서 `dashboard_service.get_dashboard`를 호출해 대시보드 6개 위젯 데이터를 `DashboardResponse`로 반환한다.

## 3. 외부 인터페이스

| 이름 | 종류 | 시그니처 | 반환 타입 |
|---|---|---|---|
| router | const | `router = APIRouter(prefix="/dashboard", tags=["dashboard"])` | APIRouter |
| get_dashboard | function | `def get_dashboard(query: Annotated[DashboardQuery, Query()]) -> DashboardResponse` | DashboardResponse |

## 4. 의존성(imports)

- 표준 라이브러리:
  - `from typing import Annotated`
- 서드파티:
  - `from fastapi import APIRouter, Query`
- 내부 모듈:
  - `from app.schemas.dashboard import DashboardQuery, DashboardResponse`
  - `from app.services import dashboard_service`

파일 최상단 주석(1행): `# 대시보드 6개 위젯(dm_apt_price_avg 마트, 최근 90일) 조회 api`

## 5. 로직 상세

### router

- 목적: `/dashboard` prefix, `dashboard` 태그의 라우터 생성.
- 처리 흐름: `router = APIRouter(prefix="/dashboard", tags=["dashboard"])`.
- 반환값: 해당 없음.

### get_dashboard

- 목적(원문 docstring): "dm_apt_price_avg 마트의 오늘 기준 최근 90일 데이터를 집계하여, 서울 자치구별 평균 매매가 Top5, 아파트 가격 상승/하락 Top5, 선호지역(cgg_cd) 실거래가 추이(4구간), 선호지역 거래량 상위 법정동 Top5, 선호지역 인기 법정동, 선호지역 아파트 거래량 Top5를 단일 JSON으로 반환한다. cgg_cd가 없거나 빈 값이면 '서울시 중구'(11140)로 대체한다. 선호지역 필터 위젯 3종은 그 지역 조건에 매칭되는 데이터가 있는 base_date까지 소급 조회하며(응답의 preference_base_date), 필터 없는 2개 위젯은 항상 최신 파티션을 사용한다."
- 데코레이터: `@router.get("", response_model=DashboardResponse)`.
- 파라미터: `query: Annotated[DashboardQuery, Query()]`.
- 처리 흐름:
  1. `summary = dashboard_service.get_dashboard(cgg_cd=query.cgg_cd)` 호출(예외 처리 없음 — try/except 블록 없음).
  2. `return DashboardResponse(**summary)`.
- 반환값: `dashboard_service.get_dashboard`가 반환한 딕셔너리를 언패킹해 생성한 `DashboardResponse`. 이 함수 자체는 예외를 잡지 않음(서비스에서 예외가 발생하면 그대로 전파).

## 6. 모듈 레벨 상수/설정값

없음.

## 7. 역참조(이 파일을 사용하는 곳)

- `app/api/v1/router.py` — `from app.api.v1.endpoints import (..., dashboard, ...)` 후 `router.include_router(dashboard.router)`로 등록.

## 8. 재생성 지침

> 위 내용을 근거로 `backend_fastApi/app/api/v1/endpoints/dashboard.py` 파일을 동일한 로직으로 재작성하라. 여기 명시되지 않은 세부 구현(변수명 스타일, 코드 포맷 등)은 기존 프로젝트 컨벤션(PEP 8, 저장소 내 동일 계층 파일들의 스타일)을 따른다.
