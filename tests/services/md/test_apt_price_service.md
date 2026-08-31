# test_apt_price_service.py 명세

## 1. 메타 정보

| 항목 | 값 |
|---|---|
| source_path | backend_fastApi/tests/services/test_apt_price_service.py |
| source_sha256 | 670b15e523c0a76b3467f56c802c5a868c4fc5387c5f425dfcb6d83e1ece75ef |
| source_lines | 86 |

## 2. 역할 요약

`apt_price_service.get_top_bottom()`이 지역 조건 폴백 base_date를 실제로 사용하는지, 매칭이 없을 때 나이브 최신으로 폴백하는지, `resolve_base_date_for_filter`에 `_build_where_clause`로 만든 조건이 그대로 전달되는지를 검증하는 회귀 테스트다.

모듈 docstring(원문): "apt_price_service.get_top_bottom()의 base_date 폴백 반영 회귀 테스트.\n\nduckdb_client.resolve_base_date_for_filter()/resolve_base_date() 자체는 tests/core/test_duckdb_client.py에서 이미 검증했으므로, 여기서는 서비스가 \"naive 최신 base_date\"가 아니라 \"폴백 탐색 결과\"를 실제로 사용하는지만 격리해서 확인한다. DB 접속(get_connection)과 내부 조회 헬퍼는 모두 monkeypatch로 대체해 MinIO 없이 실행한다."

## 3. 외부 인터페이스

| 이름 | 종류 | 시그니처 | 반환 타입 |
|---|---|---|---|
| _patch_common | function | `def _patch_common(monkeypatch, *, filter_result: str \| None, naive_latest: str)` | None |
| test_get_top_bottom_uses_fallback_base_date_when_filter_matches_past_partition | function | `def test_get_top_bottom_uses_fallback_base_date_when_filter_matches_past_partition(monkeypatch)` | None |
| test_get_top_bottom_falls_back_to_naive_latest_when_no_partition_matches | function | `def test_get_top_bottom_falls_back_to_naive_latest_when_no_partition_matches(monkeypatch)` | None |
| test_get_top_bottom_passes_where_clause_built_from_region_filters | function | `def test_get_top_bottom_passes_where_clause_built_from_region_filters(monkeypatch)` | None |

## 4. 의존성(imports)

- 표준 라이브러리:
  - `from __future__ import annotations`
  - `from unittest.mock import MagicMock`
- 서드파티: 없음
- 내부 모듈:
  - `from app.services import apt_price_service`

## 5. 로직 상세

### _patch_common

- 목적: 공통 monkeypatch 설정(연결/폴백 함수/naive 최신/`_count_rows`/`_fetch_ranked`/`_fetch_summary`)을 모아둔 헬퍼.
- 파라미터: `monkeypatch`, `filter_result: str | None`(키워드 전용), `naive_latest: str`(키워드 전용).
- 처리 흐름:
  1. `monkeypatch.setattr(apt_price_service.duckdb_client, "get_connection", lambda: MagicMock())`.
  2. `monkeypatch.setattr(apt_price_service.duckdb_client, "resolve_base_date_for_filter", lambda *args, **kwargs: filter_result)`.
  3. `monkeypatch.setattr(apt_price_service.duckdb_client, "resolve_base_date", lambda *args, **kwargs: naive_latest)`.
  4. `monkeypatch.setattr(apt_price_service, "_count_rows", lambda *args, **kwargs: 2)`.
  5. `monkeypatch.setattr(apt_price_service, "_fetch_ranked", lambda *args, **kwargs: [])`.
  6. `monkeypatch.setattr(apt_price_service, "_fetch_summary", lambda *args, **kwargs: (2, 1000, 100))`.

### test_get_top_bottom_uses_fallback_base_date_when_filter_matches_past_partition(monkeypatch)

- 함수 docstring(원문): "최신 파티션(naive)엔 지역 조건 매칭 데이터가 없고 과거 파티션에만 있는 경우, 응답 base_date는 소급된 날짜여야 한다(최신 날짜가 그대로 노출되면 회귀)."
- Given: `_patch_common(monkeypatch, filter_result="2026-08-27", naive_latest="2026-08-30")`.
- When: `base_date, *_ = apt_price_service.get_top_bottom(region_cgg_cd="11680", region_stdg_cd=None, metric_type="pyeong")`.
- Then(원문 assert): `assert base_date == "2026-08-27"`.

### test_get_top_bottom_falls_back_to_naive_latest_when_no_partition_matches(monkeypatch)

- 함수 docstring(원문): "조건에 매칭되는 파티션이 하나도 없으면(resolve_base_date_for_filter → None), 기존과 동일하게 resolve_base_date()의 최신 파티션을 사용해야 한다."
- Given: `_patch_common(monkeypatch, filter_result=None, naive_latest="2026-08-30")`.
- When: `base_date, *_ = apt_price_service.get_top_bottom(region_cgg_cd="00000", region_stdg_cd=None, metric_type="pyeong")`.
- Then(원문 assert): `assert base_date == "2026-08-30"`.

### test_get_top_bottom_passes_where_clause_built_from_region_filters(monkeypatch)

- 함수 docstring(원문): "resolve_base_date_for_filter가 apt_price_service._build_where_clause로 만든 조건을 그대로 전달받는지 확인한다(엉뚱한 조건으로 존재 확인을 하면 폴백이 무의미해진다)."
- Given:
  1. `captured: dict = {}`.
  2. `fake_resolve_for_filter(con, mart_table, where_sql, params, **kwargs)`가 `captured["mart_table"]`, `captured["where_sql"]`, `captured["params"]`를 기록하고 `"2026-08-30"` 반환.
  3. `monkeypatch.setattr(apt_price_service.duckdb_client, "get_connection", lambda: MagicMock())`.
  4. `monkeypatch.setattr(apt_price_service.duckdb_client, "resolve_base_date_for_filter", fake_resolve_for_filter)`.
  5. `monkeypatch.setattr(apt_price_service.duckdb_client, "resolve_base_date", lambda *a, **k: "2026-08-30")`.
  6. `monkeypatch.setattr(apt_price_service, "_count_rows", lambda *a, **k: 0)`.
  7. `monkeypatch.setattr(apt_price_service, "_fetch_ranked", lambda *a, **k: [])`.
  8. `monkeypatch.setattr(apt_price_service, "_fetch_summary", lambda *a, **k: (0, 0, 0))`.
- When: `apt_price_service.get_top_bottom(region_cgg_cd="11680", region_stdg_cd="10300", metric_type="pyeong")`.
- Then(원문 assert):
  - `assert captured["mart_table"] == apt_price_service.MART_TABLE`
  - `assert captured["params"] == {"cgg_cd": "11680", "stdg_cd": "10300"}`
  - `assert "cgg_cd = $cgg_cd" in captured["where_sql"]`
  - `assert "stdg_cd = $stdg_cd" in captured["where_sql"]`

## 6. 모듈 레벨 상수/설정값

없음.

## 7. 역참조(이 파일을 사용하는 곳)

- 없음(pytest가 자동 수집하는 테스트 모듈이며, 다른 소스 모듈이 import하지 않음).

## 8. 재생성 지침

> 위 내용을 근거로 `backend_fastApi/tests/services/test_apt_price_service.py` 파일을 동일한 로직으로 재작성하라. 여기 명시되지 않은 세부 구현(변수명 스타일, 코드 포맷 등)은 기존 프로젝트 컨벤션(PEP 8, 저장소 내 동일 계층 파일들의 스타일)을 따른다.
