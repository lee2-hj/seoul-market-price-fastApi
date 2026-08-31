# test_apt_trend_service.py 명세

## 1. 메타 정보

| 항목 | 값 |
|---|---|
| source_path | backend_fastApi/tests/services/test_apt_trend_service.py |
| source_sha256 | eb591162a78b6fdcb45bd1fa404398d425f29a69f92c05f31a331e6f0d2122d4 |
| source_lines | 167 |

## 2. 역할 요약

`apt_trend_service.get_apt_trend_summary()`의 range-앵커형 base_date 폴백(90일 창 이동)과, `_build_count_change_rate()`의 `MIN_TRADE_COUNT` 표본 필터링 제거 이후 동작(저거래량도 값 산출, `prev_count == 0` 스텝만 제외, 완전 무거래 시 `None`, 0으로 나누기 미발생, `MIN_TRADE_COUNT` 상수 완전 제거 확인)을 검증하는 회귀 테스트다.

모듈 docstring(원문): "apt_trend_service 회귀 테스트.\n\n1. get_apt_trend_summary()의 range-앵커형 base_date 폴백(90일 창 이동).\n2. _build_count_change_rate()의 표본 부족 필터링(MIN_TRADE_COUNT) 제거 이후 동작(backend-apt-trend-count-change-rate-fix 계획서 Phase 4 테스트 케이스)."

## 3. 외부 인터페이스

| 이름 | 종류 | 시그니처 | 반환 타입 |
|---|---|---|---|
| test_get_apt_trend_summary_shifts_window_when_naive_period_has_no_matching_trades | function | `def test_get_apt_trend_summary_shifts_window_when_naive_period_has_no_matching_trades(monkeypatch, caplog)` | None |
| test_get_apt_trend_summary_keeps_empty_result_when_no_match_at_all | function | `def test_get_apt_trend_summary_keeps_empty_result_when_no_match_at_all(monkeypatch)` | None |
| test_get_apt_trend_summary_passes_entity_filter_without_date_condition_to_fallback | function | `def test_get_apt_trend_summary_passes_entity_filter_without_date_condition_to_fallback(monkeypatch)` | None |
| test_get_apt_trend_summary_does_not_call_fallback_when_naive_window_has_rows | function | `def test_get_apt_trend_summary_does_not_call_fallback_when_naive_window_has_rows(monkeypatch)` | None |
| _trend | function | `def _trend(deal_counts: list[int]) -> list[dict]` | list[dict] |
| test_count_change_rate_low_volume_still_produces_a_value | function | `def test_count_change_rate_low_volume_still_produces_a_value()` | None |
| test_count_change_rate_only_excludes_step_with_zero_prev_count | function | `def test_count_change_rate_only_excludes_step_with_zero_prev_count()` | None |
| test_count_change_rate_all_zero_except_last_returns_none | function | `def test_count_change_rate_all_zero_except_last_returns_none()` | None |
| test_count_change_rate_never_raises_zero_division_error | function | `def test_count_change_rate_never_raises_zero_division_error()` | None |
| test_count_change_rate_no_min_trade_count_constant | function | `def test_count_change_rate_no_min_trade_count_constant()` | None |

## 4. 의존성(imports)

- 표준 라이브러리:
  - `from __future__ import annotations`
  - `import logging`
  - `from datetime import date, timedelta`
  - `from unittest.mock import MagicMock`
- 서드파티: 없음
- 내부 모듈:
  - `from app.services import apt_trend_service`

주석 구분선(17~19행): `# ---------------------------------------------------------------------------` / `# get_apt_trend_summary: range-앵커 폴백` / `# ---------------------------------------------------------------------------`

주석 구분선(121~124행): `# ---------------------------------------------------------------------------` / `# _build_count_change_rate: MIN_TRADE_COUNT 필터링 제거 회귀 테스트` / `# (docs/plans/backend-apt-trend-count-change-rate-fix-plan.md Phase 4)` / `# ---------------------------------------------------------------------------`

## 5. 로직 상세

### test_get_apt_trend_summary_shifts_window_when_naive_period_has_no_matching_trades(monkeypatch, caplog)

- Given:
  1. `monkeypatch.setattr(apt_trend_service.duckdb_client, "get_connection", lambda: MagicMock())`.
  2. `call_count = {"n": 0}`.
  3. `naive_start, _ = apt_trend_service._period_range(date.today())`.
  4. `matched = naive_start - timedelta(days=15)`(주석: `# naive 창보다 과거이면서도 max_base_date_lookback(30일) 상한 이내인 날짜.`).
  5. `fake_fetch_rows(con, cgg_cd, stdg_cd, mno, sno, apt_name, start_date, end_date)`: `call_count["n"] += 1`; `if call_count["n"] == 1: return []`; 아니면 `assert end_date == matched`; `assert start_date == matched - timedelta(days=apt_trend_service.PERIOD_DAYS)`; `return [{"cgg_cd": cgg_cd, "cgg_nm": "강서구", "stdg_cd": stdg_cd, "stdg_nm": "화곡동", "apt_name": "테스트아파트", "mno": mno, "sno": sno, "deal_date": matched.isoformat(), "floor": 5, "trade_amount": 50000, "pyeong": 25.0, "trade_count": 1}]`.
  6. `monkeypatch.setattr(apt_trend_service, "_fetch_rows", fake_fetch_rows)`.
  7. `monkeypatch.setattr(apt_trend_service.duckdb_client, "resolve_recent_match_date", lambda *a, **k: matched)`.
- When: `with caplog.at_level(logging.INFO, logger="app.services.apt_trend_service"): result = apt_trend_service.get_apt_trend_summary(cgg_cd="11500", stdg_cd="10300", mno="661", sno="0", apt_name=None)`.
- Then(원문 assert):
  - `assert result["search_period"]["end_date"] == matched`
  - `assert result["count"] == 1`
  - `assert any("Anchor fallback used" in r.message for r in caplog.records)`

### test_get_apt_trend_summary_keeps_empty_result_when_no_match_at_all(monkeypatch)

- Given:
  1. `monkeypatch.setattr(apt_trend_service.duckdb_client, "get_connection", lambda: MagicMock())`.
  2. `monkeypatch.setattr(apt_trend_service, "_fetch_rows", lambda *a, **k: [])`.
  3. `monkeypatch.setattr(apt_trend_service.duckdb_client, "resolve_recent_match_date", lambda *a, **k: None)`.
- When: `result = apt_trend_service.get_apt_trend_summary(cgg_cd="00000", stdg_cd="00000", mno="0", sno="0", apt_name=None)`.
- Then(원문 assert):
  - `assert result["count"] == 0`
  - `assert result["data"] == []`

### test_get_apt_trend_summary_passes_entity_filter_without_date_condition_to_fallback(monkeypatch)

- 함수 docstring(원문): "resolve_recent_match_date에는 날짜 조건 없이 단지 필터(cgg_cd/stdg_cd/mno/sno/apt_name)만 전달되어야 한다(전체 이력에서 조회해야 하므로)."
- Given:
  1. `captured: dict = {}`.
  2. `fake_resolve_recent_match_date(con, glob_pattern, date_column, where_sql, params)`가 `captured["date_column"]`, `captured["where_sql"]`, `captured["params"]`를 기록하고 `None` 반환.
  3. `monkeypatch.setattr(apt_trend_service.duckdb_client, "get_connection", lambda: MagicMock())`.
  4. `monkeypatch.setattr(apt_trend_service, "_fetch_rows", lambda *a, **k: [])`.
  5. `monkeypatch.setattr(apt_trend_service.duckdb_client, "resolve_recent_match_date", fake_resolve_recent_match_date)`.
- When: `apt_trend_service.get_apt_trend_summary(cgg_cd="11500", stdg_cd="10300", mno="661", sno="0", apt_name="래미안")`.
- Then(원문 assert):
  - `assert captured["date_column"] == "deal_date"`
  - `assert "start_date" not in captured["params"]`
  - `assert "end_date" not in captured["params"]`
  - `assert captured["params"]["apt_name"] == "%래미안%"`
  - `assert "apt_name ILIKE $apt_name" in captured["where_sql"]`

### test_get_apt_trend_summary_does_not_call_fallback_when_naive_window_has_rows(monkeypatch)

- Given:
  1. `monkeypatch.setattr(apt_trend_service.duckdb_client, "get_connection", lambda: MagicMock())`.
  2. `monkeypatch.setattr(apt_trend_service, "_fetch_rows", lambda *a, **k: [{"cgg_cd": "11500", "cgg_nm": "강서구", "stdg_cd": "10300", "stdg_nm": "화곡동", "apt_name": "테스트", "mno": "1", "sno": "0", "deal_date": "2026-08-30", "floor": 3, "trade_amount": 40000, "pyeong": 20.0, "trade_count": 1}])`.
  3. `called = {"n": 0}`.
  4. `fail_if_called(*a, **k)`: `called["n"] += 1`(반환값 없음).
  5. `monkeypatch.setattr(apt_trend_service.duckdb_client, "resolve_recent_match_date", fail_if_called)`.
- When: `apt_trend_service.get_apt_trend_summary(cgg_cd="11500", stdg_cd="10300", mno="1", sno="0", apt_name=None)`.
- Then(원문 assert): `assert called["n"] == 0`.

### _trend

- 목적: 테스트용 `biweekly_trend` 리스트를 `deal_count` 정수 목록으로부터 생성하는 헬퍼.
- 파라미터: `deal_counts: list[int]`.
- 처리 흐름: `return [{"deal_count": c} for c in deal_counts]`.
- 반환값: `[{"deal_count": c}, ...]`.

### test_count_change_rate_low_volume_still_produces_a_value()

- 함수 docstring(원문): "i. 저거래량 케이스: 전 구간이 3건 미만이어도 0이 아닌 이상 증감률을 계산해야 한다(기존 MIN_TRADE_COUNT=3 필터링 시 전부 제외되어 None이 나오던 회귀 케이스)."
- Given/When: `result = apt_trend_service._build_count_change_rate(_trend([1, 2, 1, 0, 2, 3]))`.
- Then(원문 assert): `assert result is not None`.

### test_count_change_rate_only_excludes_step_with_zero_prev_count()

- 함수 docstring(원문): "ii. prev_count == 0 가드: 첫 스텝(0 -> 5)만 제외되고 나머지 스텝은 정상 계산되어야 한다."
- Given: `trend = _trend([0, 5, 3, 4, 2, 6])`.
- When: `result = apt_trend_service._build_count_change_rate(trend)`.
- Then(원문 assert 및 수동 계산 검증, 주석 "수동 계산: 스텝1(0->5)은 제외. 스텝2~5만 가중평균(가중치 2,3,4,5)." 포함):
  - `assert result is not None`
  - `steps = [(5, 3, 2), (3, 4, 3), (4, 2, 4), (2, 6, 5)]`
  - `weighted_sum = sum((curr - prev) / prev * 100 * w for prev, curr, w in steps)`
  - `weight_total = sum(w for _, _, w in steps)`
  - `expected = round(weighted_sum / weight_total)`
  - `assert result == expected`

### test_count_change_rate_all_zero_except_last_returns_none()

- 함수 docstring(원문): "iii. 완전 무거래: 마지막 구간을 제외한 모든 prev_count가 0이면 계산 가능한 스텝이 하나도 없으므로 여전히 None을 반환해야 한다."
- Given/When: `result = apt_trend_service._build_count_change_rate(_trend([0, 0, 0, 0, 0, 5]))`.
- Then(원문 assert): `assert result is None`.

### test_count_change_rate_never_raises_zero_division_error()

- 함수 docstring(원문): "모든 스텝이 prev_count == 0이어도(마지막 구간 포함 전부 0) ZeroDivisionError가 발생하면 안 된다."
- Given/When: `result = apt_trend_service._build_count_change_rate(_trend([0, 0, 0, 0, 0, 0]))`.
- Then(원문 assert): `assert result is None`.

### test_count_change_rate_no_min_trade_count_constant()

- 함수 docstring(원문): "MIN_TRADE_COUNT 상수가 apt_trend_service에서 완전히 제거되었는지 확인한다."
- Given/When/Then(원문 assert): `assert not hasattr(apt_trend_service, "MIN_TRADE_COUNT")`.

## 6. 모듈 레벨 상수/설정값

없음.

## 7. 역참조(이 파일을 사용하는 곳)

- 없음(pytest가 자동 수집하는 테스트 모듈이며, 다른 소스 모듈이 import하지 않음).

## 8. 재생성 지침

> 위 내용을 근거로 `backend_fastApi/tests/services/test_apt_trend_service.py` 파일을 동일한 로직으로 재작성하라. 여기 명시되지 않은 세부 구현(변수명 스타일, 코드 포맷 등)은 기존 프로젝트 컨벤션(PEP 8, 저장소 내 동일 계층 파일들의 스타일)을 따른다.
