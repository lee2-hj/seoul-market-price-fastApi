# apt_price.py 명세

## 1. 메타 정보

| 항목 | 값 |
|---|---|
| source_path | backend_fastApi/app/schemas/apt_price.py |
| source_sha256 | c0e9c825e1c04573ee912985bf7d54796330a123c87ce553c83b87b9015f8916 |
| source_lines | 63 |

## 2. 역할 요약

`GET /api/v1/apt-price/top-bottom`의 요청 Query 스키마(`AptPriceTopBottomQuery`), 아파트별 row 스키마(`AptPriceItem`), 응답 스키마(`AptPriceTopBottomResponse`)와 `MetricType` 타입 별칭을 정의한다.

## 3. 외부 인터페이스

| 이름 | 종류 | 시그니처 | 반환 타입 |
|---|---|---|---|
| MetricType | const | `MetricType = Literal["pyeong", "thing_amt"]` | type alias |
| AptPriceTopBottomQuery | class | `class AptPriceTopBottomQuery(BaseModel)` | - |
| AptPriceItem | class | `class AptPriceItem(BaseModel)` | - |
| AptPriceTopBottomResponse | class | `class AptPriceTopBottomResponse(BaseModel)` | - |

**AptPriceTopBottomQuery 필드 목록(클래스 정의 순서)**

| 필드명 | 타입 | 기본값 | Field 설명 |
|---|---|---|---|
| region_cgg_cd | str \| None | `None` | `Field(default=None, pattern=r"^\d{5}$", description="자치구코드(5자리, 선택)", examples=["11680"])` |
| region_stdg_cd | str \| None | `None` | `Field(default=None, pattern=r"^\d{5}$", description="법정동코드(5자리, 선택)", examples=["10600"])` |
| metric_type | MetricType | `"pyeong"` | `Field(default="pyeong", description="정렬 기준. 'pyeong'=평균 평당가(avg_pyeong_amt), 'thing_amt'=평균 거래가(avg_thing_amt)", examples=["pyeong"])` |

**AptPriceItem 필드 목록(클래스 정의 순서)**

| 필드명 | 타입 | 기본값 | Field 설명 |
|---|---|---|---|
| base_date | date | 없음(필수, `...`) | `Field(..., description="파티션 기준일자")` |
| cgg_cd | str | 없음(필수, `...`) | `Field(..., description="자치구코드")` |
| cgg_nm | str | 없음(필수, `...`) | `Field(..., description="자치구명")` |
| stdg_cd | str | 없음(필수, `...`) | `Field(..., description="법정동코드")` |
| stdg_nm | str | 없음(필수, `...`) | `Field(..., description="법정동명")` |
| bldg_nm | str | 없음(필수, `...`) | `Field(..., description="건물명(아파트명)")` |
| latitude | float | 없음(필수, `...`) | `Field(..., description="위도")` |
| longitude | float | 없음(필수, `...`) | `Field(..., description="경도")` |
| is_exact_location | bool | 없음(필수, `...`) | `Field(..., description="정확한 좌표 여부")` |
| updated_at | datetime | 없음(필수, `...`) | `Field(..., description="데이터 갱신 시각")` |
| deal_cnt | int | 없음(필수, `...`) | `Field(..., description="거래 건수")` |
| avg_thing_amt | int | 없음(필수, `...`) | `Field(..., description="평균 거래가(total_thing_amt / deal_cnt, 반올림)")` |
| avg_pyeong_amt | int | 없음(필수, `...`) | `Field(..., description="평균 평당가(total_pyeong_amt / deal_cnt, 반올림)")` |

**AptPriceTopBottomResponse 필드 목록(클래스 정의 순서)**

| 필드명 | 타입 | 기본값 | Field 설명 |
|---|---|---|---|
| base_date | str | 없음(필수, `...`) | `Field(..., description="실제 조회에 사용된 mart 파티션의 base_date")` |
| total_count | int | 없음(필수, `...`) | `Field(..., description="조건에 해당하는 전체 거래건수 합계")` |
| avg_thing_amt | int | 없음(필수, `...`) | `Field(..., description="조건에 해당하는 전체 평균 거래금액(반올림)")` |
| avg_pyeong_amt | int | 없음(필수, `...`) | `Field(..., description="조건에 해당하는 전체 평균 평당가(반올림)")` |
| top | list[AptPriceItem] | `default_factory=list` | `Field(default_factory=list, description="metric_type 기준(평균 평당가 또는 평균 거래가) 내림차순 상위 5개.")` |
| bottom | list[AptPriceItem] | `default_factory=list` | `Field(default_factory=list, description="metric_type 기준(평균 평당가 또는 평균 거래가) 오름차순 하위 5개.")` |

## 4. 의존성(imports)

- 표준 라이브러리:
  - `from datetime import date, datetime`
  - `from typing import Literal`
- 서드파티:
  - `from pydantic import BaseModel, Field`
- 내부 모듈: 없음

## 5. 로직 상세

### MetricType

- 목적: `metric_type` 쿼리 파라미터의 허용값을 제한하는 타입 별칭.
- 값: `Literal["pyeong", "thing_amt"]`.

### AptPriceTopBottomQuery

- 목적(원문 docstring): "`GET /api/v1/apt-price/top-bottom` 요청 Query Parameter."
- 필드: 위 표 참조. 검증 로직 없음(필드 레벨 `pattern` 제약만 존재).

### AptPriceItem

- 목적(원문 docstring): "`dm_apt_price_avg` 마트의 아파트별 row 스키마(거래금액/평당가는 거래 건수 기준 평균값)."
- 필드: 위 표 참조. 검증 로직 없음.

### AptPriceTopBottomResponse

- 목적(원문 docstring): "`GET /api/v1/apt-price/top-bottom` 응답 스키마."
- 필드: 위 표 참조. 검증 로직 없음.

## 6. 모듈 레벨 상수/설정값

| 이름 | 값 |
|---|---|
| MetricType | `Literal["pyeong", "thing_amt"]` |

## 7. 역참조(이 파일을 사용하는 곳)

- `app/api/v1/endpoints/apt_price.py` — `from app.schemas.apt_price import AptPriceTopBottomQuery, AptPriceTopBottomResponse`.

## 8. 재생성 지침

> 위 내용을 근거로 `backend_fastApi/app/schemas/apt_price.py` 파일을 동일한 로직으로 재작성하라. 여기 명시되지 않은 세부 구현(변수명 스타일, 코드 포맷 등)은 기존 프로젝트 컨벤션(PEP 8, 저장소 내 동일 계층 파일들의 스타일)을 따른다.
