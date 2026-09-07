from fastapi import APIRouter

from app.api.v1.endpoints import (
    apt_compare,
    apt_price,
    apt_trend,
    compare,
    dashboard,
    dong_summary,
    main_mart,
    real_estate,
    region_apt_compare,
    rtt,
)

router = APIRouter(prefix="/api/v1")
router.include_router(compare.router)
router.include_router(apt_price.router)
router.include_router(dong_summary.router)
router.include_router(apt_compare.router)
router.include_router(rtt.router)
router.include_router(apt_trend.router)
router.include_router(region_apt_compare.router)
router.include_router(dashboard.router)
router.include_router(real_estate.router)
router.include_router(main_mart.router)
