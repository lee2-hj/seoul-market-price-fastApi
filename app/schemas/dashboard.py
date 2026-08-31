from datetime import date

from pydantic import BaseModel, Field


class DashboardQuery(BaseModel):
    """`GET /api/v1/dashboard` 요청 Query Parameter."""

    cgg_cd: str | None = Field(
        default=None,
        description="자치구코드(선택). 미지정 또는 빈 값이면 '서울시 중구'(11140)로 대체된다.",
        examples=["11140"],
    )


class DistrictAvgPriceItem(BaseModel):
    """자치구별 평균 매매가/평단가 항목."""

    cgg_nm: str = Field(..., description="자치구명")
    avg_deal_price: int = Field(..., description="평균 매매가(SUM(total_thing_amt) / SUM(deal_cnt), 반올림)")
    avg_pyeong_price: int = Field(..., description="평균 평단가(SUM(total_pyeong_amt) / SUM(deal_cnt), 반올림)")


class PriceChangeItem(BaseModel):
    """단지별 가격 변동률 항목."""

    bldg_nm: str = Field(..., description="단지명")
    change_rate: float = Field(
        ...,
        description=(
            "최신 평당가(recent_pyeong_amt) 대비 90일 평균 평당가 변동률(%), 소수 둘째 자리 반올림. "
            "(recent_pyeong_amt - 90일 평균 평당가) / 90일 평균 평당가 * 100. "
            "매매가 대신 평당가 기준으로 계산해 평형 차이에 따른 왜곡을 배제하며, 90일 거래건수가 3건 미만인 "
            "단지와 |변동률| > 30%인 이상치는 제외한다. 정렬은 이 값이 아닌 거래량 가중 스코어"
            "(change_rate * ln(1 + deal_cnt))를 기준으로 한다."
        ),
    )


class PriceChangeTop5(BaseModel):
    """아파트 가격 상승/하락 Top5."""

    rising_top5: list[PriceChangeItem] = Field(default_factory=list, description="변동률 상위 5개(상승률 큰 순)")
    falling_top5: list[PriceChangeItem] = Field(default_factory=list, description="변동률 하위 5개(하락률 큰 순)")


class PreferencePriceTrendItem(BaseModel):
    """선호지역 실거래가 추이 구간 항목."""

    period_label: str = Field(..., description="구간 식별자. 예: 'D-90~D-68'")
    start_date: date = Field(..., description="구간 시작일")
    end_date: date = Field(..., description="구간 종료일")
    avg_deal_price: int = Field(..., description="구간 평균 거래가(SUM(total_thing_amt) / SUM(deal_cnt), 반올림)")
    avg_pyeong_price: int = Field(..., description="구간 평균 평단가(SUM(total_pyeong_amt) / SUM(deal_cnt), 반올림)")
    deal_cnt: int = Field(..., description="구간 거래량 총합(SUM(deal_cnt))")


class TopTradingDongItem(BaseModel):
    """선호지역 내 거래량 상위 법정동 항목."""

    cgg_nm: str = Field(..., description="자치구명")
    stdg_nm: str = Field(..., description="법정동명")
    deal_cnt: int = Field(..., description="거래량(SUM(deal_cnt))")


class PopularDong(BaseModel):
    """선호지역 내 거래량 1위 법정동."""

    cgg_nm: str = Field(..., description="자치구명")
    stdg_nm: str = Field(..., description="법정동명")


class TopTradingAptItem(BaseModel):
    """선호지역 내 아파트 거래량 상위 항목."""

    bldg_nm: str = Field(..., description="아파트명")
    recent_thing_amt: int = Field(..., description="최근 매매가(base_date 최신 row 기준)")
    deal_cnt: int = Field(..., description="거래량(SUM(deal_cnt))")


class DashboardResponse(BaseModel):
    """`GET /api/v1/dashboard` 응답 스키마. dm_apt_price_avg 마트의 최근 90일 데이터를 기준으로 6개 위젯을
    단일 JSON으로 반환한다."""

    cgg_cd: str = Field(..., description="조회에 사용된 자치구코드(미지정 시 기본값 '11140')")
    period_start: date = Field(..., description="집계 기간 시작일(오늘 기준 90일 전)")
    period_end: date = Field(..., description="집계 기간 종료일(오늘)")
    preference_base_date: str = Field(
        ...,
        description=(
            "선호지역(cgg_cd) 필터 위젯 3종(preference_price_trend/preference_top_trading_dongs/"
            "preference_top_trading_apts)에 실제 사용된 base_date. 이 지역 조건에 매칭되는 데이터가 "
            "최신 파티션에 없으면 과거 파티션으로 소급될 수 있다. 필터 없는 2개 위젯"
            "(seoul_top5_districts/price_change_top5)은 항상 최신 파티션(나이브 최신 base_date)을 "
            "사용하므로 이 필드와 다를 수 있다."
        ),
    )

    seoul_top5_districts: list[DistrictAvgPriceItem] = Field(
        default_factory=list, description="서울시 전체 자치구별 평균 매매가 Top5(자치구 필터 없음)"
    )
    price_change_top5: PriceChangeTop5 = Field(..., description="아파트 가격 상승/하락 Top5(전체 데이터 기준)")
    preference_price_trend: list[PreferencePriceTrendItem] = Field(
        default_factory=list, description="선호지역(cgg_cd) 실거래가 추이(최근 90일을 4구간으로 분할)"
    )
    preference_top_trading_dongs: list[TopTradingDongItem] = Field(
        default_factory=list, description="선호지역 내 거래량 상위 법정동 Top5"
    )
    preference_popular_dong: PopularDong | None = Field(
        default=None, description="선호지역 내 거래량 1위 법정동. 거래 데이터가 없으면 null"
    )
    preference_top_trading_apts: list[TopTradingAptItem] = Field(
        default_factory=list, description="선호지역 내 아파트 거래량 Top5"
    )
