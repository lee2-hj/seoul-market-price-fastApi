# apt_trend.py 명세

## 1. 메타 정보

| 항목 | 값 |
|---|---|
| source_path | backend_fastApi/app/schemas/apt_trend.py |
| source_sha256 | 2ad5a04ed39b39b7a037190e7cea3dd4b34206ea30d40687281ec2db5ce3b935 |
| source_lines | 123 |

## 2. 역할 요약

`GET /api/v1/apt-trend/summary`의 요청 Query 스키마(`AptTrendQuery`)와 하위 집계 스키마(`BiweeklyTrendItem`, `AreaRatioItem`, `RecentDealItem`, `AreaDealItem`, `AptTrendData`, `SearchPeriod`), 최종 응답 스키마(`AptTrendResponse`)를 정의한다.

## 3. 외부 인터페이스

| 이름 | 종류 | 시그니처 | 반환 타입 |
|---|---|---|---|
| AptTrendQuery | class | `class AptTrendQuery(BaseModel)` | - |
| BiweeklyTrendItem | class | `class BiweeklyTrendItem(BaseModel)` | - |
| AreaRatioItem | class | `class AreaRatioItem(BaseModel)` | - |
| RecentDealItem | class | `class RecentDealItem(BaseModel)` | - |
| AreaDealItem | class | `class AreaDealItem(BaseModel)` | - |
| AptTrendData | class | `class AptTrendData(BaseModel)` | - |
| SearchPeriod | class | `class SearchPeriod(BaseModel)` | - |
| AptTrendResponse | class | `class AptTrendResponse(BaseModel)` | - |

**AptTrendQuery 필드 목록(클래스 정의 순서)**

| 필드명 | 타입 | 기본값 | Field 설명 |
|---|---|---|---|
| cgg_cd | str | 없음(필수, `...`) | `Field(..., description="자치구코드(필수)", examples=["11680"])` |
| stdg_cd | str | 없음(필수, `...`) | `Field(..., description="법정동코드(필수)", examples=["10300"])` |
| mno | str | 없음(필수, `...`) | `Field(..., description="지번 본번(필수)")` |
| sno | str | 없음(필수, `...`) | `Field(..., description="지번 부번(필수)")` |
| apt_name | str | 없음(필수, `...`) | `Field(..., description=("아파트명 검색어(필수, 부분일치/대소문자 무시). apt_mkt_trends의 실제 apt_name 컬럼을 " "SQL WHERE(ILIKE)에서 직접 검색한다. 다른 마트를 참조하지 않으며, 매칭되는 데이터가 없으면 " "빈 결과(count: 0, data: [])가 반환된다."), examples=["반포자이"])` |

**BiweeklyTrendItem 필드 목록(클래스 정의 순서)**

| 필드명 | 타입 | 기본값 | Field 설명 |
|---|---|---|---|
| biweekly_period | str | 없음(필수, `...`) | `Field(..., description="기간 식별자. 'YYYY-MM-DD/YYYY-MM-DD'(시작일/종료일) 형식")` |
| deal_count | int | 없음(필수, `...`) | `Field(..., description="해당 구간 거래건수(trade_count 합계)")` |
| avg_price | int | 없음(필수, `...`) | `Field(..., description="해당 구간 평균 거래가(만원, 반올림)")` |

**AreaRatioItem 필드 목록(클래스 정의 순서)**

| 필드명 | 타입 | 기본값 | Field 설명 |
|---|---|---|---|
| pyeong_grp | str | 없음(필수, `...`) | `Field(..., description=("평형 그룹. 10평 단위이며 상한 없이 실제 거래 데이터 기준으로 동적으로 생성된다" "(예: '10','20',...,'50','60'. 10평 미만은 '10'에 포함)."))` |
| deal_count | int | 없음(필수, `...`) | `Field(..., description="해당 평형 그룹 거래건수(trade_count 합계)")` |
| share_percentage | float | 없음(필수, `...`) | `Field(..., description="전체 거래건수 대비 비중(%), 소수 둘째 자리 반올림. 비중 0%인 그룹은 응답에서 제외된다")` |

**RecentDealItem 필드 목록(클래스 정의 순서)**

| 필드명 | 타입 | 기본값 | Field 설명 |
|---|---|---|---|
| deal_date | date | 없음(필수, `...`) | `Field(..., description="계약일")` |
| exclusive_area | str | 없음(필수, `...`) | `Field(..., description="전용면적(㎡, 소수 둘째 자리). pyeong * 3.305785로 환산")` |
| pyeong | int | 없음(필수, `...`) | `Field(..., description="평수(마트 원본 pyeong 값을 반올림)")` |
| floor | int | 없음(필수, `...`) | `Field(..., description="층수")` |
| deal_amount | int | 없음(필수, `...`) | `Field(..., description="거래가(만원). trade_amount / trade_count, 반올림")` |

**AreaDealItem 필드 목록(클래스 정의 순서)**

| 필드명 | 타입 | 기본값 | Field 설명 |
|---|---|---|---|
| exclusive_area | str | 없음(필수, `...`) | `Field(..., description="전용면적(㎡, 소수 둘째 자리). pyeong * 3.305785로 환산")` |
| pyeong | int | 없음(필수, `...`) | `Field(..., description="평수(마트 원본 pyeong 값을 반올림)")` |
| deal_count | int | 없음(필수, `...`) | `Field(..., description="해당 면적 거래건수(trade_count 합계)")` |
| avg_deal_price | int | 없음(필수, `...`) | `Field(..., description="해당 면적 평균 거래가(만원, 반올림)")` |

**AptTrendData 필드 목록(클래스 정의 순서)**

| 필드명 | 타입 | 기본값 | Field 설명 |
|---|---|---|---|
| apt_name | str | 없음(필수, `...`) | `Field(..., description="아파트명(apt_mkt_trends의 실제 apt_name 컬럼값)")` |
| cgg_cd | str | 없음(필수, `...`) | `Field(..., description="자치구코드")` |
| cgg_nm | str | 없음(필수, `...`) | `Field(..., description="자치구명")` |
| stdg_cd | str | 없음(필수, `...`) | `Field(..., description="법정동코드")` |
| stdg_nm | str | 없음(필수, `...`) | `Field(..., description="법정동명")` |
| total_deal_count | int | 없음(필수, `...`) | `Field(..., description="총 거래건수(trade_count 합계)")` |
| total_deal_amount | int | 없음(필수, `...`) | `Field(..., description="총 거래금액(만원)")` |
| average_deal_price | int | 없음(필수, `...`) | `Field(..., description="평균 거래가(만원, 반올림)")` |
| max_deal_price | int | 없음(필수, `...`) | `Field(..., description="최고 거래가(만원)")` |
| count_change_rate | int \| None | `None` | `Field(default=None, description=("biweekly_trend의 인접한 구간 간 deal_count 증감률(%)을, 오래된 스텝부터 1,2,3,...로 " "선형 증가하는 가중치(최신 스텝일수록 가중치가 높음)로 가중평균해 반올림한 정수값이다. " "이전 구간의 거래건수가 0이면(증감률 계산 불가) 해당 스텝만 제외되며, 계산 가능한 스텝이 " "하나도 없으면(마지막 구간을 제외한 나머지 구간 전부 거래 0건) null을 반환한다."))` |
| biweekly_trend | list[BiweeklyTrendItem] | `default_factory=list` | `Field(default_factory=list, description="90일을 6구간으로 균등 분할한 거래량/평균 거래가 추이")` |
| area_ratio | list[AreaRatioItem] | `default_factory=list` | `Field(default_factory=list, description="전용면적별 거래 점유 비율")` |
| recent_deals | list[RecentDealItem] | `default_factory=list` | `Field(default_factory=list, description="전체 거래 내역(개수 제한 없음), 거래일자 최신순(내림차순)")` |
| area_deals | list[AreaDealItem] | `default_factory=list` | `Field(default_factory=list, description="전용면적(평)별 요약 통계")` |

**SearchPeriod 필드 목록(클래스 정의 순서)**

| 필드명 | 타입 | 기본값 | Field 설명 |
|---|---|---|---|
| start_date | date | 없음(필수, `...`) | `Field(..., description=("조회 시작일. 기본은 오늘 기준 90일 전이지만, 그 구간에 조건에 맞는 거래가 없으면 조건에 " "맞는 데이터가 있는 가장 최근 날짜 기준 90일 구간으로 소급될 수 있다(이 경우 오늘 기준이 " "아니다)."))` |
| end_date | date | 없음(필수, `...`) | `Field(..., description="조회 종료일. 기본은 오늘이지만, start_date와 마찬가지로 소급이 일어나면 오늘이 아닐 수 있다.")` |

**AptTrendResponse 필드 목록(클래스 정의 순서)**

| 필드명 | 타입 | 기본값 | Field 설명 |
|---|---|---|---|
| status | str | `"success"` | `Field(default="success", description="처리 상태")` |
| search_period | SearchPeriod | 없음(필수, `...`) | `Field(..., description="조회에 사용된 기간")` |
| count | int | 없음(필수, `...`) | `Field(..., description="data 배열에 포함된 단지 수")` |
| data | list[AptTrendData] | `default_factory=list` | `Field(default_factory=list, description="단지별 실거래가 트렌드 집계 목록")` |

## 4. 의존성(imports)

- 표준 라이브러리:
  - `from datetime import date`
- 서드파티:
  - `from pydantic import BaseModel, Field`
- 내부 모듈: 없음

## 5. 로직 상세

### AptTrendQuery

- 목적(원문 docstring): "`GET /api/v1/apt-trend/summary` 요청 Query Parameter. 모두 필수값이며, AND로 결합된다. 모든 조건은 다른 마트를 참조하지 않고 `apt_mkt_trends` 자체의 컬럼만으로 SQL WHERE에서 필터링한다."
- 필드: 위 표 참조. 검증 로직 없음.

### BiweeklyTrendItem

- 목적(원문 docstring): "90일 조회 구간을 6개로 균등 분할한 구간별 거래량/평균 거래가 추이 항목."
- 필드: 위 표 참조.

### AreaRatioItem

- 목적(원문 docstring): "평형대별 거래 점유 비율 항목."
- 필드: 위 표 참조.

### RecentDealItem

- 목적(원문 docstring): "실거래 개별 항목(개수 제한 없이 전체, 거래일자 최신순)."
- 필드: 위 표 참조.

### AreaDealItem

- 목적(원문 docstring): "전용면적(평)별 요약 통계 항목."
- 필드: 위 표 참조.

### AptTrendData

- 목적(원문 docstring): "단지(cgg_cd+stdg_cd+apt_name) 단위 실거래가 트렌드 집계. apt_name은 apt_mkt_trends의 실제 컬럼값을 그대로 사용한다. apt_name은 전역 고유하지 않아(동명 단지가 여러 법정동에 존재) cgg_cd/stdg_cd와 함께 묶어야 서로 다른 동의 동명 단지가 섞이지 않는다. 한 단지가 여러 지번(mno/sno)에 걸쳐 있을 수 있어 지번 필드는 이 집계 단위에서는 노출하지 않는다."
- 필드: 위 표 참조. 검증 로직 없음(docstring 없는 필드별 클래스, `count_change_rate` 설명은 위 표에 원문 그대로).

### SearchPeriod

- 목적: docstring 없음. 검색에 사용된 기간(시작일/종료일)을 표현.
- 필드: 위 표 참조.

### AptTrendResponse

- 목적(원문 docstring): "`GET /api/v1/apt-trend/summary` 응답 스키마."
- 필드: 위 표 참조. 검증 로직 없음.

## 6. 모듈 레벨 상수/설정값

없음.

## 7. 역참조(이 파일을 사용하는 곳)

- `app/api/v1/endpoints/apt_trend.py` — `from app.schemas.apt_trend import AptTrendQuery, AptTrendResponse`.

## 8. 재생성 지침

> 위 내용을 근거로 `backend_fastApi/app/schemas/apt_trend.py` 파일을 동일한 로직으로 재작성하라. 여기 명시되지 않은 세부 구현(변수명 스타일, 코드 포맷 등)은 기존 프로젝트 컨벤션(PEP 8, 저장소 내 동일 계층 파일들의 스타일)을 따른다.
