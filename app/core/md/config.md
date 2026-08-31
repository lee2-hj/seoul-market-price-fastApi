# config.py 명세

## 1. 메타 정보

| 항목 | 값 |
|---|---|
| source_path | backend_fastApi/app/core/config.py |
| source_sha256 | a0ca850dff88265881a454766cbac82120b1d013aa6e6b70ca28bd3330efbb6b |
| source_lines | 34 |

## 2. 역할 요약

`pydantic_settings.BaseSettings`를 상속한 `Settings` 클래스를 정의해 `.env` 파일과 환경 변수로부터 애플리케이션 설정값(앱 이름, mart 소급 조회 개수, CORS origin, MinIO/S3 접속 정보, 데이터 레이크 버킷명)을 로드한다. 모듈 임포트 시 `Settings()` 인스턴스를 `settings`로 생성해 다른 모듈에 노출한다.

## 3. 외부 인터페이스

| 이름 | 종류 | 시그니처 | 반환 타입 |
|---|---|---|---|
| Settings | class | `class Settings(BaseSettings)` | - |
| settings | const | `settings = Settings()` | Settings |

## 4. 의존성(imports)

- 표준 라이브러리: 없음
- 서드파티:
  - `from pydantic import Field`
  - `from pydantic_settings import BaseSettings, SettingsConfigDict`
- 내부 모듈: 없음

## 5. 로직 상세

### Settings

- 목적: 환경 변수/`.env` 파일 기반 설정값을 타입 검증과 함께 로드하는 설정 클래스.
- 파라미터: 없음(클래스 정의, 필드는 아래 표 참조).
- 처리 흐름:
  1. `model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")`로 `.env` 파일 경로/인코딩을 지정하고, 정의되지 않은 추가 환경 변수는 무시(`extra="ignore"`)하도록 설정한다.
  2. 필드는 아래 "필드 목록"(클래스 정의 순서) 표에 따라 선언되며, `BaseSettings`가 인스턴스화 시점에 환경 변수/`.env`에서 값을 채우고 타입 검증을 수행한다.
- 반환값: 해당 없음(클래스 정의).

**필드 목록(클래스 정의 순서)**

| 필드명 | 타입 | 기본값 | Field 설명 |
|---|---|---|---|
| app_name | str | `"backend_fastApi"` | 없음(Field 미사용, 단순 기본값 대입) |
| debug | bool | `False` | 없음(Field 미사용, 단순 기본값 대입) |
| max_base_date_lookback | int | `30` | `Field(default=30, description="Maximum number of partitions to look back when searching for matching data")` |
| cors_origins | list[str] | `["*"]` | 없음(Field 미사용, 단순 기본값 대입) |
| s3_end_point | str | 없음(필수, 기본값 미지정) | 없음 |
| s3_access_key | str | 없음(필수, 기본값 미지정) | 없음 |
| s3_secret_key | str | 없음(필수, 기본값 미지정) | 없음 |
| s3_use_ssl | bool | `False` | 없음(Field 미사용, 단순 기본값 대입) |
| s3_url_style | str | `"path"` | 없음(Field 미사용, 단순 기본값 대입) |
| aws_region | str | `"ap-northeast-2"` | 없음(Field 미사용, 단순 기본값 대입) |
| raw | str | `"lake"` | 없음(Field 미사용, 단순 기본값 대입) |
| lake | str | `"warehouse"` | 없음(Field 미사용, 단순 기본값 대입) |

원문 주석(코드에 존재하는 필드별 설명):
- `max_base_date_lookback` 위: "mart 조회 조건(WHERE) 매칭 데이터가 없을 때 과거 base_date 파티션으로 소급 조회할 최대 파티션 개수. 배치가 매일 1회 적재된다고 가정하면 30 ≈ 최근 30일 소급."
- `cors_origins` 위: "프론트엔드 CORS 허용 origin (dev 기본값: 전체 허용)"
- `s3_end_point`~`aws_region` 위: "MinIO / S3 접속 정보"
- `raw`/`lake` 위: "데이터 레이크 버킷"

### settings

- 목적: 애플리케이션 전역에서 재사용할 `Settings` 싱글턴 인스턴스.
- 파라미터: 없음.
- 처리 흐름:
  1. 모듈 임포트 시 `Settings()`를 호출해 환경 변수/`.env`로부터 값을 로드한다.
- 반환값: 해당 없음(모듈 레벨 변수).

## 6. 모듈 레벨 상수/설정값

| 이름 | 값 |
|---|---|
| settings | `Settings()` 인스턴스(필드값은 5항 표 참조) |

## 7. 역참조(이 파일을 사용하는 곳)

- `app/main.py` — `from app.core.config import settings` (앱 title, CORS origins에 사용).
- `app/core/duckdb_client.py` — `from app.core.config import settings` (S3 접속 정보, `max_base_date_lookback`, `raw`/`lake` 버킷명에 사용).
- `app/services/apt_trend_service.py` — `from app.core.config import settings`.
- `app/services/rtt_service.py` — `from app.core.config import settings`.
- `tests/core/test_duckdb_client.py` — `duckdb_client.settings`(재노출된 참조)의 속성을 `monkeypatch.setattr`로 변경.
- `tests/services/test_rtt_service.py` — `rtt_service.settings`(재노출된 참조)의 `max_base_date_lookback` 속성 참조.

## 8. 재생성 지침

> 위 내용을 근거로 `backend_fastApi/app/core/config.py` 파일을 동일한 로직으로 재작성하라. 여기 명시되지 않은 세부 구현(변수명 스타일, 코드 포맷 등)은 기존 프로젝트 컨벤션(PEP 8, 저장소 내 동일 계층 파일들의 스타일)을 따른다.
