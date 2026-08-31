# apt_compare.py 명세

## 1. 메타 정보

| 항목 | 값 |
|---|---|
| source_path | backend_fastApi/app/api/v1/endpoints/apt_compare.py |
| source_sha256 | fb53c1da5c7897078787770cd07927a2819f26234699d44482b3cb127d38ca8b |
| source_lines | 106 |

## 2. 역할 요약

`/apt-price/apt-compare` prefix 라우터를 정의하고, `GET /apt-price/apt-compare`에서 `apt_compare_service.compare_apartments`를 두 그룹(grp/grp2)에 대해 호출한 뒤 `_build_group`으로 각각 지표를 가공해 `AptCompareResponse`로 반환한다.

## 3. 외부 인터페이스

| 이름 | 종류 | 시그니처 | 반환 타입 |
|---|---|---|---|
| router | const | `router = APIRouter(prefix="/apt-price/apt-compare", tags=["apt-compare"])` | APIRouter |
| _build_group | function | `def _build_group(item: dict[str, Any] \| None, fallback_supply_pyeong: float \| None = None) -> AptCompareGroup \| None` | AptCompareGroup \| None |
| get_apt_compare | function | `def get_apt_compare(query: Annotated[AptCompareQuery, Query()]) -> AptCompareResponse` | AptCompareResponse |

## 4. 의존성(imports)

- 표준 라이브러리:
  - `from typing import Annotated, Any`
- 서드파티:
  - `from fastapi import APIRouter, HTTPException, Query`
- 내부 모듈:
  - `from app.schemas.apt_compare import AptCompareGroup, AptCompareQuery, AptCompareResponse`
  - `from app.services import apt_compare_service`

파일 최상단 주석(1행): `# 아파트 평단가/층별가 자치구+법정동 비교 조회 api`

## 5. 로직 상세

### router

- 목적: `/apt-price/apt-compare` prefix, `apt-compare` 태그의 라우터 생성.
- 처리 흐름: `router = APIRouter(prefix="/apt-price/apt-compare", tags=["apt-compare"])`.
- 반환값: 해당 없음.

### _build_group

- 목적(원문 docstring): "row 하나를 grp/grp2 비교 지표(avg_thing_amt/avg_pyeong_amt는 deal_cnt로 나눈 반올림값)로 변환한다. row에 recent_supply_pyeong이 없는 경우(query_type='floor') fallback_supply_pyeong으로 보완한다."
- 파라미터:
  - `item: dict[str, Any] | None` — 서비스가 반환한 row 딕셔너리(없을 수 있음).
  - `fallback_supply_pyeong: float | None = None` — `item`에 `recent_supply_pyeong` 키가 없을 때 사용할 대체값.
- 처리 흐름:
  1. `if item is None: return None`.
  2. `deal_cnt = item.get("deal_cnt") or 0`.
  3. `total_thing_amt = item.get("total_thing_amt")`; `total_pyeong_amt = item.get("total_pyeong_amt")`.
  4. `avg_thing_amt = round(total_thing_amt / deal_cnt) if deal_cnt and total_thing_amt is not None else 0`.
  5. `avg_pyeong_amt = round(total_pyeong_amt / deal_cnt) if deal_cnt and total_pyeong_amt is not None else 0`.
  6. `recent_supply_pyeong = item.get("recent_supply_pyeong", fallback_supply_pyeong)`(키 자체가 없을 때만 fallback 사용, 딕셔너리에 키가 있고 값이 None이면 fallback 미적용).
  7. `return AptCompareGroup(pyeong_grp=item.get("pyeong_grp"), flr_grp=item.get("flr_grp"), deal_cnt=deal_cnt, avg_thing_amt=avg_thing_amt, avg_pyeong_amt=avg_pyeong_amt, recent_thing_amt=item.get("recent_thing_amt"), recent_pyeong_amt=item.get("recent_pyeong_amt"), recent_deal_date=item.get("recent_deal_date"), recent_supply_pyeong=round(recent_supply_pyeong) if recent_supply_pyeong is not None else None, recent_floor=item.get("recent_floor"))`.
- 반환값: `item`이 `None`이면 `None`. 아니면 위 필드로 구성된 `AptCompareGroup`.

### get_apt_compare

- 목적(원문 docstring): "query_type(평단가/층별가)에 해당하는 마트의 최신 파티션에서 자치구코드+법정동코드(+건물명, +그룹/그룹2, 선택)가 일치하는 row를 조회한다. 단지 공통 정보(cgg_nm/stdg_nm/좌표 등)는 최상위에, grp/grp2로 조회한 거래 지표는 각각 단일 객체로 나누어 반환한다."
- 데코레이터: `@router.get("", response_model=AptCompareResponse, response_model_exclude_none=True)`.
- 파라미터: `query: Annotated[AptCompareQuery, Query()]`.
- 처리 흐름:
  1. `try:` 블록:
     a. `base_date, grp_rows = apt_compare_service.compare_apartments(cgg_cd=query.cgg_cd, stdg_cd=query.stdg_cd, bldg_nm=query.bldg_nm, mno=query.mno, sno=query.sno, query_type=query.query_type, grp=query.grp)`.
     b. `_base_date, grp2_rows = apt_compare_service.compare_apartments(cgg_cd=query.cgg_cd, stdg_cd=query.stdg_cd, bldg_nm=query.bldg_nm, mno=query.mno, sno=query.sno, query_type=query.query_type, grp=query.grp2)`(두 번째 호출의 base_date는 `_base_date`로 받고 사용하지 않음).
  2. `except FileNotFoundError as exc:` 이면 `raise HTTPException(status_code=404, detail=str(exc)) from exc`.
  3. `except Exception as exc:` 이면 `raise HTTPException(status_code=500, detail=f"S3 데이터 조회 중 오류가 발생했습니다: {exc}") from exc`.
  4. `grp_item = grp_rows[0] if grp_rows else None`; `grp2_item = grp2_rows[0] if grp2_rows else None`.
  5. `if grp_item is None and grp2_item is None:` 이면:
     a. `condition = f"cgg_cd='{query.cgg_cd}', stdg_cd='{query.stdg_cd}', mno='{query.mno}', sno='{query.sno}'"`.
     b. `if query.bldg_nm: condition += f", bldg_nm='{query.bldg_nm}'"`.
     c. `if query.grp: condition += f", grp='{query.grp}'"`.
     d. `if query.grp2: condition += f", grp2='{query.grp2}'"`.
     e. `raise HTTPException(status_code=404, detail=f"{condition}에 해당하는 데이터가 없습니다.")`.
  6. `common = grp_item or grp2_item or {}`.
  7. `fallback_supply_pyeong = None`; `if query.query_type == "floor":` 이면 `fallback_supply_pyeong = apt_compare_service.fetch_recent_supply_pyeong(cgg_cd=query.cgg_cd, stdg_cd=query.stdg_cd, bldg_nm=query.bldg_nm, mno=query.mno, sno=query.sno)`.
  8. `return AptCompareResponse(base_date=base_date, cgg_cd=query.cgg_cd, cgg_nm=common.get("cgg_nm"), stdg_cd=query.stdg_cd, stdg_nm=common.get("stdg_nm"), bldg_nm=common.get("bldg_nm", query.bldg_nm), latitude=common.get("latitude"), longitude=common.get("longitude"), is_exact_location=common.get("is_exact_location"), updated_at=common.get("updated_at"), grp=_build_group(grp_item, fallback_supply_pyeong), grp2=_build_group(grp2_item, fallback_supply_pyeong))`.
- 반환값: 정상 시 위 필드로 구성된 `AptCompareResponse`(응답 시 `response_model_exclude_none=True`로 `None` 필드는 응답 JSON에서 제외됨). 두 그룹 모두 매칭 row가 없으면 404, `detail`은 조립된 조건 문자열 + `"에 해당하는 데이터가 없습니다."`. 서비스에서 `FileNotFoundError` 발생 시 404. 그 외 예외는 500, `detail`은 `f"S3 데이터 조회 중 오류가 발생했습니다: {exc}"`.

## 6. 모듈 레벨 상수/설정값

없음.

## 7. 역참조(이 파일을 사용하는 곳)

- `app/api/v1/router.py` — `from app.api.v1.endpoints import (..., apt_compare, ...)` 후 `router.include_router(apt_compare.router)`로 등록.

## 8. 재생성 지침

> 위 내용을 근거로 `backend_fastApi/app/api/v1/endpoints/apt_compare.py` 파일을 동일한 로직으로 재작성하라. 여기 명시되지 않은 세부 구현(변수명 스타일, 코드 포맷 등)은 기존 프로젝트 컨벤션(PEP 8, 저장소 내 동일 계층 파일들의 스타일)을 따른다.
