"""GET /api/v1/apt-price/apt-compare 엔드포인트 회귀 테스트.

실제 사례 재현: cgg_cd=11680/stdg_cd=10300/bldg_nm=개포2차현대아파트(220)/mno=0655/sno=0002/
query_type=floor/grp=LOW/grp2=HIGH 호출 시, grp/grp2 조회(apt_compare_service.compare_apartments)는
성공했는데 query_type='floor'일 때만 추가로 호출되는 부가 정보 조회
(apt_compare_service.fetch_recent_supply_pyeong)가 MinIO 일시적 IO 오류로 실패하면서 응답
전체가 500으로 실패했다. fetch_recent_supply_pyeong은 recent_supply_pyeong(스키마상 Optional)
필드 하나만 보완하는 부가 조회이므로, 이 조회 하나가 실패해도 이미 성공한 grp/grp2 데이터는
그대로 정상 반환되어야 한다(그 필드만 None)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.services import apt_compare_service

client = TestClient(app)

_QUERY_PARAMS = {
    "cgg_cd": "11680",
    "stdg_cd": "10300",
    "bldg_nm": "개포2차현대아파트(220)",
    "mno": "0655",
    "sno": "0002",
    "query_type": "floor",
    "grp": "LOW",
    "grp2": "HIGH",
}

_GRP_ROW = {
    "flr_grp": "LOW",
    "deal_cnt": 1,
    "total_thing_amt": 259000,
    "total_pyeong_amt": 8471,
    "recent_thing_amt": 259000,
    "recent_pyeong_amt": 8471,
    "recent_deal_date": "2025-11-07",
    "recent_floor": 5,
    "cgg_nm": "강남구",
    "stdg_nm": "개포동",
}


def test_apt_compare_degrades_to_none_when_supply_pyeong_lookup_fails(monkeypatch):
    """recent_supply_pyeong 보완 조회가 실패해도(예: 스토리지 일시적 IO 오류) 응답은 200으로
    정상 반환되고, 이미 조회된 grp 데이터는 그대로 담겨야 한다."""

    def fake_compare_apartments(*, cgg_cd, stdg_cd, bldg_nm, mno, sno, query_type, grp):
        if grp == "LOW":
            return "2025-11-07", [_GRP_ROW]
        return "2025-11-07", []  # HIGH 그룹은 매칭 없음

    def fake_fetch_recent_supply_pyeong(**kwargs):
        raise IOError("Could not connect to server error for HTTP GET")

    monkeypatch.setattr(apt_compare_service, "compare_apartments", fake_compare_apartments)
    monkeypatch.setattr(
        apt_compare_service, "fetch_recent_supply_pyeong", fake_fetch_recent_supply_pyeong
    )

    response = client.get("/api/v1/apt-price/apt-compare", params=_QUERY_PARAMS)

    assert response.status_code == 200
    body = response.json()
    assert body["grp"]["flr_grp"] == "LOW"
    assert body["grp"]["deal_cnt"] == 1
    # response_model_exclude_none=True라 None 필드는 키 자체가 응답에서 빠진다(기존 관례).
    assert "recent_supply_pyeong" not in body["grp"]
    assert "grp2" not in body  # HIGH 그룹은 매칭 없어 응답에서 제외(response_model_exclude_none)


def test_apt_compare_uses_supply_pyeong_when_lookup_succeeds(monkeypatch):
    """정상 케이스(회귀 없음 확인): 보완 조회가 성공하면 그 값이 그대로 채워져야 한다."""

    def fake_compare_apartments(*, cgg_cd, stdg_cd, bldg_nm, mno, sno, query_type, grp):
        if grp == "LOW":
            return "2025-11-07", [_GRP_ROW]
        return "2025-11-07", []

    monkeypatch.setattr(apt_compare_service, "compare_apartments", fake_compare_apartments)
    monkeypatch.setattr(
        apt_compare_service, "fetch_recent_supply_pyeong", lambda **kwargs: 25.71
    )

    response = client.get("/api/v1/apt-price/apt-compare", params=_QUERY_PARAMS)

    assert response.status_code == 200
    assert response.json()["grp"]["recent_supply_pyeong"] == 26  # round(25.71)
