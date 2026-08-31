# rtt.py 명세

## 1. 메타 정보

| 항목 | 값 |
|---|---|
| source_path | backend_fastApi/app/api/v1/endpoints/rtt.py |
| source_sha256 | fd0b82fff359306366564baaa5a86e555b16bfb48b54a9eaa317f9b9b05be34f |
| source_lines | 23 |

## 2. 역할 요약

`/rtt` prefix 라우터를 정의하고, `GET /rtt/summary`에서 `rtt_service.get_rtt_summary`를 호출해 최근 90일 실거래(RTT) 요약을 `RttSummaryResponse`로 반환한다.

## 3. 외부 인터페이스

| 이름 | 종류 | 시그니처 | 반환 타입 |
|---|---|---|---|
| router | const | `router = APIRouter(prefix="/rtt", tags=["rtt"])` | APIRouter |
| get_rtt_summary | function | `def get_rtt_summary(query: Annotated[RttSummaryQuery, Query()]) -> RttSummaryResponse` | RttSummaryResponse |

## 4. 의존성(imports)

- 표준 라이브러리:
  - `from typing import Annotated`
- 서드파티:
  - `from fastapi import APIRouter, Query`
- 내부 모듈:
  - `from app.schemas.rtt import RttSummaryQuery, RttSummaryResponse`
  - `from app.services import rtt_service`

파일 최상단 주석(1행): `# 동별 최근 90일 실거래(RTT) 요약 조회 api`

## 5. 로직 상세

### router

- 목적: `/rtt` prefix, `rtt` 태그의 라우터 생성.
- 처리 흐름: `router = APIRouter(prefix="/rtt", tags=["rtt"])`.
- 반환값: 해당 없음.

### get_rtt_summary

- 목적(원문 docstring): "시군구코드(sgg_cd, 필수)+법정동코드(dong_cd, 선택) 조건으로 오늘 기준 최근 90일간의 RTT 실거래 데이터를 집계하여 총 거래건수/총 거래금액/평균 거래가/최고 거래가/거래량 증감률과 함께 90일을 6구간으로 균등 분할한 거래량 추이, 평형별 거래 비중, 최근 실거래 목록, 거래량 상위 top5 단지를 단일 JSON으로 반환한다. dong_cd가 없으면 자치구 내 모든 법정동의 거래내역을 합산해 동일한 로직으로 계산하며, recent_trades 각 항목에는 자치구명/법정동명이 함께 채워진다."
- 데코레이터: `@router.get("/summary", response_model=RttSummaryResponse)`.
- 파라미터: `query: Annotated[RttSummaryQuery, Query()]`.
- 처리 흐름:
  1. `summary = rtt_service.get_rtt_summary(sgg_cd=query.sgg_cd, dong_cd=query.dong_cd)` 호출(예외 처리 없음 — try/except 블록 없음).
  2. `return RttSummaryResponse(**summary)`.
- 반환값: `rtt_service.get_rtt_summary`가 반환한 딕셔너리를 언패킹해 생성한 `RttSummaryResponse`. 이 함수 자체는 예외를 잡지 않음(서비스에서 예외가 발생하면 그대로 전파).

## 6. 모듈 레벨 상수/설정값

없음.

## 7. 역참조(이 파일을 사용하는 곳)

- `app/api/v1/router.py` — `from app.api.v1.endpoints import (..., rtt)` 후 `router.include_router(rtt.router)`로 등록.

## 8. 재생성 지침

> 위 내용을 근거로 `backend_fastApi/app/api/v1/endpoints/rtt.py` 파일을 동일한 로직으로 재작성하라. 여기 명시되지 않은 세부 구현(변수명 스타일, 코드 포맷 등)은 기존 프로젝트 컨벤션(PEP 8, 저장소 내 동일 계층 파일들의 스타일)을 따른다.
