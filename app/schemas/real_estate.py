from datetime import date

from pydantic import BaseModel, Field


class RealEstateListingItem(BaseModel):
    """아파트(건물) 단위로 집계된 최신 실거래 항목. 같은 날 동일 건물(자치구+법정동+지번+건물명)에
    여러 거래가 있으면 매매가/평당가는 해당 거래들의 평균값이다."""

    apt_name: str = Field(..., description="아파트명(BLDG_NM)")
    cgg_nm: str = Field(..., description="자치구명(CGG_NM)")
    stdg_nm: str = Field(..., description="법정동명(STDG_NM)")
    thing_amt: int = Field(..., description="매매가(만원). 같은 날 동일 건물 거래가 여러 건이면 평균, 반올림")
    pyeong_amt: int = Field(
        ..., description="평당가(만원/평) = 매매가 / (전용면적(ARCH_AREA, ㎡) / 3.305785), 반올림"
    )
    price_change: int | None = Field(
        ...,
        description=(
            "아파트별 직전 업데이트(같은 건물의 가장 최근 이전 거래일) 매매가 대비 가격 변동(만원). "
            "이전 거래 이력이 없으면 null."
        ),
    )
    update_date: date = Field(..., description="업데이트 일자(해당 거래가 속한 RAW 파티션 날짜)")


class RealEstateLatestResponse(BaseModel):
    """`GET /api/v1/real-estate/latest` 응답 스키마."""

    base_date: str = Field(..., description="실제 조회에 사용된 RAW 파티션의 날짜(YYYY-MM-DD)")
    count: int = Field(..., description="조회된 아파트(건물) 개수")
    items: list[RealEstateListingItem] = Field(default_factory=list, description="아파트별 최신 실거래 목록")
