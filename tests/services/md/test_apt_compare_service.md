# test_apt_compare_service.py 명세

## 1. 메타 정보

| 항목 | 값 |
|---|---|
| source_path | backend_fastApi/tests/services/test_apt_compare_service.py |
| source_sha256 | 2910879d73e263784116e2e5c2967411ab6217303ad3137b473be974bfb7526c |
| source_lines | 105 |

## 2. 역할 요약

`apt_compare_service.compare_apartments()`의 base_date 폴백 반영과 `grp="40"` → `"40+"` 변환 관례, `fetch_recent_supply_pyeong()`의 폴백 base_date 사용을 검증하는 회귀 테스트다.

모듈 docstring(원문): "apt_compare_service의 base_date 폴백 반영 + 기존 grp 값 변환(\"40\" -> \"40+\") 회귀 테스트."

## 3. 외부 인터페이스

| 이름 | 종류 | 시그니처 | 반환 타입 |
|---|---|---|---|
| test_compare_apartments_uses_fallback_base_date | function | `def test_compare_apartments_uses_fallback_base_date(monkeypatch)` | None |
| test_compare_apartments_still_converts_pyeong_grp_40_to_40_plus | function | `def test_compare_apartments_still_converts_pyeong_grp_40_to_40_plus(monkeypatch)` | None |
| test_fetch_recent_supply_pyeong_uses_fallback_base_date | function | `def test_fetch_recent_supply_pyeong_uses_fallback_base_date(monkeypatch)` | None |

## 4. 의존성(imports)

- 표준 라이브러리:
  - `from __future__ import annotations`
  - `from unittest.mock import MagicMock`
- 서드파티: 없음
- 내부 모듈:
  - `from app.services import apt_compare_service as svc`

## 5. 로직 상세

### test_compare_apartments_uses_fallback_base_date(monkeypatch)

- Given:
  1. `monkeypatch.setattr(svc.duckdb_client, "get_connection", lambda: MagicMock())`.
  2. `monkeypatch.setattr(svc.duckdb_client, "resolve_base_date_for_filter", lambda *a, **k: "2026-08-27")`.
  3. `monkeypatch.setattr(svc.duckdb_client, "resolve_base_date", lambda *a, **k: "2026-08-30")`.
  4. 지역 클래스 `_FakeCursor`: `description = [("cgg_cd",)]`; `fetchall(self)` → `[]`.
  5. `monkeypatch.setattr(svc.duckdb_client, "rows_to_dicts", lambda result: [])`.
  6. 지역 클래스 `_FakeCon`: `execute(self, query, params=None)` → `_FakeCursor()`; `close(self)` → `pass`.
  7. `monkeypatch.setattr(svc.duckdb_client, "get_connection", lambda: _FakeCon())`(1번의 설정을 덮어씀).
- When: `base_date, items = svc.compare_apartments(cgg_cd="11500", stdg_cd="10300", bldg_nm=None, mno="1", sno="0", query_type="pyeong", grp="30")`.
- Then(원문 assert):
  - `assert base_date == "2026-08-27"`
  - `assert items == []`

### test_compare_apartments_still_converts_pyeong_grp_40_to_40_plus(monkeypatch)

- 함수 docstring(원문): "리팩터링 후에도 기존 관례(\"40\" -> \"40+\")가 where 절 파라미터에 그대로 반영되어야 한다."
- Given:
  1. `captured: dict = {}`.
  2. `fake_resolve_for_filter(con, mart_table, where_sql, params, **kwargs)`가 `captured["params"] = params`를 기록하고 `"2026-08-30"` 반환.
  3. `monkeypatch.setattr(svc.duckdb_client, "resolve_base_date_for_filter", fake_resolve_for_filter)`.
  4. `monkeypatch.setattr(svc.duckdb_client, "resolve_base_date", lambda *a, **k: "2026-08-30")`.
  5. `monkeypatch.setattr(svc.duckdb_client, "rows_to_dicts", lambda result: [])`.
  6. 지역 클래스 `_FakeCon`: `execute(self, query, params=None)` → `object()`; `close(self)` → `pass`.
  7. `monkeypatch.setattr(svc.duckdb_client, "get_connection", lambda: _FakeCon())`.
- When: `svc.compare_apartments(cgg_cd="11500", stdg_cd="10300", bldg_nm=None, mno="1", sno="0", query_type="pyeong", grp="40")`.
- Then(원문 assert): `assert captured["params"]["grp"] == "40+"`.

### test_fetch_recent_supply_pyeong_uses_fallback_base_date(monkeypatch)

- Given:
  1. `captured: dict = {}`.
  2. `fake_resolve_for_filter(con, mart_table, where_sql, params, **kwargs)`가 `captured["mart_table"] = mart_table`를 기록하고 `"2026-08-27"` 반환.
  3. `monkeypatch.setattr(svc.duckdb_client, "resolve_base_date_for_filter", fake_resolve_for_filter)`.
  4. `monkeypatch.setattr(svc.duckdb_client, "resolve_base_date", lambda *a, **k: "2026-08-30")`.
  5. 지역 클래스 `_FakeCon`: `execute(self, query, params=None)` → 지역 클래스 `_R`(`fetchone(self)` → `(12.3,)`)의 인스턴스; `close(self)` → `pass`.
  6. `monkeypatch.setattr(svc.duckdb_client, "get_connection", lambda: _FakeCon())`.
- When: `result = svc.fetch_recent_supply_pyeong(cgg_cd="11500", stdg_cd="10300", bldg_nm=None, mno="1", sno="0")`.
- Then(원문 assert):
  - `assert result == 12.3`
  - `assert captured["mart_table"] == svc.MART_TABLE_BY_QUERY_TYPE["pyeong"]`

## 6. 모듈 레벨 상수/설정값

없음.

## 7. 역참조(이 파일을 사용하는 곳)

- 없음(pytest가 자동 수집하는 테스트 모듈이며, 다른 소스 모듈이 import하지 않음).

## 8. 재생성 지침

> 위 내용을 근거로 `backend_fastApi/tests/services/test_apt_compare_service.py` 파일을 동일한 로직으로 재작성하라. 여기 명시되지 않은 세부 구현(변수명 스타일, 코드 포맷 등)은 기존 프로젝트 컨벤션(PEP 8, 저장소 내 동일 계층 파일들의 스타일)을 따른다.
