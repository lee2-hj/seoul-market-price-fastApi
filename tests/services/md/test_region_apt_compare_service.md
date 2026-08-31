# test_region_apt_compare_service.py 명세

## 1. 메타 정보

| 항목 | 값 |
|---|---|
| source_path | backend_fastApi/tests/services/test_region_apt_compare_service.py |
| source_sha256 | 9bfcefc830c00306099e8f5328eb2f31a05758accc28cd98463ee2fb8ab8636b |
| source_lines | 73 |

## 2. 역할 요약

`region_apt_compare_service.compare_region_apts()`가 두 단지의 base_date 폴백을 서로 독립적으로 수행하는지(한쪽은 소급되어 매칭, 다른 쪽은 매칭 자체가 없어 빈 객체), 매칭된 단지라도 거래건수가 0이면 빈 객체를 유지하는지를 검증하는 회귀 테스트다.

모듈 docstring(원문): "region_apt_compare_service.compare_region_apts()의 독립 2-엔티티(단지1/단지2) base_date 폴백 회귀 테스트. 한쪽 단지만 소급되고 다른 쪽은 매칭 자체가 없어 빈 객체({})로 남는 케이스를 포함한다(명세서 5항, Phase 5 세 번째 테스트 항목)."

## 3. 외부 인터페이스

| 이름 | 종류 | 시그니처 | 반환 타입 |
|---|---|---|---|
| test_compare_region_apts_one_falls_back_other_has_no_match | function | `def test_compare_region_apts_one_falls_back_other_has_no_match(monkeypatch)` | None |
| test_compare_region_apts_matched_but_zero_trade_count_omits_base_date | function | `def test_compare_region_apts_matched_but_zero_trade_count_omits_base_date(monkeypatch)` | None |

## 4. 의존성(imports)

- 표준 라이브러리:
  - `from __future__ import annotations`
  - `from unittest.mock import MagicMock`
- 서드파티: 없음
- 내부 모듈:
  - `from app.services import region_apt_compare_service as svc`

## 5. 로직 상세

### test_compare_region_apts_one_falls_back_other_has_no_match(monkeypatch)

- Given:
  1. `fake_resolve_for_filter(con, mart_table, where_sql, params, **kwargs)`: `if params.get("apt_nm") == "아파트1": return "2026-08-27"`(주석: `# 단지1: 과거로 소급되어 매칭됨`); 아니면 `return None`(주석: `# 단지2: max_lookback 안에서 매칭 자체가 없음`).
  2. `monkeypatch.setattr(svc.duckdb_client, "get_connection", lambda: MagicMock())`.
  3. `monkeypatch.setattr(svc.duckdb_client, "resolve_base_date_for_filter", fake_resolve_for_filter)`.
  4. `monkeypatch.setattr(svc.duckdb_client, "resolve_base_date", lambda *a, **k: "2026-08-30")`.
  5. `fake_fetch_apt_row(con, base_date, cgg_cd, bjd_cd, apt_nm, mno, sno)`: `if apt_nm == "아파트1":` 이면 `{"apt_name": "아파트1", "trade_count": 3, "total_trade_amount": 30000, "total_price_per_pyeong": 9000, "total_pyeong": 90, "latest_trade_pyeong": 30.0, "household_count": 200, "build_year": 2010, "use_approval_date": "2010-05-01"}` 반환; 아니면 `return None`(주석: `# 단지2: 최근 90일 실거래 매칭 row 자체가 없음`).
  6. `monkeypatch.setattr(svc, "_fetch_apt_row", fake_fetch_apt_row)`.
- When: `group_1, group_2 = svc.compare_region_apts(cgg_cd_1="11500", bjd_cd_1="10300", apt_nm_1="아파트1", mno_1="1", sno_1="0", cgg_cd_2="11500", bjd_cd_2="10300", apt_nm_2="아파트2", mno_2="2", sno_2="0")`.
- Then(원문 assert, 주석 포함):
  - `assert group_1["apt_name"] == "아파트1"`
  - `assert group_1["base_date"] == "2026-08-27"`
  - 주석: `# 단지2는 매칭되는 row가 없으므로 base_date를 포함하지 않는 빈 객체여야 한다.`
  - `assert group_2 == {}`

### test_compare_region_apts_matched_but_zero_trade_count_omits_base_date(monkeypatch)

- 함수 docstring(원문): "단지를 찾긴 했지만(row 존재) 최근 90일 거래가 0건이면 기존 관례대로 빈 객체({})를 유지한다."
- Given:
  1. `monkeypatch.setattr(svc.duckdb_client, "get_connection", lambda: MagicMock())`.
  2. `monkeypatch.setattr(svc.duckdb_client, "resolve_base_date_for_filter", lambda *a, **k: "2026-08-30")`.
  3. `monkeypatch.setattr(svc.duckdb_client, "resolve_base_date", lambda *a, **k: "2026-08-30")`.
  4. `monkeypatch.setattr(svc, "_fetch_apt_row", lambda *a, **k: {"apt_name": "아파트1", "trade_count": 0})`.
- When: `group_1, group_2 = svc.compare_region_apts(cgg_cd_1="11500", bjd_cd_1="10300", apt_nm_1="아파트1", mno_1="1", sno_1="0", cgg_cd_2="11500", bjd_cd_2="10300", apt_nm_2="아파트1", mno_2="1", sno_2="0")`.
- Then(원문 assert):
  - `assert group_1 == {}`
  - `assert group_2 == {}`

## 6. 모듈 레벨 상수/설정값

없음.

## 7. 역참조(이 파일을 사용하는 곳)

- 없음(pytest가 자동 수집하는 테스트 모듈이며, 다른 소스 모듈이 import하지 않음).

## 8. 재생성 지침

> 위 내용을 근거로 `backend_fastApi/tests/services/test_region_apt_compare_service.py` 파일을 동일한 로직으로 재작성하라. 여기 명시되지 않은 세부 구현(변수명 스타일, 코드 포맷 등)은 기존 프로젝트 컨벤션(PEP 8, 저장소 내 동일 계층 파일들의 스타일)을 따른다.
