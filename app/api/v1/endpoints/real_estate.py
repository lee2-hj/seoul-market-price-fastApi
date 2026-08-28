# RAW 아파트 실거래 최신 목록 조회 api
from fastapi import APIRouter, HTTPException

from app.schemas.real_estate import RealEstateLatestResponse
from app.services import real_estate_service

router = APIRouter(prefix="/real-estate", tags=["real-estate"])


@router.get("/latest", response_model=RealEstateLatestResponse)
def get_real_estate_latest() -> RealEstateLatestResponse:
    """RAW 버킷(real_estate/year=yyyy/month=MM/day=dd)에서 오늘(없으면 가장 최근) 파티션의
    아파트 실거래 원본 목록을 조회한다."""
    try:
        base_date, items = real_estate_service.get_latest_listings()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return RealEstateLatestResponse(base_date=base_date, count=len(items), items=items)
