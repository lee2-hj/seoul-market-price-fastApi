# region_apt_compare.py 명세

## 1. 메타 정보

| 항목 | 값 |
|---|---|
| source_path | backend_fastApi/app/schemas/region_apt_compare.py |
| source_sha256 | 373898428d30c2b8f0aebabe82729341dbadbb17a342e0b41b753683585d5f85 |
| source_lines | 47 |

## 2. 역할 요약

`GET /api/v1/region-apt-compare`의 요청 Query 스키마(`RegionAptCompareQuery`), 단지 비교 항목 스키마(`RegionAptCompareItem`), 응답 스키마(`RegionAptCompareResponse`)를 정의한다.

## 3. 외부 인터페이스

| 이름 | 종류 | 시그니처 | 반환 타입 |
|---|---|---|---|
| RegionAptCompareQuery | class | `class RegionAptCompareQuery(BaseModel)` | - |
| RegionAptCompareItem | class | `class RegionAptCompareItem(BaseModel)` | - |
| RegionAptCompareResponse | class | `class RegionAptCompareResponse(BaseModel)` | - |

**RegionAptCompareQuery 필드 목록(클래스 정의 순서)**

| 필드명 | 타입 | 기본값 | Field 설명 |
|---|---|---|---|
| cgg_cd_1 | str | 없음(필수, `...`) | `Field(..., description="아파트1 자치구코드", examples=["11500"])` |
| bjd_cd_1 | str | 없음(필수, `...`) | `Field(..., description="아파트1 법정동코드", examples=["10300"])` |
| apt_nm_1 | str | 없음(필수, `...`) | `Field(..., description="아파트1 아파트명", examples=["강서힐스테이트"])` |
| mno_1 | str | 없음(필수, `...`) | `Field(..., description="아파트1 지번 본번", examples=["661"])` |
| sno_1 | str | 없음(필수, `...`) | `Field(..., description="아파트1 지번 부번", examples=["0"])` |
| cgg_cd_2 | str | 없음(필수, `...`) | `Field(..., description="아파트2 자치구코드", examples=["11500"])` |
| bjd_cd_2 | str | 없음(필수, `...`) | `Field(..., description="아파트2 법정동코드", examples=["10300"])` |
| apt_nm_2 | str | 없음(필수, `...`) | `Field(..., description="아파트2 아파트명", examples=["마곡엠밸리7단지"])` |
| mno_2 | str | 없음(필수, `...`) | `Field(..., description="아파트2 지번 본번", examples=["1398"])` |
| sno_2 | str | 없음(필수, `...`) | `Field(..., description="아파트2 지번 부번", examples=["0"])` |

**RegionAptCompareItem 필드 목록(클래스 정의 순서)**

| 필드명 | 타입 | 기본값 | Field 설명 |
|---|---|---|---|
| apt_name | str | 없음(필수, `...`) | `Field(..., description="아파트명")` |
| base_date | str | 없음(필수, `...`) | `Field(..., description="이 단지 조회에 실제 사용된 base_date")` |
| avg_deal_price | int | 없음(필수, `...`) | `Field(..., description="최근 90일 평균 매매가(만원, 반올림한 정수)")` |
| avg_pyeong_price | int | 없음(필수, `...`) | `Field(..., description="최근 90일 평균 평당가(만원, 반올림한 정수)")` |
| avg_pyeong | int | 없음(필수, `...`) | `Field(..., description="최근 90일 평균 거래 전용면적(평, 반올림한 정수)")` |
| latest_trade_pyeong | int \| None | `None` | `Field(default=None, description="최근 거래 전용면적(평, 반올림한 정수)")` |
| deal_count | int | 없음(필수, `...`) | `Field(..., description="최근 90일 거래건수")` |
| total_households | int \| None | `None` | `Field(default=None, description="세대수")` |
| build_year | int \| None | `None` | `Field(default=None, description="준공년도")` |
| use_approval_date | str \| None | `None` | `Field(default=None, description="사용승인일")` |

**RegionAptCompareResponse 필드 목록(클래스 정의 순서)**

| 필드명 | 타입 | 기본값 | Field 설명 |
|---|---|---|---|
| aptGroup1 | RegionAptCompareItem \| dict[str, Any] | 없음(필수, `...`) | `Field(..., description="아파트1 비교 지표(없으면 {})")` |
| aptGroup2 | RegionAptCompareItem \| dict[str, Any] | 없음(필수, `...`) | `Field(..., description="아파트2 비교 지표(없으면 {})")` |

## 4. 의존성(imports)

- 표준 라이브러리:
  - `from typing import Any`
- 서드파티:
  - `from pydantic import BaseModel, Field`
- 내부 모듈: 없음

## 5. 로직 상세

### RegionAptCompareQuery

- 목적(원문 docstring): "`GET /api/v1/region-apt-compare` 요청 Query Parameter. 아파트1/아파트2를 각각 자치구코드+법정동코드+아파트명+지번 본번/부번(모두 필수)으로 특정한다. 같은 법정동 안에 동명 단지가 존재할 수 있어 mno/sno까지 포함해 정확히 매칭한다."
- 필드: 위 표 참조. 검증 로직 없음.

### RegionAptCompareItem

- 목적(원문 docstring): "단지 하나의 비교 지표 + 메타데이터. 최근 90일간 거래가 없는(매칭되는 단지가 없는) 경우, 이 모델 대신 빈 객체({})가 내려간다(RegionAptCompareResponse.aptGroup1/aptGroup2 참고)."
- 필드: 위 표 참조. 검증 로직 없음.

### RegionAptCompareResponse

- 목적(원문 docstring): "`GET /api/v1/region-apt-compare` 응답: 아파트1/아파트2 비교 지표를 aptGroup1/aptGroup2로 분리해 반환한다. 최근 90일간 거래가 없는(매칭되는 단지가 없는) 그룹은 RegionAptCompareItem 대신 빈 객체({})로 내려간다."
- 필드: 위 표 참조(`aptGroup1`/`aptGroup2`는 Union 타입 `RegionAptCompareItem | dict[str, Any]`). 검증 로직 없음.

## 6. 모듈 레벨 상수/설정값

없음.

## 7. 역참조(이 파일을 사용하는 곳)

- `app/api/v1/endpoints/region_apt_compare.py` — `from app.schemas.region_apt_compare import RegionAptCompareQuery, RegionAptCompareResponse`.

## 8. 재생성 지침

> 위 내용을 근거로 `backend_fastApi/app/schemas/region_apt_compare.py` 파일을 동일한 로직으로 재작성하라. 여기 명시되지 않은 세부 구현(변수명 스타일, 코드 포맷 등)은 기존 프로젝트 컨벤션(PEP 8, 저장소 내 동일 계층 파일들의 스타일)을 따른다.
