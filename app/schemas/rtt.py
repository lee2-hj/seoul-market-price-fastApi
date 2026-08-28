from datetime import date

from pydantic import BaseModel, Field


class RttSummaryQuery(BaseModel):
    """`GET /api/v1/rtt/summary` 요청 Query Parameter."""

    sgg_cd: str = Field(..., pattern=r"^\d{5}$", description="시군구코드(5자리, 필수)", examples=["11680"])
    dong_cd: str | None = Field(
        default=None,
        pattern=r"^\d{5}$",
        description="법정동코드(5자리, 선택). 미지정 시 자치구(sgg_cd) 내 모든 법정동의 거래내역을 합산해 조회한다.",
        examples=["10300"],
    )


class RttBiweeklyTrend(BaseModel):
    """90일 조회 구간을 6개로 균등 분할한 구간별 거래량/평균 거래가 추이 항목."""

    period_label: str = Field(..., description="기간 식별자. 'YYYY-MM-DD/YYYY-MM-DD'(시작일/종료일) 형식")
    start_date: date = Field(..., description="구간 시작일")
    end_date: date = Field(..., description="구간 종료일")
    deal_cnt: int = Field(..., description="해당 구간 총 거래건수")
    avg_trade_amount: int = Field(..., description="해당 구간 평균 거래가(반올림)")


class RttPyeongDistribution(BaseModel):
    """평(면적)별 거래 비중 항목."""

    pyeong_grp: str = Field(
        ...,
        description=(
            "평형 그룹. 10평 단위이며 상한 없이 실제 거래 데이터 기준으로 동적으로 생성된다"
            "(예: '10','20',...,'50','60'. 10평 미만은 '10'에 포함)."
        ),
    )
    deal_cnt: int = Field(..., description="해당 평형 그룹 거래건수")
    ratio: float = Field(..., description="전체 거래건수 대비 비중(%), 소수 둘째 자리 반올림. 비중 0%인 그룹은 응답에서 제외된다")


class RttRecentTrade(BaseModel):
    """최근 실거래 개별 항목."""

    apt_name: str = Field(..., description="아파트명")
    mno: str = Field(..., description="지번 본번")
    sno: str = Field(..., description="지번 부번")
    deal_date: date = Field(..., description="거래일")
    floor: int = Field(..., description="거래 층수")
    trade_amount: float = Field(..., description="거래금액")
    pyeong: float = Field(..., description="평형")
    exclusive_area_m2: float = Field(..., description="전용면적(㎡)")
    sgg_nm: str | None = Field(
        default=None, description="시군구명. 요청에 dong_cd가 없을 때(자치구 전체 조회)만 값이 채워진다."
    )
    dong_nm: str | None = Field(
        default=None, description="법정동명. 요청에 dong_cd가 없을 때(자치구 전체 조회)만 값이 채워진다."
    )


class RttTopVolumeItem(BaseModel):
    """거래량 상위 단지 항목."""

    apt_name: str = Field(..., description="아파트명")
    mno: str = Field(..., description="지번 본번")
    sno: str = Field(..., description="지번 부번")
    deal_cnt: int = Field(..., description="거래건수")
    avg_trade_amount: int = Field(..., description="평균 거래가(반올림)")


class RttSummaryResponse(BaseModel):
    """`GET /api/v1/rtt/summary` 응답 스키마. 조회 기준일로부터 최근 90일간의 실거래 데이터를 집계한다."""

    sgg_cd: str = Field(..., description="시군구코드")
    sgg_nm: str | None = Field(default=None, description="시군구명")
    dong_cd: str | None = Field(
        default=None, description="법정동코드. 요청 시 미지정했다면 null(자치구 전체 집계)"
    )
    dong_nm: str | None = Field(
        default=None, description="법정동명. dong_cd 미지정 시(자치구 전체 집계) null"
    )
    period_start: date = Field(..., description="집계 기간 시작일(오늘 기준 90일 전)")
    period_end: date = Field(..., description="집계 기간 종료일(오늘)")

    total_deal_cnt: int = Field(..., description="기간 내 일자들의 거래건수 총합")
    total_trade_amount: int = Field(..., description="기간 내 거래건수 총 거래금액")
    avg_trade_amount: int = Field(..., description="평균 거래가(총 거래금액 / 총 거래건수, 반올림)")
    max_trade_amount: int = Field(..., description="기간 내 일자들 중 최고 거래가")
    volume_change_rate: float | None = Field(
        default=None,
        description=(
            "최근 90일 동안의 거래량 증감률(%). 90일을 절반(이전 45일/최근 45일)으로 나눠 "
            "(최근 45일 거래건수 - 이전 45일 거래건수) / 이전 45일 거래건수 * 100 으로 계산한다. "
            "이전 45일 거래건수가 0이면 산출 불가로 null을 반환한다."
        ),
    )

    biweekly_trend: list[RttBiweeklyTrend] = Field(
        default_factory=list, description="90일을 6구간으로 균등 분할한 거래량/평균 거래가 추이"
    )
    pyeong_distribution: list[RttPyeongDistribution] = Field(
        default_factory=list, description="평(면적)별 거래 비중"
    )
    recent_trades: list[RttRecentTrade] = Field(
        default_factory=list, description="최근 실거래 데이터(거래일 최신순)"
    )
    top5_by_volume: list[RttTopVolumeItem] = Field(
        default_factory=list, description="거래량 상위 top5 단지"
    )
