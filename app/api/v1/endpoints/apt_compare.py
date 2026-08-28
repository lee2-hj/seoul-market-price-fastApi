# 아파트 평단가/층별가 자치구+법정동 비교 조회 api
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas.apt_compare import AptCompareGroup, AptCompareQuery, AptCompareResponse
from app.services import apt_compare_service

router = APIRouter(prefix="/apt-price/apt-compare", tags=["apt-compare"])


def _build_group(item: dict[str, Any] | None, fallback_supply_pyeong: float | None = None) -> AptCompareGroup | None:
    """row 하나를 grp/grp2 비교 지표(avg_thing_amt/avg_pyeong_amt는 deal_cnt로 나눈 반올림값)로 변환한다.
    row에 recent_supply_pyeong이 없는 경우(query_type='floor') fallback_supply_pyeong으로 보완한다."""
    if item is None:
        return None
    deal_cnt = item.get("deal_cnt") or 0
    total_thing_amt = item.get("total_thing_amt")
    total_pyeong_amt = item.get("total_pyeong_amt")
    avg_thing_amt = round(total_thing_amt / deal_cnt) if deal_cnt and total_thing_amt is not None else 0
    avg_pyeong_amt = round(total_pyeong_amt / deal_cnt) if deal_cnt and total_pyeong_amt is not None else 0
    recent_supply_pyeong = item.get("recent_supply_pyeong", fallback_supply_pyeong)
    return AptCompareGroup(
        pyeong_grp=item.get("pyeong_grp"),
        flr_grp=item.get("flr_grp"),
        deal_cnt=deal_cnt,
        avg_thing_amt=avg_thing_amt,
        avg_pyeong_amt=avg_pyeong_amt,
        recent_thing_amt=item.get("recent_thing_amt"),
        recent_pyeong_amt=item.get("recent_pyeong_amt"),
        recent_deal_date=item.get("recent_deal_date"),
        recent_supply_pyeong=round(recent_supply_pyeong) if recent_supply_pyeong is not None else None,
        recent_floor=item.get("recent_floor"),
    )


@router.get("", response_model=AptCompareResponse, response_model_exclude_none=True)
def get_apt_compare(
    query: Annotated[AptCompareQuery, Query()],
) -> AptCompareResponse:
    """query_type(평단가/층별가)에 해당하는 마트의 최신 파티션에서 자치구코드+법정동코드(+건물명, +그룹/그룹2, 선택)가
    일치하는 row를 조회한다. 단지 공통 정보(cgg_nm/stdg_nm/좌표 등)는 최상위에, grp/grp2로 조회한 거래 지표는
    각각 단일 객체로 나누어 반환한다."""
    try:
        base_date, grp_rows = apt_compare_service.compare_apartments(
            cgg_cd=query.cgg_cd,
            stdg_cd=query.stdg_cd,
            bldg_nm=query.bldg_nm,
            mno=query.mno,
            sno=query.sno,
            query_type=query.query_type,
            grp=query.grp,
        )
        _base_date, grp2_rows = apt_compare_service.compare_apartments(
            cgg_cd=query.cgg_cd,
            stdg_cd=query.stdg_cd,
            bldg_nm=query.bldg_nm,
            mno=query.mno,
            sno=query.sno,
            query_type=query.query_type,
            grp=query.grp2,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"S3 데이터 조회 중 오류가 발생했습니다: {exc}") from exc

    grp_item = grp_rows[0] if grp_rows else None
    grp2_item = grp2_rows[0] if grp2_rows else None

    if grp_item is None and grp2_item is None:
        condition = f"cgg_cd='{query.cgg_cd}', stdg_cd='{query.stdg_cd}', mno='{query.mno}', sno='{query.sno}'"
        if query.bldg_nm:
            condition += f", bldg_nm='{query.bldg_nm}'"
        if query.grp:
            condition += f", grp='{query.grp}'"
        if query.grp2:
            condition += f", grp2='{query.grp2}'"
        raise HTTPException(status_code=404, detail=f"{condition}에 해당하는 데이터가 없습니다.")

    common = grp_item or grp2_item or {}

    fallback_supply_pyeong = None
    if query.query_type == "floor":
        fallback_supply_pyeong = apt_compare_service.fetch_recent_supply_pyeong(
            cgg_cd=query.cgg_cd,
            stdg_cd=query.stdg_cd,
            bldg_nm=query.bldg_nm,
            mno=query.mno,
            sno=query.sno,
        )

    return AptCompareResponse(
        base_date=base_date,
        cgg_cd=query.cgg_cd,
        cgg_nm=common.get("cgg_nm"),
        stdg_cd=query.stdg_cd,
        stdg_nm=common.get("stdg_nm"),
        bldg_nm=common.get("bldg_nm", query.bldg_nm),
        latitude=common.get("latitude"),
        longitude=common.get("longitude"),
        is_exact_location=common.get("is_exact_location"),
        updated_at=common.get("updated_at"),
        grp=_build_group(grp_item, fallback_supply_pyeong),
        grp2=_build_group(grp2_item, fallback_supply_pyeong),
    )
