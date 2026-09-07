from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class MainMartRecentItem(BaseModel):
    """dm_main 마트의 최신 base_date 파티션을 직전 파티션과 비교해 신규/변경으로 판정된 개별 항목."""

    cgg_cd: str = Field(..., description="자치구코드")
    cgg_nm: str = Field(..., description="자치구명")
    stdg_cd: str = Field(..., description="법정동코드")
    stdg_nm: str = Field(..., description="법정동명")
    bldg_nm: str = Field(..., description="단지명")
    mno: str | None = Field(default=None, description="지번 본번")
    sno: str | None = Field(default=None, description="지번 부번")
    area: float = Field(..., description="전용면적(m2)")
    deal_date: date = Field(..., description="거래일(등록/업데이트일로 사용하는 기준 컬럼)")
    deal_cnt: int = Field(..., description="거래건수")
    thing_amt: int = Field(..., description="평균 매매가(total_thing_amt / deal_cnt, 반올림, 만원)")
    pyeong_amt: int = Field(..., description="평균 평당가(total_pyeong_amt / deal_cnt, 반올림, 만원)")
    latitude: float | None = Field(default=None, description="위도(지오코딩 실패 건은 null일 수 있음)")
    longitude: float | None = Field(default=None, description="경도(지오코딩 실패 건은 null일 수 있음)")
    status: Literal["NEW", "UPDATED"] = Field(
        ..., description="직전 base_date 파티션 대비 신규 등록(NEW)인지 값이 바뀐 갱신(UPDATED)인지"
    )


class MainMartRecentResponse(BaseModel):
    """`GET /api/v1/main-mart/recent` 응답 스키마."""

    base_date: str = Field(..., description="비교 기준 '최신' base_date 파티션 날짜")
    compared_base_date: str | None = Field(
        ..., description="비교에 사용한 '직전' base_date 파티션 날짜. 없으면 null(전량 NEW 처리됨)"
    )
    count: int = Field(..., description="반환된 항목 수")
    items: list[MainMartRecentItem] = Field(default_factory=list, description="신규/변경 항목 목록")
