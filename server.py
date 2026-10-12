"""
=====================================================================
종종이 & 무한매수 투자 시스템 - 고성능 웹 서버 (FastAPI)
Windows 개발 환경 및 Oracle Cloud Ubuntu Linux 서버 완벽 호환

진입점: `uvicorn server:app`  (라우터/스키마/유틸은 webapp 패키지에 분리)
=====================================================================
"""
import os
import sys

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# UTF-8 출력 보장 (Windows 콘솔 호환)
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from webapp.config import STATIC_DIR  # noqa: E402  (core 모듈 sys.path 등록 포함)
from webapp.routers import accounts, auth, backtest, integrations, market, pages  # noqa: E402

app = FastAPI(
    title="JJ Invest Web Trading Platform",
    description="종종이 3단계 LOC & 무한매수 주식 매매 시스템 (Web Edition)",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_no_cache_headers(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path == "/" or path == "/m" or path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

for module in (pages, auth, market, accounts, backtest, integrations):
    app.include_router(module.router)

# 구글 드라이브 백그라운드 동기화 시작
integrations.start_background_sync()


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "0.0.0.0")
    print("=" * 60)
    print(f">> JJ Invest Web Server: http://localhost:{port}")
    print(f">> Binding Address:      http://{host}:{port}")
    print(f">> Cross-Platform:      Ubuntu Linux & Windows Compatible")
    print("=" * 60)
    uvicorn.run("server:app", host=host, port=port, reload=False)
