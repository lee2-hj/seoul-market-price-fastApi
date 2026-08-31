# region_apt_compare.py 명세

## 1. 메타 정보

| 항목 | 값 |
|---|---|
| source_path | backend_fastApi/app/api/v1/endpoints/region_apt_compare.py |
| source_sha256 | b9ef0b8e2fec12072f5cd3ffca326880ce006c340924936468636d9451227c1b |
| source_lines | 37 |

## 2. 역할 요약

`/region-apt-compare` prefix 라우터를 정의하고, `GET /region-apt-compare`에서 `region_apt_compare_service.compare_region_apts`를 호출해 두 아파트의 비교 결과를 `RegionAptCompareResponse`로 반환한다.

## 3. 외부 인터페이스

| 이름 | 종류 | 시그니처 | 반환 타입 |
|---|---|---|---|
| router | const | `router = APIRouter(prefix="/region-apt-compare", tags=["region-apt-compare"])` | APIRouter |
| get_region_apt_compare | function | `def get_region_apt_compare(query: Annotated[RegionAptCompareQuery, Query()]) -> RegionAptCompareResponse` | RegionAptCompareResponse |

## 4. 의존성(imports)

- 표준 라이브러리:
  - `from typing import Annotated`
- 서드파티:
  - `from fastapi import APIRouter, HTTPException, Query`
- 내부 모듈:
  - `from app.schemas.region_apt_compare import RegionAptCompareQuery, RegionAptCompareResponse`
  - `from app.services import region_apt_compare_service`

파일 최상단 주석(1행): `# 지역별 아파트 비교(dm_apt_recent_trade 마트, 최근 90일 실거래 사전집계) 조회 api`

## 5. 로직 상세

### router

- 목적: `/region-apt-compare` prefix, `region-apt-compare` 태그의 라우터 생성.
- 처리 흐름: `router = APIRouter(prefix="/region-apt-compare", tags=["region-apt-compare"])`.
- 반환값: 해당 없음.

### get_region_apt_compare

- 목적(원문 docstring): "아파트1(cgg_cd_1/bjd_cd_1/apt_nm_1/mno_1/sno_1)과 아파트2(cgg_cd_2/bjd_cd_2/apt_nm_2/mno_2/sno_2)를 각각 자치구코드+법정동코드+아파트명+지번 본번/부번(모두 필수)으로 특정하여, dm_apt_recent_trade 마트의 최신 파티션(최근 90일 실거래 사전집계)에서 평균 매매가/평균 평당가/거래건수와 세대수/준공년도/사용승인일을 조회해 aptGroup1/aptGroup2로 나누어 반환한다. 매칭되는 단지가 없거나 최근 90일간 거래가 없으면 해당 그룹은 빈 객체({})로 반환된다(요청 자체는 404 처리하지 않음)."
- 데코레이터: `@router.get("", response_model=RegionAptCompareResponse)`.
- 파라미터: `query: Annotated[RegionAptCompareQuery, Query()]`.
- 처리 흐름:
  1. `try:` 블록에서 `group_1, group_2 = region_apt_compare_service.compare_region_apts(cgg_cd_1=query.cgg_cd_1, bjd_cd_1=query.bjd_cd_1, apt_nm_1=query.apt_nm_1, mno_1=query.mno_1, sno_1=query.sno_1, cgg_cd_2=query.cgg_cd_2, bjd_cd_2=query.bjd_cd_2, apt_nm_2=query.apt_nm_2, mno_2=query.mno_2, sno_2=query.sno_2)` 호출.
  2. `except FileNotFoundError as exc:` 이면 `raise HTTPException(status_code=404, detail=str(exc)) from exc`.
  3. `return RegionAptCompareResponse(aptGroup1=group_1, aptGroup2=group_2)`.
- 반환값: 성공 시 `RegionAptCompareResponse(aptGroup1=group_1, aptGroup2=group_2)`(각 그룹은 매칭 없으면 서비스 계층에서 빈 객체로 채워짐 — 이 파일 자체는 빈 값 여부로 분기하지 않음). 마트 파티션 자체가 없어 서비스가 `FileNotFoundError`를 던지면 404.

## 6. 모듈 레벨 상수/설정값

없음.

## 7. 역참조(이 파일을 사용하는 곳)

- `app/api/v1/router.py` — `from app.api.v1.endpoints import (..., region_apt_compare, ...)` 후 `router.include_router(region_apt_compare.router)`로 등록.

## 8. 재생성 지침

> 위 내용을 근거로 `backend_fastApi/app/api/v1/endpoints/region_apt_compare.py` 파일을 동일한 로직으로 재작성하라. 여기 명시되지 않은 세부 구현(변수명 스타일, 코드 포맷 등)은 기존 프로젝트 컨벤션(PEP 8, 저장소 내 동일 계층 파일들의 스타일)을 따른다.
