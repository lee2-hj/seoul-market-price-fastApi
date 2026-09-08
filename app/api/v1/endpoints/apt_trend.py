# 아파트 실거래가 트렌드(최근 90일, apt_mkt_trends 마트) 조회 api
from typing import Annotated

from fastapi import APIRouter, Query
from fastapi_cache.decorator import cache

from app.schemas.apt_trend import AptTrendQuery, AptTrendResponse
from app.services import apt_trend_service

router = APIRouter(prefix="/apt-trend", tags=["apt-trend"])


@router.get("/summary", response_model=AptTrendResponse)
@cache(expire=300)  # DuckDB 마트 스캔이 5초 이상 걸려 nginx 499를 유발해, 5분간 응답을 인메모리 캐싱한다.
def get_apt_trend_summary(
    query: Annotated[AptTrendQuery, Query()],
) -> AptTrendResponse:
    """cgg_cd/stdg_cd/mno/sno/apt_name(모두 선택) 조건으로 오늘 기준 최근 90일간의 apt_mkt_trends 실거래 데이터를
    단지(cgg_cd+stdg_cd+apt_name) 단위로 집계하여, 총 거래건수/총 거래금액/평균 거래가/최고 거래가와 함께
    2주 단위 거래 추이, 전용면적별 거래 비율, 최근 실거래 내역, 면적별 요약 통계를 단일 JSON으로 반환한다.
    apt_name은 apt_mkt_trends의 실제 컬럼을 다른 마트 참조 없이 SQL WHERE(ILIKE)에서 직접 부분일치
    검색하며, 매칭되는 데이터가 없으면 빈 결과를 그대로 반환한다."""
    summary = apt_trend_service.get_apt_trend_summary(
        cgg_cd=query.cgg_cd,
        stdg_cd=query.stdg_cd,
        mno=query.mno,
        sno=query.sno,
        apt_name=query.apt_name,
    )
    return AptTrendResponse(**summary)
