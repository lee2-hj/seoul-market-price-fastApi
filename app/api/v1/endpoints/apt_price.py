# 아파트당 평균가격 api
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from app.schemas.apt_price import AptPriceTopBottomQuery, AptPriceTopBottomResponse
from app.services import apt_price_service

router = APIRouter(prefix="/apt-price", tags=["apt-price"])


@router.get("/top-bottom", response_model=AptPriceTopBottomResponse)
def get_apt_price_top_bottom(
    query: Annotated[AptPriceTopBottomQuery, Query()],
) -> AptPriceTopBottomResponse:
    """지정된(선택적) 지역 내 아파트별 metric_type 기준(평균 평당가 또는 평균 거래가) 상위/하위 5개를 MinIO Parquet에서 동적 조회한다."""
    try:
        base_date, top_items, bottom_items, total_count, avg_thing_amt, avg_pyeong_amt = (
            apt_price_service.get_top_bottom(
                region_cgg_cd=query.region_cgg_cd,
                region_stdg_cd=query.region_stdg_cd,
                metric_type=query.metric_type,
            )
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return AptPriceTopBottomResponse(
        base_date=base_date,
        total_count=total_count,
        avg_thing_amt=avg_thing_amt,
        avg_pyeong_amt=avg_pyeong_amt,
        top=top_items,
        bottom=bottom_items,
    )
