#동별/자치구별 비교 api
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from app.schemas.compare import (
    DongPyeongCompareQuery,
    DongPyeongCompareResponse,
    RegionCompareResult,
)
from app.services import mart_service

router = APIRouter(prefix="/compare", tags=["compare"])


@router.get("/dong-pyeong", response_model=DongPyeongCompareResponse)
def get_dong_pyeong_compare(
    query: Annotated[DongPyeongCompareQuery, Query()],
) -> DongPyeongCompareResponse:
    """프론트가 선택한 지역1/지역2(자치구코드+법정동코드)의 동 단위 평균 시세를 MinIO Parquet에서 동적 조회한다."""
    try:
        (
            base_date,
            region1_base_date,
            region2_base_date,
            region1_items,
            region2_items,
            region1_summary,
            region2_summary,
        ) = mart_service.compare_dong_pyeong(
            region1_cgg_cd=query.region1_cgg_cd,
            region1_stdg_cd=query.region1_stdg_cd,
            region2_cgg_cd=query.region2_cgg_cd,
            region2_stdg_cd=query.region2_stdg_cd,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    region1_total_count, region1_avg_thing_amt, region1_avg_pyeong_amt = region1_summary
    region2_total_count, region2_avg_thing_amt, region2_avg_pyeong_amt = region2_summary

    region1_first_row = region1_items[0] if region1_items else {}
    region2_first_row = region2_items[0] if region2_items else {}

    return DongPyeongCompareResponse(
        base_date=base_date,
        region1=RegionCompareResult(
            cgg_cd=query.region1_cgg_cd,
            stdg_cd=query.region1_stdg_cd,
            base_date=region1_base_date,
            total_count=region1_total_count,
            avg_thing_amt=region1_avg_thing_amt,
            avg_pyeong_amt=region1_avg_pyeong_amt,
            latitude=region1_first_row.get("latitude"),
            longitude=region1_first_row.get("longitude"),
        ),
        region2=RegionCompareResult(
            cgg_cd=query.region2_cgg_cd,
            stdg_cd=query.region2_stdg_cd,
            base_date=region2_base_date,
            total_count=region2_total_count,
            avg_thing_amt=region2_avg_thing_amt,
            avg_pyeong_amt=region2_avg_pyeong_amt,
            latitude=region2_first_row.get("latitude"),
            longitude=region2_first_row.get("longitude"),
        ),
    )
