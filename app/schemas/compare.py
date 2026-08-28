from pydantic import BaseModel, Field


class DongPyeongCompareQuery(BaseModel):
    """`GET /api/v1/compare/dong-pyeong` 요청 Query Parameter."""

    region1_cgg_cd: str = Field(..., min_length=1, description="지역1 자치구코드", examples=["11680"])
    region1_stdg_cd: str | None = Field(default=None, min_length=1, description="지역1 법정동코드", examples=["10300"])
    region2_cgg_cd: str = Field(..., min_length=1, description="지역2 자치구코드", examples=["11650"])
    region2_stdg_cd: str | None = Field(default=None, min_length=1, description="지역2 법정동코드", examples=["10700"])


class RegionCompareResult(BaseModel):
    """단일 지역(자치구+자치동)에 대한 시세 조회 결과."""

    cgg_cd: str = Field(..., description="요청받은 자치구코드")
    stdg_cd: str | None = Field(default=None, description="요청받은 법정동코드")
    total_count: int = Field(..., description="해당 지역의 전체 거래건수 합계")
    avg_thing_amt: int = Field(..., description="해당 지역의 평균 매매가(SUM(total_thing_amt) / total_count, 반올림)")
    avg_pyeong_amt: int = Field(..., description="해당 지역의 평균 평당가(SUM(total_pyeong_amt) / total_count, 반올림)")
    latitude: float | None = Field(default=None, description="해당 지역 대표 위도(그룹 내 첫 row 기준)")
    longitude: float | None = Field(default=None, description="해당 지역 대표 경도(그룹 내 첫 row 기준)")


class DongPyeongCompareResponse(BaseModel):
    """`GET /api/v1/compare/dong-pyeong` 응답 스키마."""

    base_date: str = Field(..., description="실제 조회에 사용된 mart 파티션의 base_date")
    region1: RegionCompareResult
    region2: RegionCompareResult
