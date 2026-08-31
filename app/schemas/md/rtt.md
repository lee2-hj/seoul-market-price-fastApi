# rtt.py 명세

## 1. 메타 정보

| 항목 | 값 |
|---|---|
| source_path | backend_fastApi/app/schemas/rtt.py |
| source_sha256 | f987963c85df6f7f34b4e6c8d2e314d26c4ea2f560c3b301b8817c62ae0acd59 |
| source_lines | 122 |

## 2. 역할 요약

`GET /api/v1/rtt/summary`의 요청 Query 스키마(`RttSummaryQuery`)와 하위 집계 스키마(`RttBiweeklyTrend`, `RttPyeongDistribution`, `RttRecentTrade`, `RttTopVolumeItem`), 최종 응답 스키마(`RttSummaryResponse`)를 정의한다.

## 3. 외부 인터페이스

| 이름 | 종류 | 시그니처 | 반환 타입 |
|---|---|---|---|
| RttSummaryQuery | class | `class RttSummaryQuery(BaseModel)` | - |
| RttBiweeklyTrend | class | `class RttBiweeklyTrend(BaseModel)` | - |
| RttPyeongDistribution | class | `class RttPyeongDistribution(BaseModel)` | - |
| RttRecentTrade | class | `class RttRecentTrade(BaseModel)` | - |
| RttTopVolumeItem | class | `class RttTopVolumeItem(BaseModel)` | - |
| RttSummaryResponse | class | `class RttSummaryResponse(BaseModel)` | - |

**RttSummaryQuery 필드 목록(클래스 정의 순서)**

| 필드명 | 타입 | 기본값 | Field 설명 |
|---|---|---|---|
| sgg_cd | str | 없음(필수, `...`) | `Field(..., pattern=r"^\d{5}$", description="시군구코드(5자리, 필수)", examples=["11680"])` |
| dong_cd | str \| None | `None` | `Field(default=None, pattern=r"^\d{5}$", description="법정동코드(5자리, 선택). 미지정 시 자치구(sgg_cd) 내 모든 법정동의 거래내역을 합산해 조회한다.", examples=["10300"])` |

**RttBiweeklyTrend 필드 목록(클래스 정의 순서)**

| 필드명 | 타입 | 기본값 | Field 설명 |
|---|---|---|---|
| period_label | str | 없음(필수, `...`) | `Field(..., description="기간 식별자. 'YYYY-MM-DD/YYYY-MM-DD'(시작일/종료일) 형식")` |
| start_date | date | 없음(필수, `...`) | `Field(..., description="구간 시작일")` |
| end_date | date | 없음(필수, `...`) | `Field(..., description="구간 종료일")` |
| deal_cnt | int | 없음(필수, `...`) | `Field(..., description="해당 구간 총 거래건수")` |
| avg_trade_amount | int | 없음(필수, `...`) | `Field(..., description="해당 구간 평균 거래가(반올림)")` |

**RttPyeongDistribution 필드 목록(클래스 정의 순서)**

| 필드명 | 타입 | 기본값 | Field 설명 |
|---|---|---|---|
| pyeong_grp | str | 없음(필수, `...`) | `Field(..., description=("평형 그룹. 10평 단위이며 상한 없이 실제 거래 데이터 기준으로 동적으로 생성된다" "(예: '10','20',...,'50','60'. 10평 미만은 '10'에 포함)."))` |
| deal_cnt | int | 없음(필수, `...`) | `Field(..., description="해당 평형 그룹 거래건수")` |
| ratio | float | 없음(필수, `...`) | `Field(..., description="전체 거래건수 대비 비중(%), 소수 둘째 자리 반올림. 비중 0%인 그룹은 응답에서 제외된다")` |

**RttRecentTrade 필드 목록(클래스 정의 순서)**

| 필드명 | 타입 | 기본값 | Field 설명 |
|---|---|---|---|
| apt_name | str | 없음(필수, `...`) | `Field(..., description="아파트명")` |
| mno | str | 없음(필수, `...`) | `Field(..., description="지번 본번")` |
| sno | str | 없음(필수, `...`) | `Field(..., description="지번 부번")` |
| deal_date | date | 없음(필수, `...`) | `Field(..., description="거래일")` |
| floor | int | 없음(필수, `...`) | `Field(..., description="거래 층수")` |
| trade_amount | float | 없음(필수, `...`) | `Field(..., description="거래금액")` |
| pyeong | float | 없음(필수, `...`) | `Field(..., description="평형")` |
| exclusive_area_m2 | float | 없음(필수, `...`) | `Field(..., description="전용면적(㎡)")` |
| sgg_nm | str \| None | `None` | `Field(default=None, description="시군구명. 요청에 dong_cd가 없을 때(자치구 전체 조회)만 값이 채워진다.")` |
| dong_nm | str \| None | `None` | `Field(default=None, description="법정동명. 요청에 dong_cd가 없을 때(자치구 전체 조회)만 값이 채워진다.")` |

**RttTopVolumeItem 필드 목록(클래스 정의 순서)**

| 필드명 | 타입 | 기본값 | Field 설명 |
|---|---|---|---|
| apt_name | str | 없음(필수, `...`) | `Field(..., description="아파트명")` |
| mno | str | 없음(필수, `...`) | `Field(..., description="지번 본번")` |
| sno | str | 없음(필수, `...`) | `Field(..., description="지번 부번")` |
| deal_cnt | int | 없음(필수, `...`) | `Field(..., description="거래건수")` |
| avg_trade_amount | int | 없음(필수, `...`) | `Field(..., description="평균 거래가(반올림)")` |

**RttSummaryResponse 필드 목록(클래스 정의 순서)**

| 필드명 | 타입 | 기본값 | Field 설명 |
|---|---|---|---|
| sgg_cd | str | 없음(필수, `...`) | `Field(..., description="시군구코드")` |
| sgg_nm | str \| None | `None` | `Field(default=None, description="시군구명")` |
| dong_cd | str \| None | `None` | `Field(default=None, description="법정동코드. 요청 시 미지정했다면 null(자치구 전체 집계)")` |
| dong_nm | str \| None | `None` | `Field(default=None, description="법정동명. dong_cd 미지정 시(자치구 전체 집계) null")` |
| period_start | date | 없음(필수, `...`) | `Field(..., description=("집계 기간 시작일. 기본은 오늘 기준 90일 전이지만, 그 구간에 조건에 맞는 거래가 없으면 " "조건에 맞는 데이터가 있는 가장 최근 날짜 기준 90일 구간으로 소급될 수 있다(이 경우 오늘 " "기준이 아니다)."))` |
| period_end | date | 없음(필수, `...`) | `Field(..., description=("집계 기간 종료일. 기본은 오늘이지만, period_start와 마찬가지로 소급이 일어나면 오늘이 " "아닐 수 있다."))` |
| total_deal_cnt | int | 없음(필수, `...`) | `Field(..., description="기간 내 일자들의 거래건수 총합")` |
| total_trade_amount | int | 없음(필수, `...`) | `Field(..., description="기간 내 거래건수 총 거래금액")` |
| avg_trade_amount | int | 없음(필수, `...`) | `Field(..., description="평균 거래가(총 거래금액 / 총 거래건수, 반올림)")` |
| max_trade_amount | int | 없음(필수, `...`) | `Field(..., description="기간 내 일자들 중 최고 거래가")` |
| volume_change_rate | float \| None | `None` | `Field(default=None, description=("최근 90일 동안의 거래량 증감률(%). 90일을 절반(이전 45일/최근 45일)으로 나눠 " "(최근 45일 거래건수 - 이전 45일 거래건수) / 이전 45일 거래건수 * 100 으로 계산한다. " "이전 45일 거래건수가 0이면 산출 불가로 null을 반환한다."))` |
| biweekly_trend | list[RttBiweeklyTrend] | `default_factory=list` | `Field(default_factory=list, description="90일을 6구간으로 균등 분할한 거래량/평균 거래가 추이")` |
| pyeong_distribution | list[RttPyeongDistribution] | `default_factory=list` | `Field(default_factory=list, description="평(면적)별 거래 비중")` |
| recent_trades | list[RttRecentTrade] | `default_factory=list` | `Field(default_factory=list, description="최근 실거래 데이터(거래일 최신순)")` |
| top5_by_volume | list[RttTopVolumeItem] | `default_factory=list` | `Field(default_factory=list, description="거래량 상위 top5 단지")` |

## 4. 의존성(imports)

- 표준 라이브러리:
  - `from datetime import date`
- 서드파티:
  - `from pydantic import BaseModel, Field`
- 내부 모듈: 없음

## 5. 로직 상세

### RttSummaryQuery

- 목적(원문 docstring): "`GET /api/v1/rtt/summary` 요청 Query Parameter."
- 필드: 위 표 참조. 검증 로직 없음.

### RttBiweeklyTrend

- 목적(원문 docstring): "90일 조회 구간을 6개로 균등 분할한 구간별 거래량/평균 거래가 추이 항목."
- 필드: 위 표 참조.

### RttPyeongDistribution

- 목적(원문 docstring): "평(면적)별 거래 비중 항목."
- 필드: 위 표 참조.

### RttRecentTrade

- 목적(원문 docstring): "최근 실거래 개별 항목."
- 필드: 위 표 참조.

### RttTopVolumeItem

- 목적(원문 docstring): "거래량 상위 단지 항목."
- 필드: 위 표 참조.

### RttSummaryResponse

- 목적(원문 docstring): "`GET /api/v1/rtt/summary` 응답 스키마. 조회 기준일로부터 최근 90일간의 실거래 데이터를 집계한다."
- 필드: 위 표 참조. 검증 로직 없음.

## 6. 모듈 레벨 상수/설정값

없음.

## 7. 역참조(이 파일을 사용하는 곳)

- `app/api/v1/endpoints/rtt.py` — `from app.schemas.rtt import RttSummaryQuery, RttSummaryResponse`.

## 8. 재생성 지침

> 위 내용을 근거로 `backend_fastApi/app/schemas/rtt.py` 파일을 동일한 로직으로 재작성하라. 여기 명시되지 않은 세부 구현(변수명 스타일, 코드 포맷 등)은 기존 프로젝트 컨벤션(PEP 8, 저장소 내 동일 계층 파일들의 스타일)을 따른다.
