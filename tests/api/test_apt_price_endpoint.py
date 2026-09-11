"""GET /api/v1/apt-price/top-bottom 엔드포인트 회귀 테스트.

실제 사례 재현: dm_apt_price_avg 마트의 일부 row는 지오코딩 실패 등으로 latitude/longitude/
is_exact_location/updated_at 컬럼이 NULL로 적재된다. 스키마(AptPriceItem)에서 이 4개 필드가
필수(`...`)로 선언돼 있으면, NULL row가 top/bottom에 포함될 때 pydantic ValidationError로
응답 전체가 500(ResponseValidationError)으로 실패한다. 이 4개 필드는 Optional(기본값 None)로
처리해 NULL row도 정상 200 응답에 포함되어야 한다."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.services import apt_price_service

client = TestClient(app)

_NULL_LOCATION_ROW = {
    "base_date": "2025-11-07",
    "cgg_cd": "11680",
    "cgg_nm": "강남구",
    "stdg_cd": "10300",
    "stdg_nm": "개포동",
    "bldg_nm": "지오코딩실패단지",
    "latitude": None,
    "longitude": None,
    "is_exact_location": None,
    "updated_at": None,
    "deal_cnt": 3,
    "avg_thing_amt": 100000,
    "avg_pyeong_amt": 5000,
}


def test_top_bottom_returns_200_when_location_columns_are_null(monkeypatch):
    """latitude/longitude/is_exact_location/updated_at이 모두 NULL인 row가 섞여 있어도
    응답은 200이어야 하며(회귀 전에는 ResponseValidationError로 500), 해당 필드는 null로
    내려온다."""

    def fake_get_top_bottom(*, region_cgg_cd, region_stdg_cd, metric_type):
        return "2025-11-07", [_NULL_LOCATION_ROW], [], 3, 100000, 5000

    monkeypatch.setattr(apt_price_service, "get_top_bottom", fake_get_top_bottom)

    response = client.get(
        "/api/v1/apt-price/top-bottom", params={"region_cgg_cd": "11680", "metric_type": "pyeong"}
    )

    assert response.status_code == 200
    body = response.json()
    top_item = body["top"][0]
    assert top_item["latitude"] is None
    assert top_item["longitude"] is None
    assert top_item["is_exact_location"] is None
    assert top_item["updated_at"] is None
    assert top_item["bldg_nm"] == "지오코딩실패단지"


def test_top_bottom_still_returns_values_when_location_present(monkeypatch):
    """정상 케이스(회귀 없음 확인): 좌표 컬럼이 채워진 row는 그대로 값이 내려와야 한다."""

    row = {**_NULL_LOCATION_ROW, "latitude": 37.48, "longitude": 127.05, "is_exact_location": True}

    def fake_get_top_bottom(*, region_cgg_cd, region_stdg_cd, metric_type):
        return "2025-11-07", [row], [], 3, 100000, 5000

    monkeypatch.setattr(apt_price_service, "get_top_bottom", fake_get_top_bottom)

    response = client.get(
        "/api/v1/apt-price/top-bottom", params={"region_cgg_cd": "11680", "metric_type": "pyeong"}
    )

    assert response.status_code == 200
    top_item = response.json()["top"][0]
    assert top_item["latitude"] == 37.48
    assert top_item["longitude"] == 127.05
    assert top_item["is_exact_location"] is True
