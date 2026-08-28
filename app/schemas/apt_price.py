from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

MetricType = Literal["pyeong", "thing_amt"]


class AptPriceTopBottomQuery(BaseModel):
    """`GET /api/v1/apt-price/top-bottom` 요청 Query Parameter."""

    region_cgg_cd: str | None = Field(
        default=None,
        pattern=r"^\d{5}$",
        description="자치구코드(5자리, 선택)",
        examples=["11680"],
    )
    region_stdg_cd: str | None = Field(
        default=None,
        pattern=r"^\d{5}$",
        description="법정동코드(5자리, 선택)",
        examples=["10600"],
    )
    metric_type: MetricType = Field(
        default="pyeong",
        description="정렬 기준. 'pyeong'=평균 평당가(avg_pyeong_amt), 'thing_amt'=평균 거래가(avg_thing_amt)",
        examples=["pyeong"],
    )


class AptPriceItem(BaseModel):
    """`dm_apt_price_avg` 마트의 아파트별 row 스키마(거래금액/평당가는 거래 건수 기준 평균값)."""

    base_date: date = Field(..., description="파티션 기준일자")
    cgg_cd: str = Field(..., description="자치구코드")
    cgg_nm: str = Field(..., description="자치구명")
    stdg_cd: str = Field(..., description="법정동코드")
    stdg_nm: str = Field(..., description="법정동명")
    bldg_nm: str = Field(..., description="건물명(아파트명)")
    latitude: float = Field(..., description="위도")
    longitude: float = Field(..., description="경도")
    is_exact_location: bool = Field(..., description="정확한 좌표 여부")
    updated_at: datetime = Field(..., description="데이터 갱신 시각")
    deal_cnt: int = Field(..., description="거래 건수")
    avg_thing_amt: int = Field(..., description="평균 거래가(total_thing_amt / deal_cnt, 반올림)")
    avg_pyeong_amt: int = Field(..., description="평균 평당가(total_pyeong_amt / deal_cnt, 반올림)")


class AptPriceTopBottomResponse(BaseModel):
    """`GET /api/v1/apt-price/top-bottom` 응답 스키마."""

    base_date: str = Field(..., description="실제 조회에 사용된 mart 파티션의 base_date")
    total_count: int = Field(..., description="조건에 해당하는 전체 거래건수 합계")
    avg_thing_amt: int = Field(..., description="조건에 해당하는 전체 평균 거래금액(반올림)")
    avg_pyeong_amt: int = Field(..., description="조건에 해당하는 전체 평균 평당가(반올림)")
    top: list[AptPriceItem] = Field(
        default_factory=list,
        description="metric_type 기준(평균 평당가 또는 평균 거래가) 내림차순 상위 5개.",
    )
    bottom: list[AptPriceItem] = Field(
        default_factory=list,
        description="metric_type 기준(평균 평당가 또는 평균 거래가) 오름차순 하위 5개.",
    )
