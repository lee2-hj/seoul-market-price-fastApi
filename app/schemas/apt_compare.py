from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

QueryType = Literal["pyeong", "floor"]

PYEONG_GRP_VALUES = {"10", "20", "30", "40"}
FLOOR_GRP_VALUES = {"LOW", "MID", "HIGH"}


class AptCompareQuery(BaseModel):
    """`GET /api/v1/apt-price/apt-compare` 요청 Query Parameter."""

    cgg_cd: str = Field(..., pattern=r"^\d{5}$", description="자치구코드(5자리)", examples=["11500"])
    stdg_cd: str = Field(..., pattern=r"^\d{5}$", description="법정동코드(5자리)", examples=["10300"])
    bldg_nm: str | None = Field(
        default=None, min_length=1, description="건물명(아파트명, 선택)", examples=["강서힐스테이트"]
    )
    mno: str = Field(..., min_length=1, description="지번 본번", examples=["123"])
    sno: str = Field(..., min_length=1, description="지번 부번", examples=["4"])
    query_type: QueryType = Field(
        ...,
        description="조회 타입. 'pyeong'=평단가(dm_apt_pyeong_price), 'floor'=층별가(dm_apt_flr_price)",
        examples=["pyeong"],
    )
    grp: str = Field(
        ...,
        description=(
            "그룹 필터(필수). query_type='pyeong'이면 10/20/30/40 중 하나(40은 40평 이상 포함), "
            "query_type='floor'이면 LOW/MID/HIGH 중 하나."
        ),
        examples=["30"],
    )
    grp2: str = Field(
        ...,
        description=(
            "그룹 필터2(필수). grp와 동일한 방식으로 받으며, query_type='pyeong'이면 10/20/30/40 중 하나"
            "(40은 40평 이상 포함), query_type='floor'이면 LOW/MID/HIGH 중 하나."
        ),
        examples=["40"],
    )

    @model_validator(mode="after")
    def _validate_grp(self) -> "AptCompareQuery":
        allowed = PYEONG_GRP_VALUES if self.query_type == "pyeong" else FLOOR_GRP_VALUES
        if self.grp not in allowed:
            raise ValueError(
                f"query_type='{self.query_type}'일 때 grp는 {sorted(allowed)} 중 하나여야 합니다."
            )
        if self.grp2 not in allowed:
            raise ValueError(
                f"query_type='{self.query_type}'일 때 grp2는 {sorted(allowed)} 중 하나여야 합니다."
            )
        return self


class AptCompareGroup(BaseModel):
    """grp/grp2 각각에 대응하는 거래/비교 지표(단지 공통 정보 제외)."""

    pyeong_grp: str | None = Field(default=None, description="평형 그룹(query_type='pyeong'일 때만 존재)")
    flr_grp: str | None = Field(default=None, description="층 그룹(query_type='floor'일 때만 존재)")
    deal_cnt: int = Field(..., description="거래건수")
    avg_thing_amt: int = Field(..., description="평균 거래가(total_thing_amt/deal_cnt, 반올림한 정수)")
    avg_pyeong_amt: int = Field(..., description="평균 평당가(total_pyeong_amt/deal_cnt, 반올림한 정수)")
    recent_thing_amt: int | None = Field(default=None, description="최근 거래가")
    recent_pyeong_amt: int | None = Field(default=None, description="최근 평당가")
    recent_deal_date: str | None = Field(default=None, description="최근 거래일")
    recent_supply_pyeong: int | None = Field(default=None, description="최근 공급면적(평, 반올림한 정수, query_type='pyeong'일 때만 존재)")
    recent_floor: int | None = Field(default=None, description="최근 거래 층수(query_type='floor'일 때만 존재)")


class AptCompareResponse(BaseModel):
    """`GET /api/v1/apt-price/apt-compare` 응답: 단지 공통 정보는 최상위, grp/grp2는 각각 단일 객체."""

    base_date: str = Field(..., description="마트 최신 파티션 기준일")
    cgg_cd: str = Field(..., description="자치구코드")
    cgg_nm: str | None = Field(default=None, description="자치구명")
    stdg_cd: str = Field(..., description="법정동코드")
    stdg_nm: str | None = Field(default=None, description="법정동명")
    bldg_nm: str | None = Field(default=None, description="건물명(아파트명)")
    latitude: float | None = Field(default=None, description="위도")
    longitude: float | None = Field(default=None, description="경도")
    is_exact_location: bool | None = Field(default=None, description="정확한 좌표 여부")
    updated_at: datetime | None = Field(default=None, description="데이터 갱신 시각")
    grp: AptCompareGroup | None = Field(default=None, description="grp 파라미터로 조회한 그룹 지표")
    grp2: AptCompareGroup | None = Field(default=None, description="grp2 파라미터로 조회한 그룹 지표")
