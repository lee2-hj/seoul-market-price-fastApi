# main.py 명세

## 1. 메타 정보

| 항목 | 값 |
|---|---|
| source_path | backend_fastApi/app/main.py |
| source_sha256 | 870acbc4ff1a1733c2e746ee75225e686fcb58ed825e42fa0969283c08c4557f |
| source_lines | 24 |

## 2. 역할 요약

FastAPI 애플리케이션 인스턴스를 생성하고 CORS 미들웨어를 설정한 뒤, `health` 라우터와 `api_v1_router`를 등록한다. 루트 경로(`/`) 헬스 확인용 엔드포인트를 정의한다.

## 3. 외부 인터페이스

| 이름 | 종류 | 시그니처 | 반환 타입 |
|---|---|---|---|
| app | const | `app = FastAPI(title=settings.app_name)` | FastAPI |
| root | function | `def root()` | dict |

## 4. 의존성(imports)

- 표준 라이브러리: 없음
- 서드파티:
  - `from fastapi import FastAPI`
  - `from fastapi.middleware.cors import CORSMiddleware`
- 내부 모듈:
  - `from app.api.routes import health`
  - `from app.api.v1.router import router as api_v1_router`
  - `from app.core.config import settings`

## 5. 로직 상세

### app (모듈 레벨 초기화)

- 목적: FastAPI 앱 인스턴스를 생성하고, CORS 미들웨어와 라우터를 등록한다.
- 파라미터: 없음(모듈 레벨 실행 코드).
- 처리 흐름:
  1. `app = FastAPI(title=settings.app_name)`로 앱 인스턴스를 생성한다(`title`은 `settings.app_name` 값을 그대로 사용).
  2. `app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])`로 CORS 미들웨어를 추가한다.
     - `allow_origins`는 `settings.cors_origins` 값.
     - `allow_credentials=True` 고정.
     - `allow_methods=["*"]` 고정(모든 메서드 허용).
     - `allow_headers=["*"]` 고정(모든 헤더 허용).
  3. `app.include_router(health.router)`로 `health` 모듈의 라우터를 등록한다.
  4. `app.include_router(api_v1_router)`로 `app.api.v1.router`의 `router`(별칭 `api_v1_router`)를 등록한다.
- 반환값: 해당 없음(모듈 레벨 변수 `app`이 결과물).

### root

- 목적: 서버 동작 확인용 루트 엔드포인트.
- 파라미터: 없음.
- 처리 흐름:
  1. `@app.get("/")` 데코레이터로 GET `/` 경로에 매핑된다.
  2. 호출 시 고정된 딕셔너리를 반환한다.
- 반환값: `{"message": "FastAPI server is running"}` (항상 동일한 값, 분기 없음).

## 6. 모듈 레벨 상수/설정값

없음(모듈 레벨의 유일한 값인 `app`은 3항 외부 인터페이스 표에 이미 기재).

## 7. 역참조(이 파일을 사용하는 곳)

- `Dockerfile`: `CMD ["uvicorn", "app.main:app", ...]` 형태로 `app.main` 모듈의 `app` 객체를 ASGI 엔트리포인트로 사용(2개 CMD 라인, 하나는 주석 처리됨).

## 8. 재생성 지침

> 위 내용을 근거로 `backend_fastApi/app/main.py` 파일을 동일한 로직으로 재작성하라. 여기 명시되지 않은 세부 구현(변수명 스타일, 코드 포맷 등)은 기존 프로젝트 컨벤션(PEP 8, 저장소 내 동일 계층 파일들의 스타일)을 따른다.
