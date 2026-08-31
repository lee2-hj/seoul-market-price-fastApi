# test_mart_service.py 명세

## 1. 메타 정보

| 항목 | 값 |
|---|---|
| source_path | backend_fastApi/tests/services/test_mart_service.py |
| source_sha256 | 4f8874399979fb3942337adcdeca45d9452d2161f3c91a0cab43875021b35e74 |
| source_lines | 78 |

## 2. 역할 요약

`mart_service.compare_dong_pyeong()`이 지역1/지역2의 base_date 폴백을 서로 독립적으로 수행하는지(한쪽만 소급, 둘 다 소급 없음 두 케이스)를 검증하는 회귀 테스트다.

모듈 docstring(원문): "mart_service.compare_dong_pyeong()의 독립 2-엔티티(지역1/지역2) base_date 폴백 회귀 테스트.\n\n명세서 5항 4번: 지역1/지역2는 서로 독립적으로 폴백을 탐색하며, 한쪽만 소급되고 다른 쪽은 최신 날짜를 그대로 쓰는 것이 정상 동작이다."

## 3. 외부 인터페이스

| 이름 | 종류 | 시그니처 | 반환 타입 |
|---|---|---|---|
| test_compare_dong_pyeong_regions_fallback_independently | function | `def test_compare_dong_pyeong_regions_fallback_independently(monkeypatch)` | None |
| test_compare_dong_pyeong_both_regions_fall_back_to_naive_latest | function | `def test_compare_dong_pyeong_both_regions_fall_back_to_naive_latest(monkeypatch)` | None |

## 4. 의존성(imports)

- 표준 라이브러리:
  - `from __future__ import annotations`
  - `from unittest.mock import MagicMock`
- 서드파티: 없음
- 내부 모듈:
  - `from app.services import mart_service`

## 5. 로직 상세

### test_compare_dong_pyeong_regions_fallback_independently(monkeypatch)

- 함수 docstring(원문): "region1은 최신 파티션에 매칭 데이터가 있어 그대로 최신 날짜를 쓰고, region2만 매칭 데이터가 없어 과거로 소급되는 케이스."
- Given:
  1. `fake_resolve_for_filter(con, mart_table, where_sql, params, **kwargs)`: 주석 원문 "region1_where/region2_where는 _build_where_clause가 만든 조건이며 cgg_cd 값으로 구분된다." — `if params.get("cgg_cd") == "11680": return "2026-08-30"`(주석: `# region1: 최신 그대로`); `if params.get("cgg_cd") == "11650": return "2026-08-27"`(주석: `# region2: 소급됨`); 그 외는 `raise AssertionError(f"예상하지 못한 params: {params}")`.
  2. `monkeypatch.setattr(mart_service.duckdb_client, "get_connection", lambda: MagicMock())`.
  3. `monkeypatch.setattr(mart_service.duckdb_client, "resolve_base_date_for_filter", fake_resolve_for_filter)`.
  4. `monkeypatch.setattr(mart_service.duckdb_client, "resolve_base_date", lambda *a, **k: "2026-08-30")`.
  5. `monkeypatch.setattr(mart_service, "_fetch_region_rows", lambda con, base_date, *a, **k: [])`.
  6. `monkeypatch.setattr(mart_service, "_fetch_region_summary", lambda con, base_date, *a, **k: (0, 0, 0))`.
- When: `(base_date, region1_base_date, region2_base_date, region1_items, region2_items, region1_summary, region2_summary) = mart_service.compare_dong_pyeong(region1_cgg_cd="11680", region1_stdg_cd=None, region2_cgg_cd="11650", region2_stdg_cd=None)`.
- Then(원문 assert, 주석 포함):
  - `assert region1_base_date == "2026-08-30"`
  - `assert region2_base_date == "2026-08-27"`
  - 주석: `# 하위 호환용 최상위 base_date는 두 지역 중 더 최신인 날짜여야 한다.`
  - `assert base_date == "2026-08-30"`

### test_compare_dong_pyeong_both_regions_fall_back_to_naive_latest(monkeypatch)

- 함수 docstring(원문): "둘 다 매칭되는 과거 파티션이 없으면 각자 resolve_base_date()의 최신 파티션으로 폴백한다."
- Given:
  1. `monkeypatch.setattr(mart_service.duckdb_client, "get_connection", lambda: MagicMock())`.
  2. `monkeypatch.setattr(mart_service.duckdb_client, "resolve_base_date_for_filter", lambda *a, **k: None)`.
  3. `monkeypatch.setattr(mart_service.duckdb_client, "resolve_base_date", lambda *a, **k: "2026-08-30")`.
  4. `monkeypatch.setattr(mart_service, "_fetch_region_rows", lambda *a, **k: [])`.
  5. `monkeypatch.setattr(mart_service, "_fetch_region_summary", lambda *a, **k: (0, 0, 0))`.
- When: `base_date, region1_base_date, region2_base_date, *_ = mart_service.compare_dong_pyeong(region1_cgg_cd="00000", region1_stdg_cd=None, region2_cgg_cd="00001", region2_stdg_cd=None)`.
- Then(원문 assert): `assert region1_base_date == region2_base_date == base_date == "2026-08-30"`.

## 6. 모듈 레벨 상수/설정값

없음.

## 7. 역참조(이 파일을 사용하는 곳)

- 없음(pytest가 자동 수집하는 테스트 모듈이며, 다른 소스 모듈이 import하지 않음).

## 8. 재생성 지침

> 위 내용을 근거로 `backend_fastApi/tests/services/test_mart_service.py` 파일을 동일한 로직으로 재작성하라. 여기 명시되지 않은 세부 구현(변수명 스타일, 코드 포맷 등)은 기존 프로젝트 컨벤션(PEP 8, 저장소 내 동일 계층 파일들의 스타일)을 따른다.
