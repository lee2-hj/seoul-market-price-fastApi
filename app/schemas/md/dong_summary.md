# dong_summary.py 명세

## 1. 메타 정보

| 항목 | 값 |
|---|---|
| source_path | backend_fastApi/app/schemas/dong_summary.py |
| source_sha256 | 131d5d911d72b3689832beadd6ba7a10808e3a29968c669b5654acd9719564d0 |
| source_lines | 37 |

## 2. 역할 요약

`GET /api/v1/dong/list`의 요청 Query 스키마(`DongSummaryQuery`), 그룹 결과 스키마(`DongSummaryGroup`), 응답 스키마(`DongSummaryResponse`)를 정의하는 Pydantic `BaseModel` 3개로 구성된다.

## 3. 외부 인터페이스

| 이름 | 종류 | 시그니처 | 반환 타입 |
|---|---|---|---|
| DongSummaryQuery | class | `class DongSummaryQuery(BaseModel)` | - |
| DongSummaryGroup | class | `class DongSummaryGroup(BaseModel)` | - |
| DongSummaryResponse | class | `class DongSummaryResponse(BaseModel)` | - |

**DongSummaryQuery 필드 목록(클래스 정의 순서)**

| 필드명 | 타입 | 기본값 | Field 설명 |
|---|---|---|---|
| region_cgg | str \| None | `None` | `Field(default=None, description=("자치구명 또는 자치구코드(선택). " "미지정 시 전체 데이터를 자치구(cgg_cd)별로, 지정 시 해당 자치구 내 데이터를 법정동(stdg_cd)별로 그룹화한다."), examples=["강남구"])` |

**DongSummaryGroup 필드 목록(클래스 정의 순서)**

| 필드명 | 타입 | 기본값 | Field 설명 |
|---|---|---|---|
| code | str | 없음(필수, `...`) | `Field(..., description="그룹 기준 코드(region_cgg 미지정 시 cgg_cd, 지정 시 stdg_cd)")` |
| name | str | 없음(필수, `...`) | `Field(..., description="그룹 기준 명칭(region_cgg 미지정 시 cgg_nm, 지정 시 stdg_nm)")` |
| total_count | int | 없음(필수, `...`) | `Field(..., description="그룹 전체 거래건수 합계(SUM(deal_cnt))")` |
| avg_thing_amt | int | 없음(필수, `...`) | `Field(..., description="그룹 평균 매매가(SUM(total_thing_amt) / total_count, 반올림)")` |
| avg_pyeong_amt | int | 없음(필수, `...`) | `Field(..., description="그룹 평균 평당가(SUM(total_pyeong_amt) / total_count, 반올림)")` |

**DongSummaryResponse 필드 목록(클래스 정의 순서)**

| 필드명 | 타입 | 기본값 | Field 설명 |
|---|---|---|---|
| base_date | str | 없음(필수, `...`) | `Field(..., description="실제 조회에 사용된 mart 파티션의 base_date")` |
| groups | dict[str, DongSummaryGroup] | `default_factory=dict` | `Field(default_factory=dict, description=("그룹 코드(cgg_cd 또는 stdg_cd)를 key로 하는 단일 객체. " "region_cgg 미지정 시 cgg_cd별, 지정 시 stdg_cd별로 그룹화된다."))` |

## 4. 의존성(imports)

- 표준 라이브러리: 없음
- 서드파티:
  - `from pydantic import BaseModel, Field`
- 내부 모듈: 없음

## 5. 로직 상세

### DongSummaryQuery

- 목적(원문 docstring): "`GET /api/v1/dong/list` 요청 Query Parameter."
- 필드: 위 표 참조. 검증 로직(`@model_validator` 등) 없음.

### DongSummaryGroup

- 목적(원문 docstring): "cgg_cd 또는 stdg_cd 기준으로 그룹화된 결과."
- 필드: 위 표 참조. 검증 로직 없음.

### DongSummaryResponse

- 목적(원문 docstring): "`GET /api/v1/dong/list` 응답 스키마."
- 필드: 위 표 참조. 검증 로직 없음.

## 6. 모듈 레벨 상수/설정값

없음.

## 7. 역참조(이 파일을 사용하는 곳)

- `app/api/v1/endpoints/dong_summary.py` — `from app.schemas.dong_summary import DongSummaryQuery, DongSummaryResponse`.

## 8. 재생성 지침

> 위 내용을 근거로 `backend_fastApi/app/schemas/dong_summary.py` 파일을 동일한 로직으로 재작성하라. 여기 명시되지 않은 세부 구현(변수명 스타일, 코드 포맷 등)은 기존 프로젝트 컨벤션(PEP 8, 저장소 내 동일 계층 파일들의 스타일)을 따른다.
