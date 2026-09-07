from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.responses import FileResponse

from app.api.routes import health
from app.api.v1.router import router as api_v1_router
from app.core.config import settings

# Swagger UI/ReDoc 정적 자산(JS/CSS)을 CDN(jsdelivr 등)이 아니라 이 서버가 직접 서빙한다.
# 기본 FastAPI /docs, /redoc은 브라우저가 cdn.jsdelivr.net 등 외부 CDN에서 swagger-ui-bundle.js/
# swagger-ui.css/redoc.standalone.js를 내려받아야 렌더링되는데, 사내망/폐쇄망 등 브라우저가 외부
# CDN에 접근할 수 없는 배포 환경에서는 API 서버 자체는 정상이어도 문서 페이지만 빈 화면으로
# 뜬다(로컬 개발 PC는 외부 인터넷이 되니 눈치채기 어렵다). 이 정적 파일들은 저장소에 커밋되어
# 있으므로(app/static/), 빌드/런타임 어느 시점에도 외부 네트워크 접근 없이 항상 동일하게 동작한다.
#
# 자산 URL은 절대경로(/static/...)가 아니라 "static/..." 같은 상대경로로 내려준다. 이 서비스는
# 운영 CMD가 uvicorn --root-path /fastapi-direct로 뜨는데, 그 앞에 실제로 prefix를 벗겨주는
# 리버스 프록시가 없으면(예: 로컬에서 컨테이너 포트를 직접 8000으로 열어 접속하는 경우)
# request.scope["root_path"]만 보고 절대경로를 만들면 "/fastapi-direct/static/..."처럼 실제로
# 존재하지 않는 경로가 되어 404가 난다. 반면 상대경로는 브라우저가 현재 문서 URL(/docs 또는
# /fastapi-direct/docs) 기준으로 알아서 풀어주므로, 프록시가 있든 없든 --root-path 설정과
# 무관하게 항상 올바르게 동작한다(oauth2 리다이렉트처럼 origin과 문자열로 직접 이어붙이는 방식이
# 아닌 한, 이 방식이 더 견고하다). 이 API는 OAuth2 인증을 쓰지 않으므로 oauth2_redirect_url은
# 아예 설정하지 않는다(그 필드만 origin과 단순 문자열 결합이라 상대경로가 통하지 않기 때문).
STATIC_DIR = Path(__file__).resolve().parent / "static"

# 운영 CMD는 uvicorn --root-path /fastapi-direct로 뜬다. 이 옵션은 "앞단에 그 prefix를 벗겨서
# 전달해주는 리버스 프록시가 있다"는 걸 전제로 응답 URL을 보정해줄 뿐, 실제 라우팅 매칭에는
# 아무 영향을 주지 않는다 - uvicorn은 소켓으로 받은 경로를 그대로 scope["path"]에 넣는다. 그런데
# 로컬/직접 테스트처럼 그 프록시 없이 컨테이너 포트(8000)를 그대로 열어 "/fastapi-direct/..."가
# 붙은 URL로 요청하면, 아무도 그 prefix를 벗겨주지 않으므로 실제 등록된 경로("/api/v1/...",
# "/docs" 등)와 매칭되지 않아 전부 404가 난다.
#
# 이 미들웨어가 리버스 프록시가 했어야 할 "prefix 스트립" 역할을 대신 수행한다 - 들어온 요청
# 경로가 이 prefix로 시작하면 라우팅 전에 미리 벗겨낸다. 그러면 실제 프록시가 있어 이미 벗겨진
# 채로 들어오는 경우("/api/v1/...")와, 프록시 없이 prefix가 그대로 붙어 들어오는 경우
# ("/fastapi-direct/api/v1/...") 둘 다 동일하게 정상 라우팅된다.
class _StripRootPathPrefixMiddleware:
    def __init__(self, app, prefix: str) -> None:
        self.app = app
        self.prefix = prefix

    async def __call__(self, scope, receive, send):
        if scope["type"] in ("http", "websocket"):
            path = scope.get("path", "")
            if path == self.prefix or path.startswith(f"{self.prefix}/"):
                scope = dict(scope)
                scope["path"] = path[len(self.prefix):] or "/"
        await self.app(scope, receive, send)


app = FastAPI(title=settings.app_name, docs_url=None, redoc_url=None)

app.add_middleware(_StripRootPathPrefixMiddleware, prefix="/fastapi-direct")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(api_v1_router)


@app.get("/static/{file_path:path}", include_in_schema=False)
def static_file(file_path: str):
    """정적 자산(Swagger UI/ReDoc용)을 직접 서빙한다. Starlette의 app.mount(StaticFiles)를
    쓰지 않는다 - 이 서버는 uvicorn --root-path /fastapi-direct로 뜨는데, root_path가 설정된
    상태에서는 Mount 서브라우팅의 경로 계산이 어긋나 실제 파일이 있어도 404가 나는 문제를
    실측으로 확인했다(일반 @app.get 라우트는 root_path와 무관하게 정상 동작함). 그래서 일반
    라우트 하나로 직접 파일을 읽어 반환한다."""
    target = (STATIC_DIR / file_path).resolve()
    if STATIC_DIR.resolve() not in target.parents or not target.is_file():
        raise HTTPException(status_code=404, detail="Not Found")
    return FileResponse(target)


@app.get("/docs", include_in_schema=False)
def swagger_ui_html():
    return get_swagger_ui_html(
        openapi_url="openapi.json",
        title=f"{app.title} - Swagger UI",
        swagger_js_url="static/swagger-ui/swagger-ui-bundle.js",
        swagger_css_url="static/swagger-ui/swagger-ui.css",
        swagger_favicon_url="static/swagger-ui/favicon-32x32.png",
    )


@app.get("/redoc", include_in_schema=False)
def redoc_html():
    return get_redoc_html(
        openapi_url="openapi.json",
        title=f"{app.title} - ReDoc",
        redoc_js_url="static/redoc/redoc.standalone.js",
        redoc_favicon_url="static/swagger-ui/favicon-32x32.png",
        with_google_fonts=False,
    )


@app.get("/")
def root():
    return {"message": "FastAPI server is running"}
