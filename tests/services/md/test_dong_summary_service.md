# test_dong_summary_service.py 명세

## 1. 메타 정보

| 항목 | 값 |
|---|---|
| source_path | backend_fastApi/tests/services/test_dong_summary_service.py |
| source_sha256 | 0493e5508803825b7d9d83ac38d6dffd38e05528df60698df6f5de13f34a70c4 |
| source_lines | 63 |

## 2. 역할 요약

`dong_summary_service.get_dong_summary()`가 `duckdb_client.resolve_base_date_for_filter`의 폴백 결과를 실제로 사용하는지, region_cgg가 없을 때 빈 `where_sql`을 정상 전달하는지, 매칭이 없을 때 나이브 최신 base_date로 폴백하는지를 검증하는 회귀 테스트다.

모듈 docstring(원문): "dong_summary_service.get_dong_summary()의 base_date 폴백 반영 회귀 테스트."

## 3. 외부 인터페이스

| 이름 | 종류 | 시그니처 | 반환 타입 |
|---|---|---|---|
| _patch_common | function | `def _patch_common(monkeypatch, *, filter_result, naive_latest)` | None |
| test_get_dong_summary_uses_fallback_base_date | function | `def test_get_dong_summary_uses_fallback_base_date(monkeypatch)` | None |
| test_get_dong_summary_supports_no_region_filter | function | `def test_get_dong_summary_supports_no_region_filter(monkeypatch)` | None |
| test_get_dong_summary_falls_back_to_naive_latest_when_no_match | function | `def test_get_dong_summary_falls_back_to_naive_latest_when_no_match(monkeypatch)` | None |

## 4. 의존성(imports)

- 표준 라이브러리:
  - `from __future__ import annotations`
  - `from unittest.mock import MagicMock`
- 서드파티: 없음
- 내부 모듈:
  - `from app.services import dong_summary_service`

## 5. 로직 상세

### _patch_common

- 목적: 공통 monkeypatch 설정(연결/폴백 함수/naive 최신/내부 `_fetch_rows`)을 모아둔 헬퍼.
- 파라미터: `monkeypatch`, `filter_result`(키워드 전용), `naive_latest`(키워드 전용).
- 처리 흐름:
  1. `monkeypatch.setattr(dong_summary_service.duckdb_client, "get_connection", lambda: MagicMock())`.
  2. `monkeypatch.setattr(dong_summary_service.duckdb_client, "resolve_base_date_for_filter", lambda *a, **k: filter_result)`.
  3. `monkeypatch.setattr(dong_summary_service.duckdb_client, "resolve_base_date", lambda *a, **k: naive_latest)`.
  4. `monkeypatch.setattr(dong_summary_service, "_fetch_rows", lambda *a, **k: [])`.

### test_get_dong_summary_uses_fallback_base_date(monkeypatch)

- Given: `_patch_common(monkeypatch, filter_result="2026-08-27", naive_latest="2026-08-30")`.
- When: `base_date, groups = dong_summary_service.get_dong_summary(region_cgg="11680")`.
- Then(원문 assert):
  - `assert base_date == "2026-08-27"`
  - `assert groups == {}`

### test_get_dong_summary_supports_no_region_filter(monkeypatch)

- 함수 docstring(원문): "region_cgg가 없으면 where_sql이 빈 문자열이 되는데, 이 경우에도 resolve_base_date_for_filter가 정상적으로 호출/사용되어야 한다."
- Given:
  1. `captured: dict = {}`.
  2. `fake_resolve_for_filter(con, mart_table, where_sql, params, **kwargs)`가 `captured["where_sql"] = where_sql`, `captured["params"] = params`를 기록하고 `"2026-08-29"`를 반환.
  3. `monkeypatch.setattr(dong_summary_service.duckdb_client, "get_connection", lambda: MagicMock())`.
  4. `monkeypatch.setattr(dong_summary_service.duckdb_client, "resolve_base_date_for_filter", fake_resolve_for_filter)`.
  5. `monkeypatch.setattr(dong_summary_service.duckdb_client, "resolve_base_date", lambda *a, **k: "2026-08-30")`.
  6. `monkeypatch.setattr(dong_summary_service, "_fetch_rows", lambda *a, **k: [])`.
- When: `base_date, _ = dong_summary_service.get_dong_summary(region_cgg=None)`.
- Then(원문 assert):
  - `assert base_date == "2026-08-29"`
  - `assert captured["where_sql"] == ""`
  - `assert captured["params"] == {}`

### test_get_dong_summary_falls_back_to_naive_latest_when_no_match(monkeypatch)

- Given: `_patch_common(monkeypatch, filter_result=None, naive_latest="2026-08-30")`.
- When: `base_date, _ = dong_summary_service.get_dong_summary(region_cgg="00000")`.
- Then(원문 assert): `assert base_date == "2026-08-30"`.

## 6. 모듈 레벨 상수/설정값

없음.

## 7. 역참조(이 파일을 사용하는 곳)

- 없음(pytest가 자동 수집하는 테스트 모듈이며, 다른 소스 모듈이 import하지 않음).

## 8. 재생성 지침

> 위 내용을 근거로 `backend_fastApi/tests/services/test_dong_summary_service.py` 파일을 동일한 로직으로 재작성하라. 여기 명시되지 않은 세부 구현(변수명 스타일, 코드 포맷 등)은 기존 프로젝트 컨벤션(PEP 8, 저장소 내 동일 계층 파일들의 스타일)을 따른다.
