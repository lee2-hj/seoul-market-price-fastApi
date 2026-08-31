from typing import Any

from pydantic import BaseModel, Field


class RegionAptCompareQuery(BaseModel):
    """`GET /api/v1/region-apt-compare` 요청 Query Parameter. 아파트1/아파트2를 각각 자치구코드+법정동코드+
    아파트명+지번 본번/부번(모두 필수)으로 특정한다. 같은 법정동 안에 동명 단지가 존재할 수 있어 mno/sno까지
    포함해 정확히 매칭한다."""

    cgg_cd_1: str = Field(..., description="아파트1 자치구코드", examples=["11500"])
    bjd_cd_1: str = Field(..., description="아파트1 법정동코드", examples=["10300"])
    apt_nm_1: str = Field(..., description="아파트1 아파트명", examples=["강서힐스테이트"])
    mno_1: str = Field(..., description="아파트1 지번 본번", examples=["661"])
    sno_1: str = Field(..., description="아파트1 지번 부번", examples=["0"])

    cgg_cd_2: str = Field(..., description="아파트2 자치구코드", examples=["11500"])
    bjd_cd_2: str = Field(..., description="아파트2 법정동코드", examples=["10300"])
    apt_nm_2: str = Field(..., description="아파트2 아파트명", examples=["마곡엠밸리7단지"])
    mno_2: str = Field(..., description="아파트2 지번 본번", examples=["1398"])
    sno_2: str = Field(..., description="아파트2 지번 부번", examples=["0"])


class RegionAptCompareItem(BaseModel):
    """단지 하나의 비교 지표 + 메타데이터. 최근 90일간 거래가 없는(매칭되는 단지가 없는) 경우, 이 모델 대신
    빈 객체({})가 내려간다(RegionAptCompareResponse.aptGroup1/aptGroup2 참고)."""

    apt_name: str = Field(..., description="아파트명")
    base_date: str = Field(..., description="이 단지 조회에 실제 사용된 base_date")
    avg_deal_price: int = Field(..., description="최근 90일 평균 매매가(만원, 반올림한 정수)")
    avg_pyeong_price: int = Field(..., description="최근 90일 평균 평당가(만원, 반올림한 정수)")
    avg_pyeong: int = Field(..., description="최근 90일 평균 거래 전용면적(평, 반올림한 정수)")
    latest_trade_pyeong: int | None = Field(
        default=None, description="최근 거래 전용면적(평, 반올림한 정수)"
    )
    deal_count: int = Field(..., description="최근 90일 거래건수")
    total_households: int | None = Field(default=None, description="세대수")
    build_year: int | None = Field(default=None, description="준공년도")
    use_approval_date: str | None = Field(default=None, description="사용승인일")


class RegionAptCompareResponse(BaseModel):
    """`GET /api/v1/region-apt-compare` 응답: 아파트1/아파트2 비교 지표를 aptGroup1/aptGroup2로 분리해 반환한다.
    최근 90일간 거래가 없는(매칭되는 단지가 없는) 그룹은 RegionAptCompareItem 대신 빈 객체({})로 내려간다."""

    aptGroup1: RegionAptCompareItem | dict[str, Any] = Field(..., description="아파트1 비교 지표(없으면 {})")
    aptGroup2: RegionAptCompareItem | dict[str, Any] = Field(..., description="아파트2 비교 지표(없으면 {})")
