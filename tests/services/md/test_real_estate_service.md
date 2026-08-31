# test_real_estate_service.py 명세

## 1. 메타 정보

| 항목 | 값 |
|---|---|
| source_path | backend_fastApi/tests/services/test_real_estate_service.py |
| source_sha256 | d215c016552944c8a7d51fcac6e06df64e88c9eabb715d3ad1f05b576964b5dd |
| source_lines | 76 |

## 2. 역할 요약

`real_estate_service.get_latest_listings()`가 RAW 파티션의 아파트 전용 필터(`BLDG_USG = '아파트'`) 폴백 결과를 실제로 사용하는지, 매칭이 없을 때 나이브 최신 파티션으로 폴백하는지, 폴백 함수에 실제로 아파트 필터 조건이 전달되는지를 검증하는 회귀 테스트다.

모듈 docstring(원문): "real_estate_service.get_latest_listings()의 RAW 파티션 base_date 폴백 회귀 테스트."

## 3. 외부 인터페이스

| 이름 | 종류 | 시그니처 | 반환 타입 |
|---|---|---|---|
| _fake_con_returning_empty | function | `def _fake_con_returning_empty()` | MagicMock |
| test_get_latest_listings_uses_fallback_partition_when_naive_latest_has_no_apt_rows | function | `def test_get_latest_listings_uses_fallback_partition_when_naive_latest_has_no_apt_rows(monkeypatch)` | None |
| test_get_latest_listings_falls_back_to_naive_when_no_apt_partition_matches | function | `def test_get_latest_listings_falls_back_to_naive_when_no_apt_partition_matches(monkeypatch)` | None |
| test_get_latest_listings_passes_apt_only_filter_to_fallback | function | `def test_get_latest_listings_passes_apt_only_filter_to_fallback(monkeypatch)` | None |

## 4. 의존성(imports)

- 표준 라이브러리:
  - `from __future__ import annotations`
  - `from unittest.mock import MagicMock`
- 서드파티: 없음
- 내부 모듈:
  - `from app.services import real_estate_service`

## 5. 로직 상세

### _fake_con_returning_empty

- 목적: 빈 결과를 반환하는 가짜 커넥션 생성.
- 처리 흐름:
  1. `con = MagicMock()`.
  2. `con.execute.return_value.description = [("apt_name",)]`.
  3. `con.execute.return_value.fetchall.return_value = []`.
  4. `return con`.

### test_get_latest_listings_uses_fallback_partition_when_naive_latest_has_no_apt_rows(monkeypatch)

- 함수 docstring(원문): "오늘(나이브 최신) 파티션 폴더는 있지만 그 날 BLDG_USG='아파트' row가 0건이면, 아파트 거래가 있는 과거 day 파티션으로 소급되어야 한다."
- Given:
  1. `monkeypatch.setattr(real_estate_service.duckdb_client, "get_connection", lambda: _fake_con_returning_empty())`.
  2. `monkeypatch.setattr(real_estate_service.duckdb_client, "resolve_latest_date_partition_for_filter", lambda *a, **k: ("2026", "08", "27"))`.
  3. `monkeypatch.setattr(real_estate_service.duckdb_client, "resolve_latest_date_partition", lambda *a, **k: ("2026", "08", "30"))`.
  4. `monkeypatch.setattr(real_estate_service.duckdb_client, "rows_to_dicts", lambda result: [])`.
- When: `base_date, items = real_estate_service.get_latest_listings()`.
- Then(원문 assert):
  - `assert base_date == "2026-08-27"`
  - `assert items == []`

### test_get_latest_listings_falls_back_to_naive_when_no_apt_partition_matches(monkeypatch)

- Given:
  1. `monkeypatch.setattr(real_estate_service.duckdb_client, "get_connection", lambda: _fake_con_returning_empty())`.
  2. `monkeypatch.setattr(real_estate_service.duckdb_client, "resolve_latest_date_partition_for_filter", lambda *a, **k: None)`.
  3. `monkeypatch.setattr(real_estate_service.duckdb_client, "resolve_latest_date_partition", lambda *a, **k: ("2026", "08", "30"))`.
  4. `monkeypatch.setattr(real_estate_service.duckdb_client, "rows_to_dicts", lambda result: [])`.
- When: `base_date, items = real_estate_service.get_latest_listings()`.
- Then(원문 assert): `assert base_date == "2026-08-30"`.

### test_get_latest_listings_passes_apt_only_filter_to_fallback(monkeypatch)

- 함수 docstring(원문): "resolve_latest_date_partition_for_filter에 BLDG_USG='아파트' 조건이 실제로 전달되는지 확인한다."
- Given:
  1. `captured: dict = {}`.
  2. `fake_fallback(con, dataset, where_sql, params, **kwargs)`가 `captured["dataset"] = dataset`, `captured["where_sql"] = where_sql`, `captured["params"] = params`를 기록하고 `("2026", "08", "30")` 반환.
  3. `monkeypatch.setattr(real_estate_service.duckdb_client, "get_connection", lambda: _fake_con_returning_empty())`.
  4. `monkeypatch.setattr(real_estate_service.duckdb_client, "resolve_latest_date_partition_for_filter", fake_fallback)`.
  5. `monkeypatch.setattr(real_estate_service.duckdb_client, "rows_to_dicts", lambda result: [])`.
- When: `real_estate_service.get_latest_listings()`.
- Then(원문 assert):
  - `assert captured["dataset"] == real_estate_service.DATASET`
  - `assert captured["params"] == {"bldg_usg": "아파트"}`
  - `assert "BLDG_USG = $bldg_usg" in captured["where_sql"]`

## 6. 모듈 레벨 상수/설정값

없음.

## 7. 역참조(이 파일을 사용하는 곳)

- 없음(pytest가 자동 수집하는 테스트 모듈이며, 다른 소스 모듈이 import하지 않음).

## 8. 재생성 지침

> 위 내용을 근거로 `backend_fastApi/tests/services/test_real_estate_service.py` 파일을 동일한 로직으로 재작성하라. 여기 명시되지 않은 세부 구현(변수명 스타일, 코드 포맷 등)은 기존 프로젝트 컨벤션(PEP 8, 저장소 내 동일 계층 파일들의 스타일)을 따른다.
