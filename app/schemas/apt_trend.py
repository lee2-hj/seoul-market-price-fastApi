from datetime import date

from pydantic import BaseModel, Field


class AptTrendQuery(BaseModel):
    """`GET /api/v1/apt-trend/summary` 요청 Query Parameter. 모두 필수값이며, AND로 결합된다.
    모든 조건은 다른 마트를 참조하지 않고 `apt_mkt_trends` 자체의 컬럼만으로 SQL WHERE에서 필터링한다."""

    cgg_cd: str = Field(..., description="자치구코드(필수)", examples=["11680"])
    stdg_cd: str = Field(..., description="법정동코드(필수)", examples=["10300"])
    mno: str = Field(..., description="지번 본번(필수)")
    sno: str = Field(..., description="지번 부번(필수)")
    apt_name: str = Field(
        ...,
        description=(
            "아파트명 검색어(필수, 부분일치/대소문자 무시). apt_mkt_trends의 실제 apt_name 컬럼을 "
            "SQL WHERE(ILIKE)에서 직접 검색한다. 다른 마트를 참조하지 않으며, 매칭되는 데이터가 없으면 "
            "빈 결과(count: 0, data: [])가 반환된다."
        ),
        examples=["반포자이"],
    )


class BiweeklyTrendItem(BaseModel):
    """90일 조회 구간을 6개로 균등 분할한 구간별 거래량/평균 거래가 추이 항목."""

    biweekly_period: str = Field(..., description="기간 식별자. 'YYYY-MM-DD/YYYY-MM-DD'(시작일/종료일) 형식")
    deal_count: int = Field(..., description="해당 구간 거래건수(trade_count 합계)")
    avg_price: int = Field(..., description="해당 구간 평균 거래가(만원, 반올림)")


class AreaRatioItem(BaseModel):
    """평형대별 거래 점유 비율 항목."""

    pyeong_grp: str = Field(
        ...,
        description=(
            "평형 그룹. 10평 단위이며 상한 없이 실제 거래 데이터 기준으로 동적으로 생성된다"
            "(예: '10','20',...,'50','60'. 10평 미만은 '10'에 포함)."
        ),
    )
    deal_count: int = Field(..., description="해당 평형 그룹 거래건수(trade_count 합계)")
    share_percentage: float = Field(
        ..., description="전체 거래건수 대비 비중(%), 소수 둘째 자리 반올림. 비중 0%인 그룹은 응답에서 제외된다"
    )


class RecentDealItem(BaseModel):
    """실거래 개별 항목(개수 제한 없이 전체, 거래일자 최신순)."""

    deal_date: date = Field(..., description="계약일")
    exclusive_area: str = Field(..., description="전용면적(㎡, 소수 둘째 자리). pyeong * 3.305785로 환산")
    pyeong: int = Field(..., description="평수(마트 원본 pyeong 값을 반올림)")
    floor: int = Field(..., description="층수")
    deal_amount: int = Field(..., description="거래가(만원). trade_amount / trade_count, 반올림")


class AreaDealItem(BaseModel):
    """전용면적(평)별 요약 통계 항목."""

    exclusive_area: str = Field(..., description="전용면적(㎡, 소수 둘째 자리). pyeong * 3.305785로 환산")
    pyeong: int = Field(..., description="평수(마트 원본 pyeong 값을 반올림)")
    deal_count: int = Field(..., description="해당 면적 거래건수(trade_count 합계)")
    avg_deal_price: int = Field(..., description="해당 면적 평균 거래가(만원, 반올림)")


class AptTrendData(BaseModel):
    """단지(cgg_cd+stdg_cd+apt_name) 단위 실거래가 트렌드 집계. apt_name은 apt_mkt_trends의 실제 컬럼값을
    그대로 사용한다. apt_name은 전역 고유하지 않아(동명 단지가 여러 법정동에 존재) cgg_cd/stdg_cd와 함께
    묶어야 서로 다른 동의 동명 단지가 섞이지 않는다. 한 단지가 여러 지번(mno/sno)에 걸쳐 있을 수 있어
    지번 필드는 이 집계 단위에서는 노출하지 않는다."""

    apt_name: str = Field(..., description="아파트명(apt_mkt_trends의 실제 apt_name 컬럼값)")
    cgg_cd: str = Field(..., description="자치구코드")
    cgg_nm: str = Field(..., description="자치구명")
    stdg_cd: str = Field(..., description="법정동코드")
    stdg_nm: str = Field(..., description="법정동명")
    total_deal_count: int = Field(..., description="총 거래건수(trade_count 합계)")
    total_deal_amount: int = Field(..., description="총 거래금액(만원)")
    average_deal_price: int = Field(..., description="평균 거래가(만원, 반올림)")
    max_deal_price: int = Field(..., description="최고 거래가(만원)")
    count_change_rate: int | None = Field(
        default=None,
        description=(
            "biweekly_trend의 인접한 구간 간 deal_count 증감률(%)을, 오래된 스텝부터 1,2,3,...로 "
            "선형 증가하는 가중치(최신 스텝일수록 가중치가 높음)로 가중평균해 반올림한 정수값이다. "
            "스텝 양쪽 구간 중 하나라도 거래건수가 3(MIN_TRADE_COUNT) 미만이면 해당 스텝은 제외되며, "
            "유효한 스텝이 하나도 없으면 산출 불가로 null을 반환한다."
        ),
    )
    biweekly_trend: list[BiweeklyTrendItem] = Field(
        default_factory=list, description="90일을 6구간으로 균등 분할한 거래량/평균 거래가 추이"
    )
    area_ratio: list[AreaRatioItem] = Field(default_factory=list, description="전용면적별 거래 점유 비율")
    recent_deals: list[RecentDealItem] = Field(
        default_factory=list, description="전체 거래 내역(개수 제한 없음), 거래일자 최신순(내림차순)"
    )
    area_deals: list[AreaDealItem] = Field(default_factory=list, description="전용면적(평)별 요약 통계")


class SearchPeriod(BaseModel):
    start_date: date = Field(..., description="조회 시작일(오늘 기준 90일 전)")
    end_date: date = Field(..., description="조회 종료일(오늘)")


class AptTrendResponse(BaseModel):
    """`GET /api/v1/apt-trend/summary` 응답 스키마."""

    status: str = Field(default="success", description="처리 상태")
    search_period: SearchPeriod = Field(..., description="조회에 사용된 기간")
    count: int = Field(..., description="data 배열에 포함된 단지 수")
    data: list[AptTrendData] = Field(default_factory=list, description="단지별 실거래가 트렌드 집계 목록")
