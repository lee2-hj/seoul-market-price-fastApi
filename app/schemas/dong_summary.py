from pydantic import BaseModel, Field


class DongSummaryQuery(BaseModel):
    """`GET /api/v1/dong/list` 요청 Query Parameter."""

    region_cgg: str | None = Field(
        default=None,
        description=(
            "자치구명 또는 자치구코드(선택). "
            "미지정 시 전체 데이터를 자치구(cgg_cd)별로, 지정 시 해당 자치구 내 데이터를 법정동(stdg_cd)별로 그룹화한다."
        ),
        examples=["강남구"],
    )


class DongSummaryGroup(BaseModel):
    """cgg_cd 또는 stdg_cd 기준으로 그룹화된 결과."""

    code: str = Field(..., description="그룹 기준 코드(region_cgg 미지정 시 cgg_cd, 지정 시 stdg_cd)")
    name: str = Field(..., description="그룹 기준 명칭(region_cgg 미지정 시 cgg_nm, 지정 시 stdg_nm)")
    total_count: int = Field(..., description="그룹 전체 거래건수 합계(SUM(deal_cnt))")
    avg_thing_amt: int = Field(..., description="그룹 평균 매매가(SUM(total_thing_amt) / total_count, 반올림)")
    avg_pyeong_amt: int = Field(..., description="그룹 평균 평당가(SUM(total_pyeong_amt) / total_count, 반올림)")


class DongSummaryResponse(BaseModel):
    """`GET /api/v1/dong/list` 응답 스키마."""

    base_date: str = Field(..., description="실제 조회에 사용된 mart 파티션의 base_date")
    groups: dict[str, DongSummaryGroup] = Field(
        default_factory=dict,
        description=(
            "그룹 코드(cgg_cd 또는 stdg_cd)를 key로 하는 단일 객체. "
            "region_cgg 미지정 시 cgg_cd별, 지정 시 stdg_cd별로 그룹화된다."
        ),
    )
