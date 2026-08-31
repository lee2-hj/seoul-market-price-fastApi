# apt_compare.py 명세

## 1. 메타 정보

| 항목 | 값 |
|---|---|
| source_path | backend_fastApi/app/schemas/apt_compare.py |
| source_sha256 | 269df5b614eb724892880b54b5eff30b19412f1af4bb466428e95f000b6fb1c6 |
| source_lines | 87 |

## 2. 역할 요약

`GET /api/v1/apt-price/apt-compare`의 요청 Query 스키마(`AptCompareQuery`, `grp`/`grp2` 값을 `query_type`에 따라 교차 검증), 그룹 비교 지표 스키마(`AptCompareGroup`), 응답 스키마(`AptCompareResponse`)와 `QueryType` 타입 별칭·허용 그룹값 상수 2개를 정의한다.

## 3. 외부 인터페이스

| 이름 | 종류 | 시그니처 | 반환 타입 |
|---|---|---|---|
| QueryType | const | `QueryType = Literal["pyeong", "floor"]` | type alias |
| PYEONG_GRP_VALUES | const | `PYEONG_GRP_VALUES = {"10", "20", "30", "40"}` | set[str] |
| FLOOR_GRP_VALUES | const | `FLOOR_GRP_VALUES = {"LOW", "MID", "HIGH"}` | set[str] |
| AptCompareQuery | class | `class AptCompareQuery(BaseModel)` | - |
| AptCompareGroup | class | `class AptCompareGroup(BaseModel)` | - |
| AptCompareResponse | class | `class AptCompareResponse(BaseModel)` | - |

**AptCompareQuery 필드 목록(클래스 정의 순서)**

| 필드명 | 타입 | 기본값 | Field 설명 |
|---|---|---|---|
| cgg_cd | str | 없음(필수, `...`) | `Field(..., pattern=r"^\d{5}$", description="자치구코드(5자리)", examples=["11500"])` |
| stdg_cd | str | 없음(필수, `...`) | `Field(..., pattern=r"^\d{5}$", description="법정동코드(5자리)", examples=["10300"])` |
| bldg_nm | str \| None | `None` | `Field(default=None, min_length=1, description="건물명(아파트명, 선택)", examples=["강서힐스테이트"])` |
| mno | str | 없음(필수, `...`) | `Field(..., min_length=1, description="지번 본번", examples=["123"])` |
| sno | str | 없음(필수, `...`) | `Field(..., min_length=1, description="지번 부번", examples=["4"])` |
| query_type | QueryType | 없음(필수, `...`) | `Field(..., description="조회 타입. 'pyeong'=평단가(dm_apt_pyeong_price), 'floor'=층별가(dm_apt_flr_price)", examples=["pyeong"])` |
| grp | str | 없음(필수, `...`) | `Field(..., description=("그룹 필터(필수). query_type='pyeong'이면 10/20/30/40 중 하나(40은 40평 이상 포함), " "query_type='floor'이면 LOW/MID/HIGH 중 하나."), examples=["30"])` |
| grp2 | str | 없음(필수, `...`) | `Field(..., description=("그룹 필터2(필수). grp와 동일한 방식으로 받으며, query_type='pyeong'이면 10/20/30/40 중 하나" "(40은 40평 이상 포함), query_type='floor'이면 LOW/MID/HIGH 중 하나."), examples=["40"])` |

**AptCompareGroup 필드 목록(클래스 정의 순서)**

| 필드명 | 타입 | 기본값 | Field 설명 |
|---|---|---|---|
| pyeong_grp | str \| None | `None` | `Field(default=None, description="평형 그룹(query_type='pyeong'일 때만 존재)")` |
| flr_grp | str \| None | `None` | `Field(default=None, description="층 그룹(query_type='floor'일 때만 존재)")` |
| deal_cnt | int | 없음(필수, `...`) | `Field(..., description="거래건수")` |
| avg_thing_amt | int | 없음(필수, `...`) | `Field(..., description="평균 거래가(total_thing_amt/deal_cnt, 반올림한 정수)")` |
| avg_pyeong_amt | int | 없음(필수, `...`) | `Field(..., description="평균 평당가(total_pyeong_amt/deal_cnt, 반올림한 정수)")` |
| recent_thing_amt | int \| None | `None` | `Field(default=None, description="최근 거래가")` |
| recent_pyeong_amt | int \| None | `None` | `Field(default=None, description="최근 평당가")` |
| recent_deal_date | str \| None | `None` | `Field(default=None, description="최근 거래일")` |
| recent_supply_pyeong | int \| None | `None` | `Field(default=None, description="최근 공급면적(평, 반올림한 정수, query_type='pyeong'일 때만 존재)")` |
| recent_floor | int \| None | `None` | `Field(default=None, description="최근 거래 층수(query_type='floor'일 때만 존재)")` |

**AptCompareResponse 필드 목록(클래스 정의 순서)**

| 필드명 | 타입 | 기본값 | Field 설명 |
|---|---|---|---|
| base_date | str | 없음(필수, `...`) | `Field(..., description="마트 최신 파티션 기준일")` |
| cgg_cd | str | 없음(필수, `...`) | `Field(..., description="자치구코드")` |
| cgg_nm | str \| None | `None` | `Field(default=None, description="자치구명")` |
| stdg_cd | str | 없음(필수, `...`) | `Field(..., description="법정동코드")` |
| stdg_nm | str \| None | `None` | `Field(default=None, description="법정동명")` |
| bldg_nm | str \| None | `None` | `Field(default=None, description="건물명(아파트명)")` |
| latitude | float \| None | `None` | `Field(default=None, description="위도")` |
| longitude | float \| None | `None` | `Field(default=None, description="경도")` |
| is_exact_location | bool \| None | `None` | `Field(default=None, description="정확한 좌표 여부")` |
| updated_at | datetime \| None | `None` | `Field(default=None, description="데이터 갱신 시각")` |
| grp | AptCompareGroup \| None | `None` | `Field(default=None, description="grp 파라미터로 조회한 그룹 지표")` |
| grp2 | AptCompareGroup \| None | `None` | `Field(default=None, description="grp2 파라미터로 조회한 그룹 지표")` |

## 4. 의존성(imports)

- 표준 라이브러리:
  - `from datetime import datetime`
  - `from typing import Literal`
- 서드파티:
  - `from pydantic import BaseModel, Field, model_validator`
- 내부 모듈: 없음

## 5. 로직 상세

### QueryType

- 목적: `query_type` 필드의 허용값을 제한하는 타입 별칭.
- 값: `Literal["pyeong", "floor"]`.

### PYEONG_GRP_VALUES

- 목적: `query_type="pyeong"`일 때 `grp`/`grp2`에 허용되는 값 집합.
- 값: `{"10", "20", "30", "40"}`.

### FLOOR_GRP_VALUES

- 목적: `query_type="floor"`일 때 `grp`/`grp2`에 허용되는 값 집합.
- 값: `{"LOW", "MID", "HIGH"}`.

### AptCompareQuery

- 목적(원문 docstring): "`GET /api/v1/apt-price/apt-compare` 요청 Query Parameter."
- 필드: 위 표 참조.
- 검증 로직(`_validate_grp`, `@model_validator(mode="after")`):
  - 목적: `grp`/`grp2` 값이 `query_type`에 대응하는 허용 집합에 속하는지 검증.
  - 시그니처: `def _validate_grp(self) -> "AptCompareQuery"`.
  - 처리 흐름:
    1. `allowed = PYEONG_GRP_VALUES if self.query_type == "pyeong" else FLOOR_GRP_VALUES`.
    2. `if self.grp not in allowed:` 이면 `raise ValueError(f"query_type='{self.query_type}'일 때 grp는 {sorted(allowed)} 중 하나여야 합니다.")`.
    3. `if self.grp2 not in allowed:` 이면 `raise ValueError(f"query_type='{self.query_type}'일 때 grp2는 {sorted(allowed)} 중 하나여야 합니다.")`.
    4. `return self`.
  - 반환값: 검증 통과 시 `self`(모델 인스턴스). 검증 실패 시 `ValueError` 발생(pydantic이 이를 `ValidationError`로 감쌈).

### AptCompareGroup

- 목적(원문 docstring): "grp/grp2 각각에 대응하는 거래/비교 지표(단지 공통 정보 제외)."
- 필드: 위 표 참조. 검증 로직 없음.

### AptCompareResponse

- 목적(원문 docstring): "`GET /api/v1/apt-price/apt-compare` 응답: 단지 공통 정보는 최상위, grp/grp2는 각각 단일 객체."
- 필드: 위 표 참조. 검증 로직 없음.

## 6. 모듈 레벨 상수/설정값

| 이름 | 값 |
|---|---|
| QueryType | `Literal["pyeong", "floor"]` |
| PYEONG_GRP_VALUES | `{"10", "20", "30", "40"}` |
| FLOOR_GRP_VALUES | `{"LOW", "MID", "HIGH"}` |

## 7. 역참조(이 파일을 사용하는 곳)

- `app/api/v1/endpoints/apt_compare.py` — `from app.schemas.apt_compare import AptCompareGroup, AptCompareQuery, AptCompareResponse`.

## 8. 재생성 지침

> 위 내용을 근거로 `backend_fastApi/app/schemas/apt_compare.py` 파일을 동일한 로직으로 재작성하라. 여기 명시되지 않은 세부 구현(변수명 스타일, 코드 포맷 등)은 기존 프로젝트 컨벤션(PEP 8, 저장소 내 동일 계층 파일들의 스타일)을 따른다.
