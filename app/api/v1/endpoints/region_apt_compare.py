# 지역별 아파트 비교(dm_apt_recent_trade 마트, 최근 90일 실거래 사전집계) 조회 api
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from app.schemas.region_apt_compare import RegionAptCompareQuery, RegionAptCompareResponse
from app.services import region_apt_compare_service

router = APIRouter(prefix="/region-apt-compare", tags=["region-apt-compare"])


@router.get("", response_model=RegionAptCompareResponse)
def get_region_apt_compare(
    query: Annotated[RegionAptCompareQuery, Query()],
) -> RegionAptCompareResponse:
    """아파트1(cgg_cd_1/bjd_cd_1/apt_nm_1/mno_1/sno_1)과 아파트2(cgg_cd_2/bjd_cd_2/apt_nm_2/mno_2/sno_2)를
    각각 자치구코드+법정동코드+아파트명+지번 본번/부번(모두 필수)으로 특정하여, dm_apt_recent_trade 마트의
    최신 파티션(최근 90일 실거래 사전집계)에서 평균 매매가/평균 평당가/거래건수와 세대수/준공년도/사용승인일을
    조회해 aptGroup1/aptGroup2로 나누어 반환한다. 매칭되는 단지가 없거나 최근 90일간 거래가 없으면 해당
    그룹은 빈 객체({})로 반환된다(요청 자체는 404 처리하지 않음)."""
    try:
        group_1, group_2 = region_apt_compare_service.compare_region_apts(
            cgg_cd_1=query.cgg_cd_1,
            bjd_cd_1=query.bjd_cd_1,
            apt_nm_1=query.apt_nm_1,
            mno_1=query.mno_1,
            sno_1=query.sno_1,
            cgg_cd_2=query.cgg_cd_2,
            bjd_cd_2=query.bjd_cd_2,
            apt_nm_2=query.apt_nm_2,
            mno_2=query.mno_2,
            sno_2=query.sno_2,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return RegionAptCompareResponse(aptGroup1=group_1, aptGroup2=group_2)
