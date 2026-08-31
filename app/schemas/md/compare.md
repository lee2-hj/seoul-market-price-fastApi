# compare.py 명세

## 1. 메타 정보

| 항목 | 값 |
|---|---|
| source_path | backend_fastApi/app/schemas/compare.py |
| source_sha256 | ea6704d7393458099c86134a3e4b3cf1766f12b7fcb760a157661998fefbc148 |
| source_lines | 38 |

## 2. 역할 요약

`GET /api/v1/compare/dong-pyeong`의 요청 Query 스키마(`DongPyeongCompareQuery`), 단일 지역 결과 스키마(`RegionCompareResult`), 응답 스키마(`DongPyeongCompareResponse`)를 정의한다.

## 3. 외부 인터페이스

| 이름 | 종류 | 시그니처 | 반환 타입 |
|---|---|---|---|
| DongPyeongCompareQuery | class | `class DongPyeongCompareQuery(BaseModel)` | - |
| RegionCompareResult | class | `class RegionCompareResult(BaseModel)` | - |
| DongPyeongCompareResponse | class | `class DongPyeongCompareResponse(BaseModel)` | - |

**DongPyeongCompareQuery 필드 목록(클래스 정의 순서)**

| 필드명 | 타입 | 기본값 | Field 설명 |
|---|---|---|---|
| region1_cgg_cd | str | 없음(필수, `...`) | `Field(..., min_length=1, description="지역1 자치구코드", examples=["11680"])` |
| region1_stdg_cd | str \| None | `None` | `Field(default=None, min_length=1, description="지역1 법정동코드", examples=["10300"])` |
| region2_cgg_cd | str | 없음(필수, `...`) | `Field(..., min_length=1, description="지역2 자치구코드", examples=["11650"])` |
| region2_stdg_cd | str \| None | `None` | `Field(default=None, min_length=1, description="지역2 법정동코드", examples=["10700"])` |

**RegionCompareResult 필드 목록(클래스 정의 순서)**

| 필드명 | 타입 | 기본값 | Field 설명 |
|---|---|---|---|
| cgg_cd | str | 없음(필수, `...`) | `Field(..., description="요청받은 자치구코드")` |
| stdg_cd | str \| None | `None` | `Field(default=None, description="요청받은 법정동코드")` |
| base_date | str | 없음(필수, `...`) | `Field(..., description="이 지역 조회에 실제 사용된 base_date")` |
| total_count | int | 없음(필수, `...`) | `Field(..., description="해당 지역의 전체 거래건수 합계")` |
| avg_thing_amt | int | 없음(필수, `...`) | `Field(..., description="해당 지역의 평균 매매가(SUM(total_thing_amt) / total_count, 반올림)")` |
| avg_pyeong_amt | int | 없음(필수, `...`) | `Field(..., description="해당 지역의 평균 평당가(SUM(total_pyeong_amt) / total_count, 반올림)")` |
| latitude | float \| None | `None` | `Field(default=None, description="해당 지역 대표 위도(그룹 내 첫 row 기준)")` |
| longitude | float \| None | `None` | `Field(default=None, description="해당 지역 대표 경도(그룹 내 첫 row 기준)")` |

**DongPyeongCompareResponse 필드 목록(클래스 정의 순서)**

| 필드명 | 타입 | 기본값 | Field 설명 |
|---|---|---|---|
| base_date | str | 없음(필수, `...`) | `Field(..., description=("하위 호환용 대표 base_date(region1.base_date/region2.base_date 중 더 최신 날짜). " "지역1/지역2는 서로 다른 base_date로 소급될 수 있으므로 정확한 값이 필요하면 " "region1.base_date/region2.base_date를 사용할 것"))` |
| region1 | RegionCompareResult | 없음(필수, 타입힌트만 있고 Field 미사용) | 없음(Field 미사용) |
| region2 | RegionCompareResult | 없음(필수, 타입힌트만 있고 Field 미사용) | 없음(Field 미사용) |

## 4. 의존성(imports)

- 표준 라이브러리: 없음
- 서드파티:
  - `from pydantic import BaseModel, Field`
- 내부 모듈: 없음

## 5. 로직 상세

### DongPyeongCompareQuery

- 목적(원문 docstring): "`GET /api/v1/compare/dong-pyeong` 요청 Query Parameter."
- 필드: 위 표 참조. 검증 로직 없음.

### RegionCompareResult

- 목적(원문 docstring): "단일 지역(자치구+자치동)에 대한 시세 조회 결과."
- 필드: 위 표 참조. 검증 로직 없음.

### DongPyeongCompareResponse

- 목적(원문 docstring): "`GET /api/v1/compare/dong-pyeong` 응답 스키마."
- 필드: 위 표 참조(`region1`/`region2`는 `Field(...)` 없이 타입 어노테이션만으로 필수 필드가 됨). 검증 로직 없음.

## 6. 모듈 레벨 상수/설정값

없음.

## 7. 역참조(이 파일을 사용하는 곳)

- `app/api/v1/endpoints/compare.py` — `from app.schemas.compare import (DongPyeongCompareQuery, DongPyeongCompareResponse, RegionCompareResult,)`.

## 8. 재생성 지침

> 위 내용을 근거로 `backend_fastApi/app/schemas/compare.py` 파일을 동일한 로직으로 재작성하라. 여기 명시되지 않은 세부 구현(변수명 스타일, 코드 포맷 등)은 기존 프로젝트 컨벤션(PEP 8, 저장소 내 동일 계층 파일들의 스타일)을 따른다.
