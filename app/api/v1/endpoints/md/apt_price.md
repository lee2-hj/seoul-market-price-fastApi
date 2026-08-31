# apt_price.py 명세

## 1. 메타 정보

| 항목 | 값 |
|---|---|
| source_path | backend_fastApi/app/api/v1/endpoints/apt_price.py |
| source_sha256 | e25149d375608fb8d41967721126642390d53a66d2801ef79683991fe2e91693 |
| source_lines | 35 |

## 2. 역할 요약

`/apt-price` prefix 라우터를 정의하고, `GET /apt-price/top-bottom`에서 `apt_price_service.get_top_bottom`을 호출해 아파트 metric 기준 상/하위 5개 목록을 `AptPriceTopBottomResponse`로 반환한다.

## 3. 외부 인터페이스

| 이름 | 종류 | 시그니처 | 반환 타입 |
|---|---|---|---|
| router | const | `router = APIRouter(prefix="/apt-price", tags=["apt-price"])` | APIRouter |
| get_apt_price_top_bottom | function | `def get_apt_price_top_bottom(query: Annotated[AptPriceTopBottomQuery, Query()]) -> AptPriceTopBottomResponse` | AptPriceTopBottomResponse |

## 4. 의존성(imports)

- 표준 라이브러리:
  - `from typing import Annotated`
- 서드파티:
  - `from fastapi import APIRouter, HTTPException, Query`
- 내부 모듈:
  - `from app.schemas.apt_price import AptPriceTopBottomQuery, AptPriceTopBottomResponse`
  - `from app.services import apt_price_service`

파일 최상단 주석(1행): `# 아파트당 평균가격 api`

## 5. 로직 상세

### router

- 목적: `/apt-price` prefix, `apt-price` 태그의 라우터 생성.
- 처리 흐름: `router = APIRouter(prefix="/apt-price", tags=["apt-price"])`.
- 반환값: 해당 없음.

### get_apt_price_top_bottom

- 목적(원문 docstring): "지정된(선택적) 지역 내 아파트별 metric_type 기준(평균 평당가 또는 평균 거래가) 상위/하위 5개를 MinIO Parquet에서 동적 조회한다."
- 데코레이터: `@router.get("/top-bottom", response_model=AptPriceTopBottomResponse)`.
- 파라미터: `query: Annotated[AptPriceTopBottomQuery, Query()]`.
- 처리 흐름:
  1. `try:` 블록에서 `base_date, top_items, bottom_items, total_count, avg_thing_amt, avg_pyeong_amt = apt_price_service.get_top_bottom(region_cgg_cd=query.region_cgg_cd, region_stdg_cd=query.region_stdg_cd, metric_type=query.metric_type)` 호출(6개 값 언패킹).
  2. `except FileNotFoundError as exc:` 이면 `raise HTTPException(status_code=404, detail=str(exc)) from exc`.
  3. `return AptPriceTopBottomResponse(base_date=base_date, total_count=total_count, avg_thing_amt=avg_thing_amt, avg_pyeong_amt=avg_pyeong_amt, top=top_items, bottom=bottom_items)`.
- 반환값: 성공 시 위 6개 필드를 채운 `AptPriceTopBottomResponse`. 서비스가 `FileNotFoundError`를 던지면 상태코드 404, `detail`은 예외 메시지 문자열.

## 6. 모듈 레벨 상수/설정값

없음.

## 7. 역참조(이 파일을 사용하는 곳)

- `app/api/v1/router.py` — `from app.api.v1.endpoints import (..., apt_price, ...)` 후 `router.include_router(apt_price.router)`로 등록.

## 8. 재생성 지침

> 위 내용을 근거로 `backend_fastApi/app/api/v1/endpoints/apt_price.py` 파일을 동일한 로직으로 재작성하라. 여기 명시되지 않은 세부 구현(변수명 스타일, 코드 포맷 등)은 기존 프로젝트 컨벤션(PEP 8, 저장소 내 동일 계층 파일들의 스타일)을 따른다.
