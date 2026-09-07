from datetime import date

from pydantic import BaseModel, Field


class AptRecentRankQuery(BaseModel):
    """`GET /api/v1/apt-recent-rank/top-bottom` 요청 Query Parameter. rtt.py의 RttSummaryQuery와
    동일한 pattern 검증을 사용하되, 이 API는 "법정동 내"로 범위를 명시했으므로 dong_cd도 필수다."""

    sgg_cd: str = Field(..., pattern=r"^\d{5}$", description="구코드(5자리, 필수)", examples=["11680"])
    dong_cd: str = Field(..., pattern=r"^\d{5}$", description="법정동코드(5자리, 필수)", examples=["10300"])


class AptRecentRankItem(BaseModel):
    """RTT 마트의 개별 실거래 row에서 5개 필드만 추출한 랭킹 항목. 반올림/재계산 없이 원본 값
    그대로다."""

    apt_name: str = Field(..., description="아파트명")
    exclusive_area_m2: float = Field(..., description="전용면적(㎡)")
    pyeong: int = Field(..., description="평형(RTT 원본 값을 반올림한 정수, 소수점 제거)")
    floor: int = Field(..., description="거래 층수")
    trade_amount: float = Field(..., description="실거래가(RTT 원본 값 그대로, 가공 없음)")


class AptRecentRankResponse(BaseModel):
    """`GET /api/v1/apt-recent-rank/top-bottom` 응답 스키마. 조회 기준일로부터 최근 90일간(데이터가
    없으면 앵커 폴백으로 소급된 구간) 해당 법정동 내 개별 실거래 기준 상위 5건/하위 5건을 반환한다."""

    sgg_cd: str = Field(..., description="구코드")
    sgg_nm: str | None = Field(default=None, description="구명")
    dong_cd: str = Field(..., description="법정동코드")
    dong_nm: str | None = Field(default=None, description="법정동명")
    period_start: date = Field(
        ...,
        description=(
            "집계 기간 시작일. 기본은 오늘 기준 90일 전이지만, 그 구간에 조건에 맞는 거래가 없으면 "
            "조건에 맞는 데이터가 있는 가장 최근 날짜 기준 90일 구간으로 소급될 수 있다(이 경우 오늘 "
            "기준이 아니다)."
        ),
    )
    period_end: date = Field(
        ...,
        description=(
            "집계 기간 종료일. 기본은 오늘이지만, period_start와 마찬가지로 소급이 일어나면 오늘이 "
            "아닐 수 있다."
        ),
    )
    top: list[AptRecentRankItem] = Field(
        default_factory=list, description="실거래가 상위 5건(내림차순). 매칭 데이터가 없으면 빈 리스트"
    )
    bottom: list[AptRecentRankItem] = Field(
        default_factory=list,
        description="실거래가 하위 5건(오름차순). 매칭 데이터가 5건 이하이면(top과 중복 방지) 빈 리스트",
    )
