# real_estate.py 명세

## 1. 메타 정보

| 항목 | 값 |
|---|---|
| source_path | backend_fastApi/app/api/v1/endpoints/real_estate.py |
| source_sha256 | 13fbca0c6bd2bafbeae0315234725054232bf38357de3c38787e91dbdc5c1b88 |
| source_lines | 19 |

## 2. 역할 요약

`/real-estate` prefix 라우터를 정의하고, `GET /real-estate/latest`에서 `real_estate_service.get_latest_listings`를 호출해 RAW 아파트 실거래 최신 목록을 `RealEstateLatestResponse`로 반환한다.

## 3. 외부 인터페이스

| 이름 | 종류 | 시그니처 | 반환 타입 |
|---|---|---|---|
| router | const | `router = APIRouter(prefix="/real-estate", tags=["real-estate"])` | APIRouter |
| get_real_estate_latest | function | `def get_real_estate_latest() -> RealEstateLatestResponse` | RealEstateLatestResponse |

## 4. 의존성(imports)

- 표준 라이브러리: 없음
- 서드파티:
  - `from fastapi import APIRouter, HTTPException`
- 내부 모듈:
  - `from app.schemas.real_estate import RealEstateLatestResponse`
  - `from app.services import real_estate_service`

파일 최상단 주석(1행): `# RAW 아파트 실거래 최신 목록 조회 api`

## 5. 로직 상세

### router

- 목적: `/real-estate` prefix, `real-estate` 태그의 라우터 생성.
- 처리 흐름: `router = APIRouter(prefix="/real-estate", tags=["real-estate"])`.
- 반환값: 해당 없음.

### get_real_estate_latest

- 목적(원문 docstring): "RAW 버킷(real_estate/year=yyyy/month=MM/day=dd)에서 오늘(없으면 가장 최근) 파티션의 아파트 실거래 원본 목록을 조회한다."
- 데코레이터: `@router.get("/latest", response_model=RealEstateLatestResponse)`.
- 파라미터: 없음.
- 처리 흐름:
  1. `try:` 블록에서 `base_date, items = real_estate_service.get_latest_listings()` 호출.
  2. `except FileNotFoundError as exc:` 이면 `raise HTTPException(status_code=404, detail=str(exc)) from exc`.
  3. `return RealEstateLatestResponse(base_date=base_date, count=len(items), items=items)`.
- 반환값: 성공 시 `RealEstateLatestResponse(base_date=base_date, count=len(items), items=items)`(`count`는 `items` 길이로 계산). 파티션이 없어 서비스가 `FileNotFoundError`를 던지면 404, `detail`은 예외 메시지 문자열.

## 6. 모듈 레벨 상수/설정값

없음.

## 7. 역참조(이 파일을 사용하는 곳)

- `app/api/v1/router.py` — `from app.api.v1.endpoints import (..., real_estate, ...)` 후 `router.include_router(real_estate.router)`로 등록.

## 8. 재생성 지침

> 위 내용을 근거로 `backend_fastApi/app/api/v1/endpoints/real_estate.py` 파일을 동일한 로직으로 재작성하라. 여기 명시되지 않은 세부 구현(변수명 스타일, 코드 포맷 등)은 기존 프로젝트 컨벤션(PEP 8, 저장소 내 동일 계층 파일들의 스타일)을 따른다.
