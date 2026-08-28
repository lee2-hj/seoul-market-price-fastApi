# 동별 데이터 그룹 집계 조회 api
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from app.schemas.dong_summary import DongSummaryQuery, DongSummaryResponse
from app.services import dong_summary_service

router = APIRouter(prefix="/dong", tags=["dong"])


@router.get("/list", response_model=DongSummaryResponse)
def get_dong_list(
    query: Annotated[DongSummaryQuery, Query()],
) -> DongSummaryResponse:
    """region_cgg 미지정 시 자치구(cgg_cd)별로, 지정 시 해당 자치구 내 법정동(stdg_cd)별로 그룹화하여
    그룹별 평균 매매가/평균 평당가/total_count를 조회한다."""
    try:
        base_date, groups = dong_summary_service.get_dong_summary(region_cgg=query.region_cgg)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return DongSummaryResponse(base_date=base_date, groups=groups)
