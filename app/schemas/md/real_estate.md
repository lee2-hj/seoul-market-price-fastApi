# real_estate.py 명세

## 1. 메타 정보

| 항목 | 값 |
|---|---|
| source_path | backend_fastApi/app/schemas/real_estate.py |
| source_sha256 | 5e4975c627b6e3578c25b636afaa5cb43fbef9ee38a5088fed7963a96a7e23ea |
| source_lines | 32 |

## 2. 역할 요약

`GET /api/v1/real-estate/latest`의 실거래 항목 스키마(`RealEstateListingItem`)와 응답 스키마(`RealEstateLatestResponse`)를 정의한다.

## 3. 외부 인터페이스

| 이름 | 종류 | 시그니처 | 반환 타입 |
|---|---|---|---|
| RealEstateListingItem | class | `class RealEstateListingItem(BaseModel)` | - |
| RealEstateLatestResponse | class | `class RealEstateLatestResponse(BaseModel)` | - |

**RealEstateListingItem 필드 목록(클래스 정의 순서)**

| 필드명 | 타입 | 기본값 | Field 설명 |
|---|---|---|---|
| apt_name | str | 없음(필수, `...`) | `Field(..., description="아파트명(BLDG_NM)")` |
| cgg_nm | str | 없음(필수, `...`) | `Field(..., description="자치구명(CGG_NM)")` |
| stdg_nm | str | 없음(필수, `...`) | `Field(..., description="법정동명(STDG_NM)")` |
| thing_amt | int | 없음(필수, `...`) | `Field(..., description="매매가(만원). 같은 날 동일 건물 거래가 여러 건이면 평균, 반올림")` |
| pyeong_amt | int | 없음(필수, `...`) | `Field(..., description="평당가(만원/평) = 매매가 / (전용면적(ARCH_AREA, ㎡) / 3.305785), 반올림")` |
| price_change | int \| None | 없음(필수, `...`) | `Field(..., description=("아파트별 직전 업데이트(같은 건물의 가장 최근 이전 거래일) 매매가 대비 가격 변동(만원). " "이전 거래 이력이 없으면 null."))` |
| update_date | date | 없음(필수, `...`) | `Field(..., description="업데이트 일자(해당 거래가 속한 RAW 파티션 날짜)")` |

**RealEstateLatestResponse 필드 목록(클래스 정의 순서)**

| 필드명 | 타입 | 기본값 | Field 설명 |
|---|---|---|---|
| base_date | str | 없음(필수, `...`) | `Field(..., description="실제 조회에 사용된 RAW 파티션의 날짜(YYYY-MM-DD)")` |
| count | int | 없음(필수, `...`) | `Field(..., description="조회된 아파트(건물) 개수")` |
| items | list[RealEstateListingItem] | `default_factory=list` | `Field(default_factory=list, description="아파트별 최신 실거래 목록")` |

## 4. 의존성(imports)

- 표준 라이브러리:
  - `from datetime import date`
- 서드파티:
  - `from pydantic import BaseModel, Field`
- 내부 모듈: 없음

## 5. 로직 상세

### RealEstateListingItem

- 목적(원문 docstring): "아파트(건물) 단위로 집계된 최신 실거래 항목. 같은 날 동일 건물(자치구+법정동+지번+건물명)에 여러 거래가 있으면 매매가/평당가는 해당 거래들의 평균값이다."
- 필드: 위 표 참조. 검증 로직 없음.

### RealEstateLatestResponse

- 목적(원문 docstring): "`GET /api/v1/real-estate/latest` 응답 스키마."
- 필드: 위 표 참조. 검증 로직 없음.

## 6. 모듈 레벨 상수/설정값

없음.

## 7. 역참조(이 파일을 사용하는 곳)

- `app/api/v1/endpoints/real_estate.py` — `from app.schemas.real_estate import RealEstateLatestResponse`.

## 8. 재생성 지침

> 위 내용을 근거로 `backend_fastApi/app/schemas/real_estate.py` 파일을 동일한 로직으로 재작성하라. 여기 명시되지 않은 세부 구현(변수명 스타일, 코드 포맷 등)은 기존 프로젝트 컨벤션(PEP 8, 저장소 내 동일 계층 파일들의 스타일)을 따른다.
