# 대시보드 6개 위젯(dm_apt_price_avg 마트, 최근 90일) 조회 api
from typing import Annotated

from fastapi import APIRouter, Query
from fastapi_cache.decorator import cache

from app.schemas.dashboard import DashboardQuery, DashboardResponse
from app.services import dashboard_service

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardResponse)
@cache(expire=300)  # DuckDB 마트 스캔이 5초 이상 걸려 nginx 499를 유발해, 5분간 응답을 인메모리 캐싱한다.
def get_dashboard(
    query: Annotated[DashboardQuery, Query()],
) -> DashboardResponse:
    """dm_apt_price_avg 마트의 오늘 기준 최근 90일 데이터를 집계하여, 서울 자치구별 평균 매매가 Top5,
    아파트 가격 상승/하락 Top5, 선호지역(cgg_cd) 실거래가 추이(4구간), 선호지역 거래량 상위 법정동 Top5,
    선호지역 인기 법정동, 선호지역 아파트 거래량 Top5를 단일 JSON으로 반환한다.
    cgg_cd가 없거나 빈 값이면 '서울시 중구'(11140)로 대체한다. 선호지역 필터 위젯 3종은 그 지역 조건에
    매칭되는 데이터가 있는 base_date까지 소급 조회하며(응답의 preference_base_date), 필터 없는 2개
    위젯은 항상 최신 파티션을 사용한다."""
    summary = dashboard_service.get_dashboard(cgg_cd=query.cgg_cd)
    return DashboardResponse(**summary)
