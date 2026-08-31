# apt_trend_service.py 명세

## 1. 메타 정보

| 항목 | 값 |
|---|---|
| source_path | backend_fastApi/app/services/apt_trend_service.py |
| source_sha256 | ef00bd2f266b323afd9fdf3261a5aa190ca9c61cb9645b1e873e2d41db9220d2 |
| source_lines | 354 |

## 2. 역할 요약

`apt_mkt_trends` 마트에서 단지(cgg_cd+stdg_cd+apt_name) 조건에 맞는 최근 90일(또는 이력 전체에서 조건에 매칭되는 최근 시점 기준 90일) 실거래를 단지 단위로 집계해 거래건수/거래금액/평균가/최고가, 2주 단위 추이, 평형별 비율, 최근 실거래, 면적별 통계를 단일 JSON으로 반환하는 `get_apt_trend_summary`와 내부 헬퍼들을 정의한다.

## 3. 외부 인터페이스

| 이름 | 종류 | 시그니처 | 반환 타입 |
|---|---|---|---|
| MART_TABLE | const | `MART_TABLE = "apt_mkt_trends"` | str |
| PERIOD_DAYS | const | `PERIOD_DAYS = 90` | int |
| BIWEEKLY_BUCKET_COUNT | const | `BIWEEKLY_BUCKET_COUNT = 6` | int |
| PYEONG_DIVISOR | const | `PYEONG_DIVISOR = 3.305785` | float |
| logger | const | `logger = logging.getLogger(__name__)` | logging.Logger |
| _period_range | function | `def _period_range(today: date) -> tuple[date, date]` | tuple[date, date] |
| _build_entity_conditions | function | `def _build_entity_conditions(cgg_cd: str \| None, stdg_cd: str \| None, mno: str \| None, sno: str \| None, apt_name: str \| None) -> tuple[list[str], dict[str, Any]]` | tuple[list[str], dict[str, Any]] |
| _build_where_clause | function | `def _build_where_clause(cgg_cd: str \| None, stdg_cd: str \| None, mno: str \| None, sno: str \| None, apt_name: str \| None, start_date: date, end_date: date) -> tuple[str, dict[str, Any]]` | tuple[str, dict[str, Any]] |
| _fetch_rows | function | `def _fetch_rows(con, cgg_cd: str \| None, stdg_cd: str \| None, mno: str \| None, sno: str \| None, apt_name: str \| None, start_date: date, end_date: date) -> list[dict[str, Any]]` | list[dict[str, Any]] |
| _to_exclusive_area | function | `def _to_exclusive_area(pyeong: float) -> str` | str |
| _group_key | function | `def _group_key(row: dict[str, Any]) -> tuple[str, str, str]` | tuple[str, str, str] |
| _generate_biweekly_buckets | function | `def _generate_biweekly_buckets(start_date: date, end_date: date) -> list[tuple[date, date]]` | list[tuple[date, date]] |
| _build_biweekly_trend | function | `def _build_biweekly_trend(rows: list[dict[str, Any]], buckets: list[tuple[date, date]]) -> list[dict[str, Any]]` | list[dict[str, Any]] |
| _build_count_change_rate | function | `def _build_count_change_rate(biweekly_trend: list[dict[str, Any]]) -> int \| None` | int \| None |
| _pyeong_grp | function | `def _pyeong_grp(pyeong: float) -> str` | str |
| _build_area_ratio | function | `def _build_area_ratio(rows: list[dict[str, Any]], total_deal_count: int) -> list[dict[str, Any]]` | list[dict[str, Any]] |
| _build_recent_deals | function | `def _build_recent_deals(rows: list[dict[str, Any]]) -> list[dict[str, Any]]` | list[dict[str, Any]] |
| _build_area_deals | function | `def _build_area_deals(rows: list[dict[str, Any]]) -> list[dict[str, Any]]` | list[dict[str, Any]] |
| _build_apt_trend_item | function | `def _build_apt_trend_item(key: tuple[str, str, str], rows: list[dict[str, Any]], buckets: list[tuple[date, date]]) -> dict[str, Any]` | dict[str, Any] |
| get_apt_trend_summary | function | `def get_apt_trend_summary(*, cgg_cd: str \| None, stdg_cd: str \| None, mno: str \| None, sno: str \| None, apt_name: str \| None = None) -> dict[str, Any]` | dict[str, Any] |

## 4. 의존성(imports)

- 표준 라이브러리:
  - `from collections import OrderedDict`
  - `from datetime import date, timedelta`
  - `import logging`
  - `from typing import Any`
- 서드파티: 없음
- 내부 모듈:
  - `from app.core import duckdb_client`
  - `from app.core.config import settings`

파일 최상단 주석(9~16행, `MART_TABLE` 선언 직전): `apt_mkt_trends 마트 실제 컬럼(DESCRIBE로 확인): cgg_cd, cgg_nm, stdg_cd, stdg_nm, apt_name, mno, sno, deal_date, floor, trade_amount(DECIMAL, 만원), pyeong(DOUBLE), trade_count(INTEGER), pyeong_amt(DOUBLE), base_date. apt_name은 실제 컬럼이며 항상 채워져 있다(NULL/빈값 없음 확인). 다만 apt_name은 전역 고유하지 않고(예: '현대'가 26개 서로 다른 법정동에 존재) 같은 법정동 안에서 한 단지가 여러 지번(mno/sno)에 걸쳐 있을 수 있어(예: 화곡동 '남광아파트' 2개 지번), 그룹 키는 반드시 (cgg_cd, stdg_cd, apt_name)로 잡아야 한다. 한 row는 (cgg_cd, stdg_cd, mno, sno, deal_date, floor, pyeong) 조합으로 유일하고, trade_amount/trade_count는 그 조합에 몰린 거래건들의 합계 금액/건수다(RTT 마트와 동일한 관례).`

## 5. 로직 상세

### MART_TABLE / PERIOD_DAYS / BIWEEKLY_BUCKET_COUNT / PYEONG_DIVISOR / logger

- 값은 6항 표 참조.

### _period_range

- 목적(원문 docstring): "today(anchor)를 기준으로 (anchor - 90일) ~ anchor 구간의 시작일/종료일을 반환한다. 처음 호출 시 anchor는 실제 오늘 날짜이지만, 그 구간에 조건에 맞는 거래가 없으면 get_apt_trend_summary()가 이 anchor를 과거로 이동시킬 수 있다 — 즉 최종 응답의 search_period가 항상 \"오늘 기준\"이라고 가정하면 안 된다."
- 파라미터: `today: date`.
- 처리 흐름: `end_date = today`; `start_date = today - timedelta(days=PERIOD_DAYS)`; `return start_date, end_date`.
- 반환값: `(start_date, end_date)`.

### _build_entity_conditions

- 목적(원문 docstring): "날짜 조건을 제외한, 단지 필터(cgg_cd/stdg_cd/mno/sno/apt_name) 조건 목록과 파라미터. range-앵커 폴백(resolve_recent_match_date)은 날짜 범위 없이 이 조건만으로 이력 전체를 조회해야 하므로, 날짜 조건이 항상 포함되는 _build_where_clause와 분리했다."
- 파라미터: `cgg_cd: str | None`, `stdg_cd: str | None`, `mno: str | None`, `sno: str | None`, `apt_name: str | None`.
- 처리 흐름:
  1. `conditions: list[str] = []`; `params: dict[str, Any] = {}`.
  2. `if cgg_cd: conditions.append("cgg_cd = $cgg_cd"); params["cgg_cd"] = cgg_cd`.
  3. `if stdg_cd: conditions.append("stdg_cd = $stdg_cd"); params["stdg_cd"] = stdg_cd`.
  4. `if mno: conditions.append("mno = $mno"); params["mno"] = mno`.
  5. `if sno: conditions.append("sno = $sno"); params["sno"] = sno`.
  6. `if apt_name and apt_name.strip():` 이면(주석 원문: "apt_mkt_trends의 실제 apt_name 컬럼을 대소문자 무시 부분일치로 필터링한다.") `conditions.append("apt_name ILIKE $apt_name")`; `params["apt_name"] = f"%{apt_name.strip()}%"`.
  7. `return conditions, params`.
- 반환값: 조건 문자열 리스트(AND로 결합되지 않은 상태)와 파라미터 딕셔너리.

### _build_where_clause

- 목적: 날짜 범위 조건(`deal_date BETWEEN`)과 `_build_entity_conditions`의 단지 필터를 합쳐 전체 `WHERE` 절을 조립.
- 파라미터: `cgg_cd: str | None`, `stdg_cd: str | None`, `mno: str | None`, `sno: str | None`, `apt_name: str | None`, `start_date: date`, `end_date: date`.
- 처리 흐름:
  1. `entity_conditions, entity_params = _build_entity_conditions(cgg_cd, stdg_cd, mno, sno, apt_name)`.
  2. `conditions = ["deal_date BETWEEN $start_date AND $end_date", *entity_conditions]`.
  3. `params: dict[str, Any] = {"start_date": start_date, "end_date": end_date, **entity_params}`.
  4. `return "WHERE " + " AND ".join(conditions), params`.
- 반환값: 날짜 조건이 항상 포함된 `WHERE` 절과 파라미터.

### _fetch_rows

- 목적(원문 docstring): "apt_mkt_trends 마트(재귀 glob, base_date 파티션 전체) 에서 필터 조건에 맞는 row를 조회한다."
- 파라미터: `con`, `cgg_cd: str | None`, `stdg_cd: str | None`, `mno: str | None`, `sno: str | None`, `apt_name: str | None`, `start_date: date`, `end_date: date`.
- 처리 흐름:
  1. `parquet_glob = f"{duckdb_client.mart_base_path(MART_TABLE)}/**/*.parquet"`.
  2. `where_clause, params = _build_where_clause(cgg_cd, stdg_cd, mno, sno, apt_name, start_date, end_date)`.
  3. 쿼리(f-string, `{where_clause}` 치환, glob은 파라미터 바인딩이 아닌 문자열 리터럴로 직접 삽입):
     ```python
     query = f"""
         SELECT
             cgg_cd, cgg_nm, stdg_cd, stdg_nm, apt_name, mno, sno,
             deal_date, floor, trade_amount, pyeong, trade_count
         FROM read_parquet('{parquet_glob}')
         {where_clause}
     """
     ```
  4. `result = con.execute(query, params)`; `return duckdb_client.rows_to_dicts(result)`.
- 반환값: 조건에 맞는 row의 12개 컬럼(`cgg_cd, cgg_nm, stdg_cd, stdg_nm, apt_name, mno, sno, deal_date, floor, trade_amount, pyeong, trade_count`)만 포함한 딕셔너리 리스트.

### _to_exclusive_area

- 목적(원문 docstring): "마트에 전용면적(㎡) 컬럼이 없어, pyeong * 3.305785로 역산해 표시용 문자열을 만든다."
- 파라미터: `pyeong: float`.
- 처리 흐름: `return f"{pyeong * PYEONG_DIVISOR:.2f}"`.
- 반환값: 소수 둘째 자리까지 포맷된 전용면적(㎡) 문자열.

### _group_key

- 목적(원문 docstring): "단지 그룹 키. apt_name은 전역 고유하지 않으므로(동명 단지 다수 존재) 반드시 (cgg_cd, stdg_cd, apt_name)로 묶어야 서로 다른 동의 동명 단지가 섞이지 않는다."
- 파라미터: `row: dict[str, Any]`.
- 처리 흐름: `return row["cgg_cd"], row["stdg_cd"], row["apt_name"]`.
- 반환값: `(cgg_cd, stdg_cd, apt_name)` 3튜플.

### _generate_biweekly_buckets

- 목적(원문 docstring): "조회 구간(90일)을 BIWEEKLY_BUCKET_COUNT(6)개 구간으로 균등 분할해 (구간 시작일, 구간 종료일) 목록을 만든다. 전체 일수가 6으로 나누어떨어지지 않으면 나머지 일수를 구간별로 최대한 고르게 배분한다."
- 파라미터: `start_date: date`, `end_date: date`.
- 처리 흐름: `rtt_service._generate_biweekly_buckets`와 동일한 로직.
  1. `total_days = (end_date - start_date).days + 1`.
  2. `buckets: list[tuple[date, date]] = []`.
  3. `range(BIWEEKLY_BUCKET_COUNT)`의 각 `i`에 대해:
     a. `bucket_start = start_date + timedelta(days=round(i * total_days / BIWEEKLY_BUCKET_COUNT))`.
     b. `bucket_end = start_date + timedelta(days=round((i + 1) * total_days / BIWEEKLY_BUCKET_COUNT) - 1)`.
     c. `buckets.append((bucket_start, bucket_end))`.
  4. `return buckets`.
- 반환값: 6개의 `(bucket_start, bucket_end)` 튜플 리스트.

### _build_biweekly_trend

- 목적: docstring 없음(주석만 있음). 90일 구간을 6등분한 구간별 거래건수/평균 거래가 집계.
- 파라미터: `rows: list[dict[str, Any]]`, `buckets: list[tuple[date, date]]`.
- 처리 흐름:
  1. `trend: list[dict[str, Any]] = []`.
  2. `buckets`의 각 `(bucket_start, bucket_end)`에 대해:
     a. 주석 원문: "duckdb_client.rows_to_dicts()가 date를 ISO 문자열로 변환하므로(rtt_service와 동일 관례), 문자열끼리 비교한다(ISO 8601 형식은 사전식 비교 = 날짜순 비교)."
     b. `start_str, end_str = bucket_start.isoformat(), bucket_end.isoformat()`.
     c. `bucket_rows = [r for r in rows if start_str <= r["deal_date"] <= end_str]`.
     d. `deal_count = sum(r["trade_count"] for r in bucket_rows)`; `total_amount = sum(r["trade_amount"] for r in bucket_rows)`.
     e. `avg_price = round(total_amount / deal_count) if deal_count else 0`.
     f. `trend.append({"biweekly_period": f"{bucket_start.isoformat()}/{bucket_end.isoformat()}", "deal_count": deal_count, "avg_price": avg_price})`.
  3. `return trend`.
- 반환값: 6개 구간의 `{biweekly_period, deal_count, avg_price}` 리스트.

### _build_count_change_rate

- 목적(원문 docstring): "인접한 2주 구간 간 deal_count 증감률을 순서대로 계산해, 오래된 스텝부터 1,2,3,...로 선형 증가하는 가중치(최신 스텝일수록 가중치가 높음)로 가중평균한다. 이전 구간의 deal_count가 0이면 증감률(%) 자체를 정의할 수 없으므로(0으로 나누기) 그 스텝만 제외한다 — 거래건수가 적다는 이유로 제외하지는 않는다(rtt_service._build_volume_change_rate와 동일한 원칙). 계산 가능한 스텝이 하나도 없으면(=마지막 구간을 제외한 나머지 구간 전부 거래 0건) None을 반환한다."
- 파라미터: `biweekly_trend: list[dict[str, Any]]`.
- 처리 흐름:
  1. `step_count = len(biweekly_trend) - 1`.
  2. `if step_count < 1: return None`.
  3. `weighted_sum = 0.0`; `weight_total = 0`.
  4. `range(step_count)`의 각 `i`에 대해:
     a. `prev_count = biweekly_trend[i]["deal_count"]`; `curr_count = biweekly_trend[i + 1]["deal_count"]`.
     b. `if prev_count == 0: continue`(주석 원문: "0으로 나누기 방지만 — 거래건수가 적다는 이유로 제외하지 않는다.").
     c. `weight = i + 1`(주석 원문: "항상 스텝 가중치 적용").
     d. `step_rate = (curr_count - prev_count) / prev_count * 100`.
     e. `weighted_sum += step_rate * weight`; `weight_total += weight`.
  5. `if weight_total == 0: return None`.
  6. `return round(weighted_sum / weight_total)`.
- 반환값: 가중평균 증감률을 반올림한 정수, 또는 계산 불가 시(`step_count < 1` 또는 모든 스텝이 `prev_count == 0`) `None`.

### _pyeong_grp

- 목적(원문 docstring): "평형을 10평 단위 그룹으로 분류한다. area_deals/recent_deals의 표시용 pyeong과 동일하게 반올림한 값을 기준으로 그룹을 나눠야 한다(예: 19.97평은 반올림하면 20평이므로 '20' 그룹이어야 하며, 반올림 전 원본값을 그대로 버림(floor) 계산하면 '10' 그룹으로 잘못 분류된다). 10평 미만은 '10' 그룹에 포함하고, 그 이상은 실제 데이터 범위에 맞춰 50/60/70... 등 상한 없이 동적으로 분류한다."
- 파라미터: `pyeong: float`.
- 처리 흐름: `bucket = (round(pyeong) // 10) * 10`; `return str(bucket) if bucket >= 10 else "10"`.
- 반환값: `rtt_service._pyeong_grp`와 동일한 규칙의 문자열.

### _build_area_ratio

- 목적(원문 docstring): "평형 그룹(10평 단위, 상한 없이 실제 데이터 기준으로 동적 분류)별 거래건수와 전체 대비 비중(%)을 집계한다. 거래가 없는(비중 0%) 그룹은 결과에 포함하지 않는다."
- 파라미터: `rows: list[dict[str, Any]]`, `total_deal_count: int`.
- 처리 흐름:
  1. `counts: dict[str, int] = {}`.
  2. `rows`의 각 `row`에 대해 `grp = _pyeong_grp(row["pyeong"])`; `counts[grp] = counts.get(grp, 0) + row["trade_count"]`.
  3. `result: list[dict[str, Any]] = []`.
  4. `sorted(counts, key=int)`의 각 `grp`에 대해:
     a. `deal_count = counts[grp]`.
     b. `if deal_count <= 0: continue`.
     c. `share_percentage = round(deal_count / total_deal_count * 100, 2) if total_deal_count else 0.0`.
     d. `result.append({"pyeong_grp": grp, "deal_count": deal_count, "share_percentage": share_percentage})`.
  5. `return result`.
- 반환값: 평형 그룹 오름차순, 거래 0건 그룹 제외 리스트.

### _build_recent_deals

- 목적(원문 docstring): "개수 제한 없이 전체 거래 내역을 거래일자 최신순(내림차순)으로 반환한다."
- 파라미터: `rows: list[dict[str, Any]]`.
- 처리 흐름:
  1. `ordered = sorted(rows, key=lambda r: r["deal_date"], reverse=True)`.
  2. `return [{"deal_date": r["deal_date"], "exclusive_area": _to_exclusive_area(r["pyeong"]), "pyeong": round(r["pyeong"]), "floor": r["floor"], "deal_amount": round(r["trade_amount"] / r["trade_count"]) if r["trade_count"] else 0} for r in ordered]`.
- 반환값: 전체 row(개수 제한 없음)를 거래일 내림차순으로 변환한 리스트.

### _build_area_deals

- 목적: docstring 없음. `pyeong` 값별로 거래건수/평균 거래가를 집계.
- 파라미터: `rows: list[dict[str, Any]]`.
- 처리 흐름:
  1. `groups: "OrderedDict[float, dict[str, Any]]" = OrderedDict()`.
  2. `rows`의 각 `row`에 대해:
     a. `pyeong = row["pyeong"]`; `group = groups.get(pyeong)`.
     b. `group`이 `None`이면 `group = {"pyeong": pyeong, "_cnt": 0, "_amt": 0}`; `groups[pyeong] = group`.
     c. `group["_cnt"] += row["trade_count"]`; `group["_amt"] += row["trade_amount"]`.
  3. `return [{"exclusive_area": _to_exclusive_area(g["pyeong"]), "pyeong": round(g["pyeong"]), "deal_count": g["_cnt"], "avg_deal_price": round(g["_amt"] / g["_cnt"]) if g["_cnt"] else 0} for g in sorted(groups.values(), key=lambda g: g["pyeong"])]`.
- 반환값: `pyeong` 오름차순으로 정렬된 면적별 요약 통계 리스트(원본 `pyeong` 값 기준 그룹화, 반올림은 출력 시에만 적용).

### _build_apt_trend_item

- 목적: docstring 없음. 그룹 키(`(cgg_cd, stdg_cd, apt_name)`)에 속한 row들로부터 단지 하나의 트렌드 집계 항목을 조립.
- 파라미터: `key: tuple[str, str, str]`, `rows: list[dict[str, Any]]`, `buckets: list[tuple[date, date]]`.
- 처리 흐름:
  1. `cgg_cd, stdg_cd, apt_name = key`; `first = rows[0]`.
  2. `total_deal_count = sum(r["trade_count"] for r in rows)`.
  3. `total_deal_amount = round(sum(r["trade_amount"] for r in rows))`.
  4. `average_deal_price = round(total_deal_amount / total_deal_count) if total_deal_count else 0`.
  5. `max_deal_price = round(max((r["trade_amount"] / r["trade_count"] for r in rows if r["trade_count"]), default=0))`.
  6. `biweekly_trend = _build_biweekly_trend(rows, buckets)`.
  7. `return {...}`(아래 12개 키).
- 반환값: 딕셔너리 `{"apt_name": apt_name, "cgg_cd": cgg_cd, "cgg_nm": first["cgg_nm"], "stdg_cd": stdg_cd, "stdg_nm": first["stdg_nm"], "total_deal_count": total_deal_count, "total_deal_amount": total_deal_amount, "average_deal_price": average_deal_price, "max_deal_price": max_deal_price, "count_change_rate": _build_count_change_rate(biweekly_trend), "biweekly_trend": biweekly_trend, "area_ratio": _build_area_ratio(rows, total_deal_count), "recent_deals": _build_recent_deals(rows), "area_deals": _build_area_deals(rows)}`. `cgg_nm`/`stdg_nm`은 그룹의 첫 row(`first`)에서 가져옴(그룹 내 모든 row가 동일하다고 가정).

### get_apt_trend_summary

- 목적(원문 docstring, 3문단): "기본적으로 오늘 기준 최근 90일간, 지정된(선택적) 조건에 맞는 apt_mkt_trends 실거래 데이터를 단지(cgg_cd+stdg_cd+apt_name) 단위로 집계하여 단일 JSON으로 반환한다. apt_name은 apt_mkt_trends의 실제 컬럼이지만 전역 고유하지 않아(동명 단지가 여러 법정동에 존재) cgg_cd+stdg_cd와 함께 그룹 키로 사용한다. apt_name이 주어지면 실제 apt_name 컬럼을 SQL WHERE(ILIKE)에서 부분일치 필터링한다(다른 마트를 조인하지 않는다).\n\n이 90일 창(오늘 기준)에 조건에 맞는 거래가 하나도 없으면, 날짜 범위 제한 없이 전체 이력에서 조건에 매칭되는 가장 최근 deal_date를 한 번에 찾아(`resolve_recent_match_date`) 그 날짜를 새 end_date로 삼아 90일 창 전체를 그 시점으로 이동시켜 재조회한다(\"파티션 폴백\"이 아니라 \"조회 창의 기준일(anchor) 이동\"). 이동된 시작일이 원래 창의 시작일보다 settings.max_base_date_lookback일 이상 더 과거이거나, 애초에 그 조건의 거래가 이력 전체에 없으면 창을 이동하지 않고 기존처럼 빈 결과를 그대로 반환한다(에러 아님). 창이 실제로 이동된 경우 search_period.start_date/end_date는 \"오늘 기준 90일\"이 아니라 이동된 실제 구간을 반영한다.\n\ncount_change_rate는 biweekly_trend(90일을 6구간으로 균등 분할한 거래량)의 인접 구간(스텝)별 증감률을, 오래된 스텝일수록 낮고 최신 스텝일수록 높은 가중치(1,2,3,...)로 가중평균해 계산한다. 이전 구간 거래건수가 0인 스텝만 계산에서 제외한다(자세한 내용은 _build_count_change_rate 참고). 여러 단지가 매칭되면 총 거래건수(total_deal_count) 내림차순으로 정렬한다."
- 파라미터(모두 키워드 전용): `cgg_cd: str | None`, `stdg_cd: str | None`, `mno: str | None`, `sno: str | None`, `apt_name: str | None = None`.
- 처리 흐름:
  1. `start_date, end_date = _period_range(date.today())`.
  2. `con = duckdb_client.get_connection()`.
  3. `try:` 블록:
     a. `rows = _fetch_rows(con, cgg_cd, stdg_cd, mno, sno, apt_name, start_date, end_date)`.
     b. `if not rows:` 이면(앵커 폴백 로직):
        i. `naive_start, naive_end = start_date, end_date`.
        ii. `entity_conditions, entity_params = _build_entity_conditions(cgg_cd, stdg_cd, mno, sno, apt_name)`.
        iii. `match_where = ("WHERE " + " AND ".join(entity_conditions)) if entity_conditions else ""`.
        iv. `full_glob = f"{duckdb_client.mart_base_path(MART_TABLE)}/**/*.parquet"`.
        v. `matched_date = duckdb_client.resolve_recent_match_date(con, full_glob, "deal_date", match_where, entity_params)`.
        vi. `if matched_date is not None and matched_date >= start_date - timedelta(days=settings.max_base_date_lookback):` 이면:
            - `end_date = matched_date`; `start_date = end_date - timedelta(days=PERIOD_DAYS)`.
            - `rows = _fetch_rows(con, cgg_cd, stdg_cd, mno, sno, apt_name, start_date, end_date)`.
            - `logger.info("Anchor fallback used for table=%s, condition_summary=%s, naive_window=%s~%s, matched_window=%s~%s", MART_TABLE, (match_where or "(no filter)")[:100], naive_start, naive_end, start_date, end_date)`.
        vii. 주석 원문: "matched_date가 없거나 lookback 상한을 넘으면 rows/기간은 나이브 값 그대로 — 기존과 동일하게 빈 결과 반환(에러 아님)."
  4. `finally: con.close()`.
  5. `buckets = _generate_biweekly_buckets(start_date, end_date)`.
  6. `grouped: "OrderedDict[tuple[str, str, str], list[dict[str, Any]]]" = OrderedDict()`; `rows`의 각 `row`에 대해 `grouped.setdefault(_group_key(row), []).append(row)`.
  7. `items = [_build_apt_trend_item(key, group_rows, buckets) for key, group_rows in grouped.items()]`.
  8. `items.sort(key=lambda item: item["total_deal_count"], reverse=True)`.
  9. `return {"status": "success", "search_period": {"start_date": start_date, "end_date": end_date}, "count": len(items), "data": items}`.
- 반환값: 딕셔너리(`status`, `search_period`, `count`, `data`). `data`는 총 거래건수 내림차순 정렬된 단지별 트렌드 항목 리스트. `PERIOD_DAYS`를 빼는 방식이 `_period_range`(`start_date = today - timedelta(days=PERIOD_DAYS)`)와 앵커 이동 시(`start_date = end_date - timedelta(days=PERIOD_DAYS)`)에 동일하게 적용됨(rtt_service의 `PERIOD_DAYS - 1`과 다름에 유의).

## 6. 모듈 레벨 상수/설정값

| 이름 | 값 |
|---|---|
| MART_TABLE | `"apt_mkt_trends"` |
| PERIOD_DAYS | `90` |
| BIWEEKLY_BUCKET_COUNT | `6` |
| PYEONG_DIVISOR | `3.305785` |
| logger | `logging.getLogger(__name__)` |

## 7. 역참조(이 파일을 사용하는 곳)

- `app/api/v1/endpoints/apt_trend.py` — `from app.services import apt_trend_service` 후 `apt_trend_service.get_apt_trend_summary(...)` 호출.

## 8. 재생성 지침

> 위 내용을 근거로 `backend_fastApi/app/services/apt_trend_service.py` 파일을 동일한 로직으로 재작성하라. 여기 명시되지 않은 세부 구현(변수명 스타일, 코드 포맷 등)은 기존 프로젝트 컨벤션(PEP 8, 저장소 내 동일 계층 파일들의 스타일)을 따른다.
