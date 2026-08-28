# 동별 최근 90일 실거래(RTT) 요약 조회 api
from typing import Annotated

from fastapi import APIRouter, Query

from app.schemas.rtt import RttSummaryQuery, RttSummaryResponse
from app.services import rtt_service

router = APIRouter(prefix="/rtt", tags=["rtt"])


@router.get("/summary", response_model=RttSummaryResponse)
def get_rtt_summary(
    query: Annotated[RttSummaryQuery, Query()],
) -> RttSummaryResponse:
    """시군구코드(sgg_cd, 필수)+법정동코드(dong_cd, 선택) 조건으로 오늘 기준 최근 90일간의 RTT 실거래 데이터를
    집계하여 총 거래건수/총 거래금액/평균 거래가/최고 거래가/거래량 증감률과 함께 90일을 6구간으로 균등
    분할한 거래량 추이,
    평형별 거래 비중, 최근 실거래 목록, 거래량 상위 top5 단지를 단일 JSON으로 반환한다.
    dong_cd가 없으면 자치구 내 모든 법정동의 거래내역을 합산해 동일한 로직으로 계산하며,
    recent_trades 각 항목에는 자치구명/법정동명이 함께 채워진다."""
    summary = rtt_service.get_rtt_summary(sgg_cd=query.sgg_cd, dong_cd=query.dong_cd)
    return RttSummaryResponse(**summary)
