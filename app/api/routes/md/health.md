# health.py 명세

## 1. 메타 정보

| 항목 | 값 |
|---|---|
| source_path | backend_fastApi/app/api/routes/health.py |
| source_sha256 | 8c59f465d07930f25b6b13118eda06ba6744da31126504a56a44bf75c0fb8550 |
| source_lines | 8 |

## 2. 역할 요약

서버 헬스체크용 `/health` GET 엔드포인트를 제공하는 `APIRouter`를 정의한다.

## 3. 외부 인터페이스

| 이름 | 종류 | 시그니처 | 반환 타입 |
|---|---|---|---|
| router | const | `router = APIRouter(tags=["health"])` | APIRouter |
| health_check | function | `def health_check()` | dict |

## 4. 의존성(imports)

- 표준 라이브러리: 없음
- 서드파티:
  - `from fastapi import APIRouter`
- 내부 모듈: 없음

## 5. 로직 상세

### router

- 목적: `health` 태그를 가진 `APIRouter` 인스턴스 생성.
- 처리 흐름: `router = APIRouter(tags=["health"])`.
- 반환값: 해당 없음(모듈 레벨 변수).

### health_check

- 목적: 서버 동작 확인용 헬스체크 엔드포인트.
- 파라미터: 없음.
- 처리 흐름:
  1. `@router.get("/health")` 데코레이터로 GET `/health` 경로에 매핑.
  2. 고정된 딕셔너리를 반환.
- 반환값: `{"status": "ok"}` (항상 동일, 분기 없음).

## 6. 모듈 레벨 상수/설정값

없음(모듈 레벨의 유일한 값인 `router`는 3항 외부 인터페이스 표에 이미 기재).

## 7. 역참조(이 파일을 사용하는 곳)

- `app/main.py` — `from app.api.routes import health` 후 `app.include_router(health.router)`로 등록.

## 8. 재생성 지침

> 위 내용을 근거로 `backend_fastApi/app/api/routes/health.py` 파일을 동일한 로직으로 재작성하라. 여기 명시되지 않은 세부 구현(변수명 스타일, 코드 포맷 등)은 기존 프로젝트 컨벤션(PEP 8, 저장소 내 동일 계층 파일들의 스타일)을 따른다.
