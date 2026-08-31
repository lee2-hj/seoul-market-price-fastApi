# dashboard.py 명세

## 1. 메타 정보

| 항목 | 값 |
|---|---|
| source_path | backend_fastApi/app/schemas/dashboard.py |
| source_sha256 | c1375558096988bac90de4303ad76a9a6a026bda98488fb5214ff5577dda5c9a |
| source_lines | 114 |

## 2. 역할 요약

`GET /api/v1/dashboard`의 요청 Query 스키마(`DashboardQuery`)와 6개 위젯을 구성하는 하위 스키마(`DistrictAvgPriceItem`, `PriceChangeItem`, `PriceChangeTop5`, `PreferencePriceTrendItem`, `TopTradingDongItem`, `PopularDong`, `TopTradingAptItem`), 최종 응답 스키마(`DashboardResponse`)를 정의한다.

## 3. 외부 인터페이스

| 이름 | 종류 | 시그니처 | 반환 타입 |
|---|---|---|---|
| DashboardQuery | class | `class DashboardQuery(BaseModel)` | - |
| DistrictAvgPriceItem | class | `class DistrictAvgPriceItem(BaseModel)` | - |
| PriceChangeItem | class | `class PriceChangeItem(BaseModel)` | - |
| PriceChangeTop5 | class | `class PriceChangeTop5(BaseModel)` | - |
| PreferencePriceTrendItem | class | `class PreferencePriceTrendItem(BaseModel)` | - |
| TopTradingDongItem | class | `class TopTradingDongItem(BaseModel)` | - |
| PopularDong | class | `class PopularDong(BaseModel)` | - |
| TopTradingAptItem | class | `class TopTradingAptItem(BaseModel)` | - |
| DashboardResponse | class | `class DashboardResponse(BaseModel)` | - |

**DashboardQuery 필드 목록(클래스 정의 순서)**

| 필드명 | 타입 | 기본값 | Field 설명 |
|---|---|---|---|
| cgg_cd | str \| None | `None` | `Field(default=None, description="자치구코드(선택). 미지정 또는 빈 값이면 '서울시 중구'(11140)로 대체된다.", examples=["11140"])` |

**DistrictAvgPriceItem 필드 목록(클래스 정의 순서)**

| 필드명 | 타입 | 기본값 | Field 설명 |
|---|---|---|---|
| cgg_nm | str | 없음(필수, `...`) | `Field(..., description="자치구명")` |
| avg_deal_price | int | 없음(필수, `...`) | `Field(..., description="평균 매매가(SUM(total_thing_amt) / SUM(deal_cnt), 반올림)")` |
| avg_pyeong_price | int | 없음(필수, `...`) | `Field(..., description="평균 평단가(SUM(total_pyeong_amt) / SUM(deal_cnt), 반올림)")` |

**PriceChangeItem 필드 목록(클래스 정의 순서)**

| 필드명 | 타입 | 기본값 | Field 설명 |
|---|---|---|---|
| bldg_nm | str | 없음(필수, `...`) | `Field(..., description="단지명")` |
| change_rate | float | 없음(필수, `...`) | `Field(..., description=("최신 평당가(recent_pyeong_amt) 대비 90일 평균 평당가 변동률(%), 소수 둘째 자리 반올림. " "(recent_pyeong_amt - 90일 평균 평당가) / 90일 평균 평당가 * 100. " "매매가 대신 평당가 기준으로 계산해 평형 차이에 따른 왜곡을 배제하며, 90일 거래건수가 3건 미만인 " "단지와 \|변동률\| > 30%인 이상치는 제외한다. 정렬은 이 값이 아닌 거래량 가중 스코어" "(change_rate * ln(1 + deal_cnt))를 기준으로 한다."))` |

**PriceChangeTop5 필드 목록(클래스 정의 순서)**

| 필드명 | 타입 | 기본값 | Field 설명 |
|---|---|---|---|
| rising_top5 | list[PriceChangeItem] | `default_factory=list` | `Field(default_factory=list, description="변동률 상위 5개(상승률 큰 순)")` |
| falling_top5 | list[PriceChangeItem] | `default_factory=list` | `Field(default_factory=list, description="변동률 하위 5개(하락률 큰 순)")` |

**PreferencePriceTrendItem 필드 목록(클래스 정의 순서)**

| 필드명 | 타입 | 기본값 | Field 설명 |
|---|---|---|---|
| period_label | str | 없음(필수, `...`) | `Field(..., description="구간 식별자. 예: 'D-90~D-68'")` |
| start_date | date | 없음(필수, `...`) | `Field(..., description="구간 시작일")` |
| end_date | date | 없음(필수, `...`) | `Field(..., description="구간 종료일")` |
| avg_deal_price | int | 없음(필수, `...`) | `Field(..., description="구간 평균 거래가(SUM(total_thing_amt) / SUM(deal_cnt), 반올림)")` |
| avg_pyeong_price | int | 없음(필수, `...`) | `Field(..., description="구간 평균 평단가(SUM(total_pyeong_amt) / SUM(deal_cnt), 반올림)")` |
| deal_cnt | int | 없음(필수, `...`) | `Field(..., description="구간 거래량 총합(SUM(deal_cnt))")` |

**TopTradingDongItem 필드 목록(클래스 정의 순서)**

| 필드명 | 타입 | 기본값 | Field 설명 |
|---|---|---|---|
| cgg_nm | str | 없음(필수, `...`) | `Field(..., description="자치구명")` |
| stdg_nm | str | 없음(필수, `...`) | `Field(..., description="법정동명")` |
| deal_cnt | int | 없음(필수, `...`) | `Field(..., description="거래량(SUM(deal_cnt))")` |

**PopularDong 필드 목록(클래스 정의 순서)**

| 필드명 | 타입 | 기본값 | Field 설명 |
|---|---|---|---|
| cgg_nm | str | 없음(필수, `...`) | `Field(..., description="자치구명")` |
| stdg_nm | str | 없음(필수, `...`) | `Field(..., description="법정동명")` |

**TopTradingAptItem 필드 목록(클래스 정의 순서)**

| 필드명 | 타입 | 기본값 | Field 설명 |
|---|---|---|---|
| bldg_nm | str | 없음(필수, `...`) | `Field(..., description="아파트명")` |
| recent_thing_amt | int | 없음(필수, `...`) | `Field(..., description="최근 매매가(base_date 최신 row 기준)")` |
| deal_cnt | int | 없음(필수, `...`) | `Field(..., description="거래량(SUM(deal_cnt))")` |

**DashboardResponse 필드 목록(클래스 정의 순서)**

| 필드명 | 타입 | 기본값 | Field 설명 |
|---|---|---|---|
| cgg_cd | str | 없음(필수, `...`) | `Field(..., description="조회에 사용된 자치구코드(미지정 시 기본값 '11140')")` |
| period_start | date | 없음(필수, `...`) | `Field(..., description="집계 기간 시작일(오늘 기준 90일 전)")` |
| period_end | date | 없음(필수, `...`) | `Field(..., description="집계 기간 종료일(오늘)")` |
| preference_base_date | str | 없음(필수, `...`) | `Field(..., description=("선호지역(cgg_cd) 필터 위젯 3종(preference_price_trend/preference_top_trading_dongs/" "preference_top_trading_apts)에 실제 사용된 base_date. 이 지역 조건에 매칭되는 데이터가 " "최신 파티션에 없으면 과거 파티션으로 소급될 수 있다. 필터 없는 2개 위젯" "(seoul_top5_districts/price_change_top5)은 항상 최신 파티션(나이브 최신 base_date)을 " "사용하므로 이 필드와 다를 수 있다."))` |
| seoul_top5_districts | list[DistrictAvgPriceItem] | `default_factory=list` | `Field(default_factory=list, description="서울시 전체 자치구별 평균 매매가 Top5(자치구 필터 없음)")` |
| price_change_top5 | PriceChangeTop5 | 없음(필수, `...`) | `Field(..., description="아파트 가격 상승/하락 Top5(전체 데이터 기준)")` |
| preference_price_trend | list[PreferencePriceTrendItem] | `default_factory=list` | `Field(default_factory=list, description="선호지역(cgg_cd) 실거래가 추이(최근 90일을 4구간으로 분할)")` |
| preference_top_trading_dongs | list[TopTradingDongItem] | `default_factory=list` | `Field(default_factory=list, description="선호지역 내 거래량 상위 법정동 Top5")` |
| preference_popular_dong | PopularDong \| None | `None` | `Field(default=None, description="선호지역 내 거래량 1위 법정동. 거래 데이터가 없으면 null")` |
| preference_top_trading_apts | list[TopTradingAptItem] | `default_factory=list` | `Field(default_factory=list, description="선호지역 내 아파트 거래량 Top5")` |

## 4. 의존성(imports)

- 표준 라이브러리:
  - `from datetime import date`
- 서드파티:
  - `from pydantic import BaseModel, Field`
- 내부 모듈: 없음

## 5. 로직 상세

### DashboardQuery

- 목적(원문 docstring): "`GET /api/v1/dashboard` 요청 Query Parameter."
- 필드: 위 표 참조. 검증 로직 없음.

### DistrictAvgPriceItem

- 목적(원문 docstring): "자치구별 평균 매매가/평단가 항목."
- 필드: 위 표 참조.

### PriceChangeItem

- 목적(원문 docstring): "단지별 가격 변동률 항목."
- 필드: 위 표 참조.

### PriceChangeTop5

- 목적(원문 docstring): "아파트 가격 상승/하락 Top5."
- 필드: 위 표 참조.

### PreferencePriceTrendItem

- 목적(원문 docstring): "선호지역 실거래가 추이 구간 항목."
- 필드: 위 표 참조.

### TopTradingDongItem

- 목적(원문 docstring): "선호지역 내 거래량 상위 법정동 항목."
- 필드: 위 표 참조.

### PopularDong

- 목적(원문 docstring): "선호지역 내 거래량 1위 법정동."
- 필드: 위 표 참조.

### TopTradingAptItem

- 목적(원문 docstring): "선호지역 내 아파트 거래량 상위 항목."
- 필드: 위 표 참조.

### DashboardResponse

- 목적(원문 docstring): "`GET /api/v1/dashboard` 응답 스키마. dm_apt_price_avg 마트의 최근 90일 데이터를 기준으로 6개 위젯을 단일 JSON으로 반환한다."
- 필드: 위 표 참조. 검증 로직 없음.

## 6. 모듈 레벨 상수/설정값

없음.

## 7. 역참조(이 파일을 사용하는 곳)

- `app/api/v1/endpoints/dashboard.py` — `from app.schemas.dashboard import DashboardQuery, DashboardResponse`.

## 8. 재생성 지침

> 위 내용을 근거로 `backend_fastApi/app/schemas/dashboard.py` 파일을 동일한 로직으로 재작성하라. 여기 명시되지 않은 세부 구현(변수명 스타일, 코드 포맷 등)은 기존 프로젝트 컨벤션(PEP 8, 저장소 내 동일 계층 파일들의 스타일)을 따른다.
