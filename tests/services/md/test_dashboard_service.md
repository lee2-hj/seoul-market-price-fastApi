# test_dashboard_service.py 명세

## 1. 메타 정보

| 항목 | 값 |
|---|---|
| source_path | backend_fastApi/tests/services/test_dashboard_service.py |
| source_sha256 | ae9e91e511cbaddf15dd233cb1ce4ef58193c4d5dccf9f4a77b39ca0346c4822 |
| source_lines | 106 |

## 2. 역할 요약

`dashboard_service.get_dashboard()`가 필터 없는 2개 위젯은 나이브 최신 base_date를, 선호지역 필터 3개 위젯은 독립적으로 폴백된 preference_base_date를 사용하는지, 매칭이 없으면 나이브 최신으로 폴백하는지, `cgg_cd`가 빈 값일 때 기본값으로 대체되는지를 검증하는 회귀 테스트다.

모듈 docstring(원문): "dashboard_service.get_dashboard()의 선호지역 위젯 3종 base_date 폴백 회귀 테스트.\n\n명세서 5항 5번: 필터 없는 2개 위젯(seoul_top5_districts/price_change_top5)은 항상 latest_base_date(파티션 존재 여부 폴백)를 쓰고, resolved_cgg_cd로 필터링하는 3개 위젯만 그 지역 조건 기준으로 독립적으로 소급된 preference_base_date를 쓴다 — 한 응답 안에서 위젯 그룹별로 base_date가 갈라질 수 있다."

## 3. 외부 인터페이스

| 이름 | 종류 | 시그니처 | 반환 타입 |
|---|---|---|---|
| test_get_dashboard_preference_widgets_fall_back_independently_of_naive_latest | function | `def test_get_dashboard_preference_widgets_fall_back_independently_of_naive_latest(monkeypatch)` | None |
| test_get_dashboard_preference_base_date_falls_back_to_naive_latest_when_no_match | function | `def test_get_dashboard_preference_base_date_falls_back_to_naive_latest_when_no_match(monkeypatch)` | None |
| test_get_dashboard_defaults_cgg_cd_when_blank | function | `def test_get_dashboard_defaults_cgg_cd_when_blank(monkeypatch)` | None |

## 4. 의존성(imports)

- 표준 라이브러리:
  - `from __future__ import annotations`
  - `from unittest.mock import MagicMock`
- 서드파티: 없음
- 내부 모듈:
  - `from app.services import dashboard_service`

## 5. 로직 상세

### test_get_dashboard_preference_widgets_fall_back_independently_of_naive_latest(monkeypatch)

- Given:
  1. `monkeypatch.setattr(dashboard_service.duckdb_client, "get_connection", lambda: MagicMock())`.
  2. `monkeypatch.setattr(dashboard_service.duckdb_client, "resolve_base_date", lambda *a, **k: "2026-08-30")`.
  3. `captured: dict = {}`.
  4. `fake_resolve_for_filter(con, mart_table, where_sql, params, **kwargs)`가 `captured["where_sql"]`, `captured["params"]`를 기록하고 `"2026-08-27"`(주석: `# 선호지역 조건은 과거로 소급됨`) 반환.
  5. `monkeypatch.setattr(dashboard_service.duckdb_client, "resolve_base_date_for_filter", fake_resolve_for_filter)`.
  6. `seen_base_dates: dict[str, str] = {}`.
  7. `record(name)`: 내부 함수 `_fn(con, base_date, *a, **k)`가 `seen_base_dates[name] = base_date`를 기록하고 `[]` 반환하는 클로저를 만들어 반환.
  8. `fake_price_change_top5(con, base_date)`: `seen_base_dates["price_change"] = base_date` 기록 후 `{"rising_top5": [], "falling_top5": []}` 반환.
  9. `monkeypatch.setattr(dashboard_service, "_build_seoul_top5_districts", record("seoul_top5"))`.
  10. `monkeypatch.setattr(dashboard_service, "_build_price_change_top5", fake_price_change_top5)`.
  11. `monkeypatch.setattr(dashboard_service, "_build_preference_price_trend", record("price_trend"))`.
  12. `monkeypatch.setattr(dashboard_service, "_build_top_trading_dongs", record("top_dongs"))`.
  13. `monkeypatch.setattr(dashboard_service, "_build_top_trading_apts", record("top_apts"))`.
- When: `result = dashboard_service.get_dashboard(cgg_cd="11680")`.
- Then(원문 assert, 주석 포함):
  - `assert result["preference_base_date"] == "2026-08-27"`
  - 주석: `# 필터 없는 2개 위젯은 나이브 최신 날짜(2026-08-30) 그대로 사용.`
  - `assert seen_base_dates["seoul_top5"] == "2026-08-30"`
  - `assert seen_base_dates["price_change"] == "2026-08-30"`
  - 주석: `# 선호지역 필터 3개 위젯은 소급된 날짜(2026-08-27)를 사용.`
  - `assert seen_base_dates["price_trend"] == "2026-08-27"`
  - `assert seen_base_dates["top_dongs"] == "2026-08-27"`
  - `assert seen_base_dates["top_apts"] == "2026-08-27"`
  - 주석: `# resolve_base_date_for_filter에는 resolved_cgg_cd 조건이 전달되어야 한다.`
  - `assert captured["params"] == {"cgg_cd": "11680"}`
  - `assert "cgg_cd = $cgg_cd" in captured["where_sql"]`

### test_get_dashboard_preference_base_date_falls_back_to_naive_latest_when_no_match(monkeypatch)

- Given:
  1. `monkeypatch.setattr(dashboard_service.duckdb_client, "get_connection", lambda: MagicMock())`.
  2. `monkeypatch.setattr(dashboard_service.duckdb_client, "resolve_base_date", lambda *a, **k: "2026-08-30")`.
  3. `monkeypatch.setattr(dashboard_service.duckdb_client, "resolve_base_date_for_filter", lambda *a, **k: None)`.
  4. `monkeypatch.setattr(dashboard_service, "_build_seoul_top5_districts", lambda *a, **k: [])`.
  5. `monkeypatch.setattr(dashboard_service, "_build_price_change_top5", lambda *a, **k: {"rising_top5": [], "falling_top5": []})`.
  6. `monkeypatch.setattr(dashboard_service, "_build_preference_price_trend", lambda *a, **k: [])`.
  7. `monkeypatch.setattr(dashboard_service, "_build_top_trading_dongs", lambda *a, **k: [])`.
  8. `monkeypatch.setattr(dashboard_service, "_build_top_trading_apts", lambda *a, **k: [])`.
- When: `result = dashboard_service.get_dashboard(cgg_cd="00000")`.
- Then(원문 assert): `assert result["preference_base_date"] == "2026-08-30"`.

### test_get_dashboard_defaults_cgg_cd_when_blank(monkeypatch)

- Given:
  1. `monkeypatch.setattr(dashboard_service.duckdb_client, "get_connection", lambda: MagicMock())`.
  2. `monkeypatch.setattr(dashboard_service.duckdb_client, "resolve_base_date", lambda *a, **k: "2026-08-30")`.
  3. `monkeypatch.setattr(dashboard_service.duckdb_client, "resolve_base_date_for_filter", lambda *a, **k: "2026-08-30")`.
  4. `monkeypatch.setattr(dashboard_service, "_build_seoul_top5_districts", lambda *a, **k: [])`.
  5. `monkeypatch.setattr(dashboard_service, "_build_price_change_top5", lambda *a, **k: {"rising_top5": [], "falling_top5": []})`.
  6. `monkeypatch.setattr(dashboard_service, "_build_preference_price_trend", lambda *a, **k: [])`.
  7. `monkeypatch.setattr(dashboard_service, "_build_top_trading_dongs", lambda *a, **k: [])`.
  8. `monkeypatch.setattr(dashboard_service, "_build_top_trading_apts", lambda *a, **k: [])`.
- When: `result = dashboard_service.get_dashboard(cgg_cd=None)`.
- Then(원문 assert): `assert result["cgg_cd"] == dashboard_service.DEFAULT_CGG_CD`.

## 6. 모듈 레벨 상수/설정값

없음.

## 7. 역참조(이 파일을 사용하는 곳)

- 없음(pytest가 자동 수집하는 테스트 모듈이며, 다른 소스 모듈이 import하지 않음).

## 8. 재생성 지침

> 위 내용을 근거로 `backend_fastApi/tests/services/test_dashboard_service.py` 파일을 동일한 로직으로 재작성하라. 여기 명시되지 않은 세부 구현(변수명 스타일, 코드 포맷 등)은 기존 프로젝트 컨벤션(PEP 8, 저장소 내 동일 계층 파일들의 스타일)을 따른다.
