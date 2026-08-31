# router.py 명세

## 1. 메타 정보

| 항목 | 값 |
|---|---|
| source_path | backend_fastApi/app/api/v1/router.py |
| source_sha256 | 03dace93cb5771afb30c796cddaeddb91a218c99b9b25fdbb1c627fe730bf28d |
| source_lines | 24 |

## 2. 역할 요약

`/api/v1` prefix를 가진 최상위 `APIRouter`를 생성하고, `app.api.v1.endpoints` 하위 9개 모듈(`compare, apt_price, dong_summary, apt_compare, rtt, apt_trend, region_apt_compare, dashboard, real_estate`)의 라우터를 등록한다.

## 3. 외부 인터페이스

| 이름 | 종류 | 시그니처 | 반환 타입 |
|---|---|---|---|
| router | const | `router = APIRouter(prefix="/api/v1")` | APIRouter |

## 4. 의존성(imports)

- 표준 라이브러리: 없음
- 서드파티:
  - `from fastapi import APIRouter`
- 내부 모듈:
  - `from app.api.v1.endpoints import (apt_compare, apt_price, apt_trend, compare, dashboard, dong_summary, real_estate, region_apt_compare, rtt,)` (하나의 import 문에서 알파벳순으로 나열됨: apt_compare, apt_price, apt_trend, compare, dashboard, dong_summary, real_estate, region_apt_compare, rtt)

## 5. 로직 상세

### router

- 목적: `/api/v1` prefix로 하위 9개 엔드포인트 라우터를 통합하는 최상위 라우터.
- 파라미터: 없음(모듈 레벨 실행 코드).
- 처리 흐름:
  1. `router = APIRouter(prefix="/api/v1")`로 라우터 생성.
  2. 아래 순서(소스 코드에 나열된 순서, import 알파벳순과 다름)대로 `router.include_router(...)` 호출:
     1. `router.include_router(compare.router)`
     2. `router.include_router(apt_price.router)`
     3. `router.include_router(dong_summary.router)`
     4. `router.include_router(apt_compare.router)`
     5. `router.include_router(rtt.router)`
     6. `router.include_router(apt_trend.router)`
     7. `router.include_router(region_apt_compare.router)`
     8. `router.include_router(dashboard.router)`
     9. `router.include_router(real_estate.router)`
- 반환값: 해당 없음(모듈 레벨 변수 `router`가 결과물).

## 6. 모듈 레벨 상수/설정값

없음(모듈 레벨의 유일한 값인 `router`는 3항 외부 인터페이스 표에 이미 기재).

## 7. 역참조(이 파일을 사용하는 곳)

- `app/main.py` — `from app.api.v1.router import router as api_v1_router` 후 `app.include_router(api_v1_router)`로 등록.

## 8. 재생성 지침

> 위 내용을 근거로 `backend_fastApi/app/api/v1/router.py` 파일을 동일한 로직으로 재작성하라. 여기 명시되지 않은 세부 구현(변수명 스타일, 코드 포맷 등)은 기존 프로젝트 컨벤션(PEP 8, 저장소 내 동일 계층 파일들의 스타일)을 따른다.
