# apt_trend.py 명세

## 1. 메타 정보

| 항목 | 값 |
|---|---|
| source_path | backend_fastApi/app/api/v1/endpoints/apt_trend.py |
| source_sha256 | 044ce5c9ee5b88f8a65455d0329d572a291d3c95e8ee55fd92db022461094e81 |
| source_lines | 28 |

## 2. 역할 요약

`/apt-trend` prefix 라우터를 정의하고, `GET /apt-trend/summary`에서 `apt_trend_service.get_apt_trend_summary`를 호출해 최근 90일 실거래 트렌드 요약을 `AptTrendResponse`로 반환한다.

## 3. 외부 인터페이스

| 이름 | 종류 | 시그니처 | 반환 타입 |
|---|---|---|---|
| router | const | `router = APIRouter(prefix="/apt-trend", tags=["apt-trend"])` | APIRouter |
| get_apt_trend_summary | function | `def get_apt_trend_summary(query: Annotated[AptTrendQuery, Query()]) -> AptTrendResponse` | AptTrendResponse |

## 4. 의존성(imports)

- 표준 라이브러리:
  - `from typing import Annotated`
- 서드파티:
  - `from fastapi import APIRouter, Query`
- 내부 모듈:
  - `from app.schemas.apt_trend import AptTrendQuery, AptTrendResponse`
  - `from app.services import apt_trend_service`

파일 최상단 주석(1행): `# 아파트 실거래가 트렌드(최근 90일, apt_mkt_trends 마트) 조회 api`

## 5. 로직 상세

### router

- 목적: `/apt-trend` prefix, `apt-trend` 태그의 라우터 생성.
- 처리 흐름: `router = APIRouter(prefix="/apt-trend", tags=["apt-trend"])`.
- 반환값: 해당 없음.

### get_apt_trend_summary

- 목적(원문 docstring): "cgg_cd/stdg_cd/mno/sno/apt_name(모두 선택) 조건으로 오늘 기준 최근 90일간의 apt_mkt_trends 실거래 데이터를 단지(cgg_cd+stdg_cd+apt_name) 단위로 집계하여, 총 거래건수/총 거래금액/평균 거래가/최고 거래가와 함께 2주 단위 거래 추이, 전용면적별 거래 비율, 최근 실거래 내역, 면적별 요약 통계를 단일 JSON으로 반환한다. apt_name은 apt_mkt_trends의 실제 컬럼을 다른 마트 참조 없이 SQL WHERE(ILIKE)에서 직접 부분일치 검색하며, 매칭되는 데이터가 없으면 빈 결과를 그대로 반환한다."
- 데코레이터: `@router.get("/summary", response_model=AptTrendResponse)`.
- 파라미터: `query: Annotated[AptTrendQuery, Query()]`.
- 처리 흐름:
  1. `summary = apt_trend_service.get_apt_trend_summary(cgg_cd=query.cgg_cd, stdg_cd=query.stdg_cd, mno=query.mno, sno=query.sno, apt_name=query.apt_name)` 호출(예외 처리 없음 — try/except 블록이 이 함수에는 없음).
  2. `return AptTrendResponse(**summary)`.
- 반환값: `apt_trend_service.get_apt_trend_summary`가 반환한 딕셔너리를 언패킹해 생성한 `AptTrendResponse`. 이 함수 자체는 예외를 잡지 않음(서비스에서 예외가 발생하면 그대로 전파).

## 6. 모듈 레벨 상수/설정값

없음.

## 7. 역참조(이 파일을 사용하는 곳)

- `app/api/v1/router.py` — `from app.api.v1.endpoints import (..., apt_trend, ...)` 후 `router.include_router(apt_trend.router)`로 등록.

## 8. 재생성 지침

> 위 내용을 근거로 `backend_fastApi/app/api/v1/endpoints/apt_trend.py` 파일을 동일한 로직으로 재작성하라. 여기 명시되지 않은 세부 구현(변수명 스타일, 코드 포맷 등)은 기존 프로젝트 컨벤션(PEP 8, 저장소 내 동일 계층 파일들의 스타일)을 따른다.
