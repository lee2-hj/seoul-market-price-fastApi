from fastapi import APIRouter, HTTPException

from app.schemas.main_mart import MainMartRecentResponse
from app.services import main_mart_service

router = APIRouter(prefix="/main-mart", tags=["main-mart"])


@router.get("/recent", response_model=MainMartRecentResponse)
def get_main_mart_recent() -> MainMartRecentResponse:
    """dm_main 마트의 최신 base_date 파티션을 직전 파티션과 비교해 신규/변경 항목만 조회한다."""
    try:
        base_date, compared_base_date, items = main_mart_service.get_recent_changes()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return MainMartRecentResponse(
        base_date=base_date, compared_base_date=compared_base_date, count=len(items), items=items
    )
