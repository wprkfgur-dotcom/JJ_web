"""
페이지 라우터: PC / 모바일 HTML 제공 (User-Agent 자동 감지)
"""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse

from ..config import TEMPLATE_DIR

router = APIRouter()

MOBILE_KEYWORDS = (
    "mobile", "android", "iphone", "ipod", "blackberry",
    "windows phone", "opera mini", "iemobile", "webos",
)
COOKIE_MAX_AGE = 60 * 60 * 24 * 30  # 30일


def is_mobile_user_agent(user_agent: str) -> bool:
    """스마트폰/모바일 디바이스 User-Agent 판별"""
    ua = (user_agent or "").lower()
    return any(k in ua for k in MOBILE_KEYWORDS)


def _page(filename: str, missing_detail: str, view_cookie: str = None) -> FileResponse:
    path = TEMPLATE_DIR / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail=missing_detail)
    headers = {
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
        "Expires": "0",
    }
    resp = FileResponse(path, headers=headers)
    if view_cookie:
        resp.set_cookie("view_mode", view_cookie, max_age=COOKIE_MAX_AGE)
    return resp


@router.get("/", response_class=HTMLResponse)
async def serve_index(request: Request):
    """
    - ?view=mobile / ?view=pc 쿼리 또는 view_mode 쿠키로 명시적 모드 지정 가능
    - 미지정 시 User-Agent 로 자동 판별 (모바일 → mobile.html, PC → index.html)
    """
    query_view = request.query_params.get("view")
    view = query_view or request.cookies.get("view_mode")

    if view == "mobile":
        use_mobile = True
    elif view == "pc":
        use_mobile = False
    else:
        use_mobile = is_mobile_user_agent(request.headers.get("user-agent", ""))

    if use_mobile and (TEMPLATE_DIR / "mobile.html").exists():
        return _page("mobile.html", "Mobile template not found", query_view)
    return _page("index.html", "Frontend index.html not found", query_view)


@router.get("/m", response_class=HTMLResponse)
async def serve_mobile_direct():
    """모바일 버전 직접 접속 라우트 (/m)"""
    return _page("mobile.html", "Mobile template not found", "mobile")
