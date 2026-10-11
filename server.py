"""
=====================================================================
종종이 & 무한매수 투자 시스템 - 고성능 웹 서버 (FastAPI)
Windows 개발 환경 및 Oracle Cloud Ubuntu Linux 서버 완벽 호환
=====================================================================
"""
import sys
import os
import shutil
import math
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# UTF-8 출력 보장 (Windows 콘솔 호환)
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# -------------------------------------------------------------------
# 경로 설정 (크로스 플랫폼: Windows & Ubuntu Linux)
# -------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
APP_CODE_DIR = BASE_DIR / "app_code"
DATA_DIR = APP_CODE_DIR / "data"

if str(APP_CODE_DIR) not in sys.path:
    sys.path.insert(0, str(APP_CODE_DIR))

# data 디렉터리 및 accounts.json 초기 확인
DATA_DIR.mkdir(parents=True, exist_ok=True)
ACCOUNTS_JSON = DATA_DIR / "accounts.json"
ACCOUNTS_EXAMPLE = DATA_DIR / "accounts.example.json"

if not ACCOUNTS_JSON.exists() and ACCOUNTS_EXAMPLE.exists():
    try:
        shutil.copy(ACCOUNTS_EXAMPLE, ACCOUNTS_JSON)
        print(f"[*] 예시 계좌 데이터 복사 완료: {ACCOUNTS_JSON}")
    except Exception as e:
        print(f"[!] 계좌 예시 데이터 복사 실패: {e}")

# 코어 모듈 임포트
from core.account_manager import AccountManager
from core.user_manager import UserManager
from core.data import fetch_market_data, get_stock_price_for_date, get_exact_price_from_db
from core.backtest_runner import run_strategies, build_chart_series
from core.strategy_registry import ACCOUNT_STRATEGY_OPTIONS, DISPLAY_NAMES, JONGJONG, INFINITE, VR
from core.market_calendar import get_next_trading_day, is_us_trading_day
from core.cloud_sync import (
    is_sync_enabled,
    sync_local_with_drive,
    upload_accounts_to_drive,
    get_sync_config,
    save_sync_config,
    test_connection
)
from core.telegram_notifier import (
    get_telegram_config,
    save_telegram_config,
    send_test_notification,
    notify_order_generation
)
import threading
import time

# -------------------------------------------------------------------
# FastAPI 앱 인스턴스
# -------------------------------------------------------------------
app = FastAPI(
    title="JJ Invest Web Trading Platform",
    description="종종이 3단계 LOC & 무한매수 주식 매매 시스템 (Web Edition)",
    version="1.0.0"
)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 정적 파일 서빙
STATIC_DIR = BASE_DIR / "web" / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

am = AccountManager(filepath=str(ACCOUNTS_JSON))
um = UserManager()

# -------------------------------------------------------------------
# 자동매매 상태 관리 (향후 Oracle 서버 무중단 자동매매용)
# -------------------------------------------------------------------
AUTOTRADE_STATE = {
    "enabled": False,
    "last_run": None,
    "next_run": "미국 장전 (22:30 KST) / 장마감 (05:00 KST)",
    "status": "IDLE (대기중)",
    "logs": [
        {"time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "msg": "오라클 웹 서버 엔진 초기화 완료"}
    ]
}

# -------------------------------------------------------------------
# 유틸리티 함수: NumPy / Pandas 타입의 JSON 직렬화 클리너
# -------------------------------------------------------------------
def sanitize_for_json(val: Any) -> Any:
    """NumPy, Pandas, NaN, Infinity 등을 표준 JSON 직렬화 가능 객체로 변환"""
    if val is None:
        return None
    if isinstance(val, (int, np.integer)):
        return int(val)
    if isinstance(val, (float, np.floating)):
        if math.isnan(val) or math.isinf(val):
            return None
        return round(float(val), 4)
    if isinstance(val, (bool, np.bool_)):
        return bool(val)
    if isinstance(val, (pd.Timestamp, datetime)):
        return val.strftime("%Y-%m-%d %H:%M:%S") if hasattr(val, 'hour') and (val.hour or val.minute) else val.strftime("%Y-%m-%d")
    if isinstance(val, pd.DataFrame):
        return sanitize_for_json(val.to_dict(orient="records"))
    if isinstance(val, pd.Series):
        return sanitize_for_json(val.to_dict())
    if isinstance(val, dict):
        return {str(k): sanitize_for_json(v) for k, v in val.items()}
    if isinstance(val, (list, tuple, np.ndarray, set)):
        return [sanitize_for_json(x) for x in val]
    return val



def get_market_status() -> dict:
    """미국 증시 장 상태(개장/폐장/프리마켓) 및 각국 현재 시각 반환"""
    utc_now = datetime.now(timezone.utc)
    kst_now = utc_now + timedelta(hours=9)
    et_now = utc_now - timedelta(hours=4)  # 미국 동부시간(EDT) 기준 대략 산출

    is_weekend = et_now.weekday() >= 5
    et_hour = et_now.hour + et_now.minute / 60.0

    if is_weekend:
        status = "휴장 (주말)"
        badge = "closed"
    elif 9.5 <= et_hour < 16.0:
        status = "정규장 진행 중"
        badge = "open"
    elif 4.0 <= et_hour < 9.5:
        status = "프리마켓 (장전)"
        badge = "pre"
    elif 16.0 <= et_hour < 20.0:
        status = "애프터마켓 (장후)"
        badge = "after"
    else:
        status = "장 마감"
        badge = "closed"

    return {
        "status": status,
        "badge": badge,
        "kst": kst_now.strftime("%Y-%m-%d %H:%M:%S"),
        "et": et_now.strftime("%Y-%m-%d %H:%M:%S"),
        "utc": utc_now.strftime("%Y-%m-%d %H:%M:%S"),
    }


# -------------------------------------------------------------------
# Pydantic 요청 스키마
# -------------------------------------------------------------------
class CreateAccountRequest(BaseModel):
    name: str = Field(..., example="SOXL 종종이 1호")
    strategy: str = Field(..., example="종종이 기본전략")
    ticker: str = Field(..., example="SOXL")
    start_date: str = Field(..., example="2026-01-02")
    initial_seed: float = Field(..., example=100000.0)
    reserve_ratio: float = Field(default=0.05, example=0.05)
    memo: Optional[str] = Field(default="")

class UpdateAccountRequest(BaseModel):
    name: Optional[str] = None
    reserve_ratio: Optional[float] = None
    memo: Optional[str] = None
    initial_seed: Optional[float] = None

class SettlementRequest(BaseModel):
    close_price: float = Field(..., example=50.25)
    buy_qty: int = Field(default=0)
    buy_price: Optional[float] = None
    sell_qty: int = Field(default=0)
    sell_price: Optional[float] = None
    memo: Optional[str] = ""
    trade_date: Optional[str] = None

class AdjustmentRequest(BaseModel):
    type: str = Field(..., example="DEPOSIT")  # "DEPOSIT" or "WITHDRAW"
    amount: float = Field(..., example=5000.0)
    date: str = Field(..., example="2026-10-10")
    reason: Optional[str] = ""

class BacktestRequest(BaseModel):
    ticker: str = Field(default="SOXL")
    capital: float = Field(default=100000.0)
    start_date: str = Field(default="2023-01-03")
    end_date: str = Field(default="2026-10-09")
    strategies: List[str] = Field(default=["종종이 기본전략", "무한매수법 v4.0", "SOXL 단순보유(B&H)"])
    use_adj_close: bool = Field(default=True)

class RegisterRequest(BaseModel):
    email: str = Field(..., example="user@example.com")
    username: str = Field(..., example="myid")
    password: str = Field(..., example="mypassword")

class LoginRequest(BaseModel):
    username: str = Field(..., example="myid")
    password: str = Field(..., example="mypassword")

class TelegramConfigRequest(BaseModel):
    bot_token: str = Field(default="", example="123456789:ABCdef...")
    chat_id: str = Field(default="", example="123456789")
    enabled: bool = Field(default=True)
    notify_on_orders: bool = Field(default=True)

class TelegramTestRequest(BaseModel):
    bot_token: Optional[str] = None
    chat_id: Optional[str] = None


def get_current_user(request: Request) -> Optional[dict]:
    """요청 헤더(Bearer) 또는 쿼리 파라미터에서 세션 토큰을 검증하여 현재 회원 정보 반환"""
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.replace("Bearer ", "").strip()
    if not token:
        token = request.query_params.get("token", "")
    if not token:
        return None
    return um.get_user_by_token(token)


def is_mobile_user_agent(user_agent: str) -> bool:
    """스마트폰/모바일 디바이스 User-Agent 판별"""
    ua = (user_agent or "").lower()
    mobile_keywords = [
        "mobile", "android", "iphone", "ipod", "blackberry",
        "windows phone", "opera mini", "iemobile", "webos"
    ]
    return any(k in ua for k in mobile_keywords)


# -------------------------------------------------------------------
# HTML 메인 페이지 라우트 (PC 및 모바일 자동 라우팅)
# -------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def serve_index(request: Request):
    """
    메인 페이지 제공:
    - 쿼리 파라미터(?view=mobile 또는 ?view=pc) 또는 쿠키로 명시적 모드 지정 가능
    - 모바일 스마트폰 접속 시 자동으로 최적화된 모바일 전용 버전(mobile.html) 제공
    - 데스크톱 PC 접속 시 풀스크린 데스크톱 버전(index.html) 제공
    """
    view_override = request.query_params.get("view") or request.cookies.get("view_mode")
    ua = request.headers.get("user-agent", "")
    
    is_mobile = False
    if view_override == "mobile":
        is_mobile = True
    elif view_override == "pc":
        is_mobile = False
    else:
        is_mobile = is_mobile_user_agent(ua)

    if is_mobile:
        mobile_file = BASE_DIR / "web" / "templates" / "mobile.html"
        if mobile_file.exists():
            resp = FileResponse(mobile_file)
            if request.query_params.get("view"):
                resp.set_cookie("view_mode", request.query_params.get("view"), max_age=60*60*24*30)
            return resp

    index_file = BASE_DIR / "web" / "templates" / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=404, detail="Frontend index.html not found")
    resp = FileResponse(index_file)
    if request.query_params.get("view"):
        resp.set_cookie("view_mode", request.query_params.get("view"), max_age=60*60*24*30)
    return resp


@app.get("/m", response_class=HTMLResponse)
async def serve_mobile_direct(request: Request):
    """모바일 버전 직접 접속 라우트 (/m)"""
    mobile_file = BASE_DIR / "web" / "templates" / "mobile.html"
    if not mobile_file.exists():
        raise HTTPException(status_code=404, detail="Mobile template not found")
    resp = FileResponse(mobile_file)
    resp.set_cookie("view_mode", "mobile", max_age=60*60*24*30)
    return resp


# -------------------------------------------------------------------
# 사용자 인증 (Auth) API 라우트
# -------------------------------------------------------------------
@app.post("/api/auth/register")
async def register(req: RegisterRequest):
    """신규 회원가입: 이메일, ID, PW만 입력받아 100,000회 PBKDF2 단방향 암호화 보관"""
    try:
        user = um.register_user(email=req.email, username=req.username, password=req.password)
        token = um.create_session(user["username"])
        return {
            "success": True,
            "token": token,
            "user": {
                "username": user["username"],
                "email": user["email"],
                "name": user["name"],
                "role": user.get("role", "user"),
                "role_label": user.get("role_label", "일반회원"),
                "created_at": user["created_at"]
            },
            "message": f"환영합니다! {user['name']}님 회원가입이 완료되었습니다."
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        print(f"[Register Error] {e}")
        raise HTTPException(status_code=500, detail="회원가입 처리 중 오류가 발생했습니다.")


@app.post("/api/auth/login")
async def login(req: LoginRequest):
    """사용자 로그인 처리 (단방향 해시 검증 및 세션 토큰 발급)"""
    user = um.authenticate_user(req.username, req.password)
    if not user:
        raise HTTPException(status_code=401, detail="아이디 또는 비밀번호가 올바르지 않습니다.")

    token = um.create_session(user["username"])
    raw_accounts = am.load_accounts()
    user_accounts = [
        a["id"] for a in raw_accounts 
        if a.get("owner", "huxley").lower() == user["username"].lower()
    ]
    return {
        "success": True,
        "token": token,
        "user": {
            "username": user["username"],
            "email": user.get("email", ""),
            "name": user["name"],
            "role": user.get("role", "admin" if user["username"].lower() == "huxley" else "user"),
            "role_label": user.get("role_label", "관리자" if user["username"].lower() == "huxley" else "일반회원"),
            "linked_accounts": user_accounts,
            "login_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
    }


@app.get("/api/auth/me")
async def check_current_user(request: Request):
    """현재 로그인 세션 검증 및 사용자별 연동 계좌 상태 확인"""
    user = get_current_user(request)
    if not user:
        return {"authenticated": False}

    raw_accounts = am.load_accounts()
    user_accounts = [
        a["id"] for a in raw_accounts 
        if a.get("owner", "huxley").lower() == user["username"].lower()
    ]
    return {
        "authenticated": True,
        "user": {
            "username": user["username"],
            "email": user.get("email", ""),
            "name": user["name"],
            "role": user.get("role", "admin" if user["username"].lower() == "huxley" else "user"),
            "role_label": user.get("role_label", "관리자" if user["username"].lower() == "huxley" else "일반회원"),
            "linked_accounts": user_accounts
        }
    }


@app.post("/api/auth/logout")
async def logout(request: Request):
    """로그아웃 처리 (세션 무효화)"""
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.replace("Bearer ", "").strip()
    if token:
        um.delete_session(token)
    return {"success": True, "message": "성공적으로 로그아웃되었습니다."}


# -------------------------------------------------------------------
# 관리자 전용 회원 관리 API 라우트
# -------------------------------------------------------------------
@app.get("/api/admin/users")
async def admin_list_users(request: Request):
    """전체 회원 목록 조회 (관리자 전용: ID, 이메일, 회원 구분만 반환, PW는 비노출)"""
    curr = get_current_user(request)
    if not curr or curr.get("role") != "admin":
        raise HTTPException(status_code=403, detail="관리자(Admin) 권한이 필요한 기능입니다.")

    users = um.list_users()
    return {
        "success": True,
        "users": users,
        "total_count": len(users)
    }


@app.delete("/api/admin/users/{target_username}")
async def admin_delete_user(target_username: str, request: Request):
    """회원 계정 삭제 (관리자 전용: 본인/최고관리자 삭제 불가, 계좌 데이터 동시 정리)"""
    curr = get_current_user(request)
    if not curr or curr.get("role") != "admin":
        raise HTTPException(status_code=403, detail="관리자(Admin) 권한이 필요한 기능입니다.")

    try:
        um.delete_user(target_username, curr["username"])
        del_acc_count = am.delete_accounts_by_owner(target_username)
        return {
            "success": True,
            "message": f"'{target_username}' 회원이 성공적으로 삭제되었습니다. (연동 계좌 {del_acc_count}개 정리됨)",
            "deleted_username": target_username,
            "deleted_accounts_count": del_acc_count
        }
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"회원 삭제 중 오류가 발생했습니다: {str(e)}")


# -------------------------------------------------------------------
# REST API 라우트
# -------------------------------------------------------------------
@app.get("/api/status")
async def get_server_status():
    """서버 및 증시 상태, 지원 전략 옵션 반환"""
    market = get_market_status()
    return {
        "status": "online",
        "platform": sys.platform,
        "python_version": sys.version.split()[0],
        "market": market,
        "strategy_options": ACCOUNT_STRATEGY_OPTIONS,
        "autotrade": AUTOTRADE_STATE
    }


@app.get("/api/market/quote/{ticker}")
async def get_market_quote(ticker: str):
    """지정 티커의 최신 종가 및 등락 정보 반환"""
    ticker_clean = ticker.strip().upper()
    try:
        now_str = datetime.now().strftime("%Y-%m-%d")
        past_str = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")
        df = fetch_market_data(ticker_clean, past_str, now_str, warmup_days=10)
        if not df.empty:
            last_row = df.iloc[-1]
            prev_row = df.iloc[-2] if len(df) >= 2 else last_row
            close = float(last_row["Close"])
            prev_close = float(prev_row["Close"])
            chg_pct = round(((close / prev_close) - 1.0) * 100, 2) if prev_close > 0 else 0.0
            return {
                "ticker": ticker_clean,
                "date": str(last_row["Date"])[:10],
                "close": round(close, 2),
                "prev_close": round(prev_close, 2),
                "change_pct": chg_pct,
                "cached": True
            }
    except Exception as e:
        print(f"시세 조회 예외: {e}")
    
    return {"ticker": ticker_clean, "close": 0.0, "change_pct": 0.0, "cached": False}


@app.get("/api/accounts")
async def list_accounts(request: Request):
    """현재 로그인한 회원의 계좌 목록 및 포트폴리오 요약 반환 (회원별 독립 격리)"""
    user = get_current_user(request)
    current_username = user["username"].lower() if user else "huxley"

    raw_accounts = am.load_accounts()
    # 현재 로그인한 회원의 계좌만 추출
    user_accounts = [
        acc for acc in raw_accounts 
        if acc.get("owner", "huxley").lower() == current_username
    ]

    processed_list = []
    total_portfolio_asset = 0.0
    total_portfolio_cash = 0.0
    total_portfolio_seed = 0.0

    for acc in user_accounts:
        try:
            details = am.compute_account_details(acc)
            
            # compute_account_details 반환값에서 정밀 데이터 추출
            seed = float(details.get("initial_seed") or acc.get("initial_seed", 0.0))
            asset = float(details.get("current_asset") if details.get("current_asset") is not None else acc.get("total_asset", seed))
            cash = float(details.get("current_cash") if details.get("current_cash") is not None else acc.get("current_cash", seed))
            hold = int(details.get("current_hold") if details.get("current_hold") is not None else acc.get("current_holdings", 0))
            price = float(details.get("current_price") if details.get("current_price") is not None else acc.get("current_price", 0.0))
            profit = float(details.get("total_profit") if details.get("total_profit") is not None else (asset - seed))
            return_pct = float(details.get("total_return_pct") if details.get("total_return_pct") is not None else (((asset / seed - 1.0) * 100) if seed > 0 else 0.0))
            mode = str(details.get("mode") or "Normal")
            pending_sell_count = int(details.get("pending_sell_count", 0))

            buy_orders = details.get("buy_orders", [])
            sell_orders = details.get("sell_orders", [])

            total_portfolio_asset += asset
            total_portfolio_cash += cash
            total_portfolio_seed += seed

            processed_list.append({
                "id": acc["id"],
                "owner": acc.get("owner", current_username),
                "is_my_account": True,
                "name": acc["name"],
                "ticker": acc["ticker"],
                "strategy": acc["strategy"],
                "start_date": acc.get("start_date", ""),
                "current_date": details.get("current_date") or acc.get("current_date", ""),
                "operational_state": details.get("operational_state") or acc.get("operational_state", "WAITING_FOR_FILL"),
                "initial_seed": seed,
                "reserve_ratio": float(acc.get("reserve_ratio", 0.05)),
                "memo": acc.get("memo", ""),
                "total_asset": round(asset, 2),
                "current_cash": round(cash, 2),
                "current_holdings": hold,
                "current_price": round(price, 2),
                "total_profit": round(profit, 2),
                "return_pct": round(return_pct, 2),
                "mode": mode,
                "pending_sell_count": pending_sell_count,
                "records_count": len(acc.get("trade_records", [])),
                "has_orders": bool(buy_orders or sell_orders),
                "buy_orders": buy_orders,
                "sell_orders": sell_orders,
            })
        except Exception as e:
            print(f"계좌 [{acc.get('name')}] 계산 실패: {e}")
            seed = float(acc.get("initial_seed", 0.0))
            processed_list.append({
                "id": acc["id"],
                "owner": acc.get("owner", current_username),
                "is_my_account": True,
                "name": acc["name"],
                "ticker": acc["ticker"],
                "strategy": acc["strategy"],
                "initial_seed": seed,
                "total_asset": seed,
                "current_cash": seed,
                "current_holdings": 0,
                "current_price": 0.0,
                "total_profit": 0.0,
                "return_pct": 0.0,
                "mode": "Normal",
                "operational_state": "WAITING_FOR_FILL",
                "records_count": len(acc.get("trade_records", [])),
            })

    total_portfolio_profit = total_portfolio_asset - total_portfolio_seed
    overall_return_pct = round((total_portfolio_profit / total_portfolio_seed * 100), 2) if total_portfolio_seed > 0 else 0.0

    return {
        "portfolio": {
            "total_asset": round(total_portfolio_asset, 2),
            "total_cash": round(total_portfolio_cash, 2),
            "total_seed": round(total_portfolio_seed, 2),
            "total_profit": round(total_portfolio_profit, 2),
            "return_pct": overall_return_pct,
            "account_count": len(processed_list),
            "owner": current_username
        },
        "accounts": processed_list
    }


@app.get("/api/accounts/{acc_id}")
async def get_account_detail(acc_id: str, request: Request):
    """특정 계좌의 주문표, 미매도 슬롯, 매매일지, 입출금 상세 내역 반환 (회원별 격리)"""
    user = get_current_user(request)
    current_username = user["username"].lower() if user else "huxley"

    accounts = am.load_accounts()
    target = next((a for a in accounts if a["id"] == acc_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="Account not found")

    if target.get("owner", "huxley").lower() != current_username:
        raise HTTPException(status_code=403, detail="본인의 계좌 정보만 열람할 수 있습니다.")

    details = am.compute_account_details(target)
    
    # df_res는 대용량 DataFrame이므로 응답 크기 절약 및 안전한 JSON 직렬화를 위해 제외
    details_clean = {k: v for k, v in details.items() if k != "df_res"}

    buy_orders = details_clean.get("buy_orders", [])
    sell_orders = details_clean.get("sell_orders", [])
    unsold_lots = details_clean.get("unsold_lots", [])
    netting_info = details_clean.get("netting_info", {})

    trade_records = target.get("trade_records", [])
    adjustments = target.get("adjustments", [])

    return sanitize_for_json({
        "account": target,
        "details": details_clean,
        "summary": details_clean,
        "orders": {
            "buy_orders": buy_orders,
            "sell_orders": sell_orders,
            "netting_info": netting_info
        },
        "unsold_lots": unsold_lots,
        "trade_records": trade_records[-100:] if len(trade_records) > 100 else trade_records,
        "adjustments": adjustments
    })


@app.post("/api/accounts")
async def create_account(req: CreateAccountRequest, request: Request):
    """신규 계좌 생성 (현재 로그인한 회원 소유로 등록)"""
    user = get_current_user(request)
    current_username = user["username"].lower() if user else "huxley"

    new_acc = am.add_account(
        name=req.name,
        strategy=req.strategy,
        ticker=req.ticker,
        start_date=req.start_date,
        initial_seed=req.initial_seed,
        memo=req.memo or "",
        reserve_ratio=req.reserve_ratio,
        owner=current_username
    )
    return {"success": True, "account": new_acc}


@app.put("/api/accounts/{acc_id}")
async def update_account(acc_id: str, req: UpdateAccountRequest, request: Request):
    """계좌 설정(명칭, 위기준비금 비율, 메모 등) 수정 (소유자 검증)"""
    user = get_current_user(request)
    current_username = user["username"].lower() if user else "huxley"

    accounts = am.load_accounts()
    target = next((a for a in accounts if a["id"] == acc_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="Account not found")
    if target.get("owner", "huxley").lower() != current_username:
        raise HTTPException(status_code=403, detail="본인의 계좌만 수정할 수 있습니다.")

    updated = am.update_account_settings(
        acc_id=acc_id,
        name=req.name,
        reserve_ratio=req.reserve_ratio,
        memo=req.memo,
        initial_seed=req.initial_seed
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Account not found")
    return {"success": True, "account": updated}


@app.delete("/api/accounts/{acc_id}")
async def delete_account(acc_id: str, request: Request):
    """계좌 삭제 (소유자 검증)"""
    user = get_current_user(request)
    current_username = user["username"].lower() if user else "huxley"

    accounts = am.load_accounts()
    target = next((a for a in accounts if a["id"] == acc_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="Account not found")
    if target.get("owner", "huxley").lower() != current_username:
        raise HTTPException(status_code=403, detail="본인의 계좌만 삭제할 수 있습니다.")

    ok = am.delete_account(acc_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Account not found")
    return {"success": True, "deleted_id": acc_id}


@app.post("/api/accounts/{acc_id}/advance-day")
async def advance_account_day(acc_id: str, request: Request):
    """계좌 운용 날짜를 다음 미국 개장일로 진행 (소유자 검증)"""
    user = get_current_user(request)
    current_username = user["username"].lower() if user else "huxley"

    accounts = am.load_accounts()
    target = next((a for a in accounts if a["id"] == acc_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="Account not found")
    if target.get("owner", "huxley").lower() != current_username:
        raise HTTPException(status_code=403, detail="본인의 계좌만 운용할 수 있습니다.")

    res = am.advance_next_day(acc_id)
    if not res:
        raise HTTPException(status_code=404, detail="Account not found")

    # (예약) 매수/매도 주문표 생성 시 텔레그램 알림 자동 발송
    try:
        details = am.compute_account_details(res)
        notify_order_generation(
            account_name=res.get("name", "투자계좌"),
            ticker=res.get("ticker", "SOXL"),
            trade_date=str(details.get("target_order_date") or res.get("current_date", "")),
            mode=str(details.get("mode", "Normal")),
            buy_orders=details.get("buy_orders", []),
            sell_orders=details.get("sell_orders", []),
            netting_info=details.get("netting_info"),
            total_asset=float(details.get("current_asset", 0.0)),
            cash=float(details.get("current_cash", 0.0))
        )
    except Exception as ex:
        print(f"[Telegram Alert Error] {ex}")

    return {"success": True, "account": res}


@app.post("/api/accounts/{acc_id}/close-settlement")
async def record_close_settlement(acc_id: str, req: SettlementRequest, request: Request):
    """미국 장마감 후 당일 종가 및 체결 수량 입력 정산 (소유자 검증)"""
    user = get_current_user(request)
    current_username = user["username"].lower() if user else "huxley"

    accounts = am.load_accounts()
    target = next((a for a in accounts if a["id"] == acc_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="Account not found")
    if target.get("owner", "huxley").lower() != current_username:
        raise HTTPException(status_code=403, detail="본인의 계좌만 정산할 수 있습니다.")

    res = am.record_daily_close(
        acc_id=acc_id,
        close_price=req.close_price,
        buy_qty=req.buy_qty,
        buy_price=req.buy_price,
        sell_qty=req.sell_qty,
        sell_price=req.sell_price,
        memo=req.memo or "",
        trade_date=req.trade_date
    )
    if not res:
        raise HTTPException(status_code=404, detail="Account not found or settlement failed")
    return {"success": True, "account": res}


@app.post("/api/accounts/{acc_id}/adjustment")
async def add_account_adjustment(acc_id: str, req: AdjustmentRequest, request: Request):
    """계좌 입금 또는 출금 기록 (소유자 검증)"""
    user = get_current_user(request)
    current_username = user["username"].lower() if user else "huxley"

    accounts = am.load_accounts()
    target = next((a for a in accounts if a["id"] == acc_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="Account not found")
    if target.get("owner", "huxley").lower() != current_username:
        raise HTTPException(status_code=403, detail="본인의 계좌만 입출금 기록이 가능합니다.")

    ok = am.add_adjustment(
        acc_id=acc_id,
        adj_type=req.type,
        amount=req.amount,
        date_str=req.date,
        reason=req.reason or ""
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Account not found")
    return {"success": True}


@app.post("/api/accounts/{acc_id}/undo")
async def undo_last_trade(acc_id: str, request: Request):
    """마지막 거래일 기록 취소 (소유자 검증)"""
    user = get_current_user(request)
    current_username = user["username"].lower() if user else "huxley"

    accounts = am.load_accounts()
    target = next((a for a in accounts if a["id"] == acc_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="Account not found")
    if target.get("owner", "huxley").lower() != current_username:
        raise HTTPException(status_code=403, detail="본인의 계좌만 취소(Undo)할 수 있습니다.")

    ok = am.delete_last_trade_record(acc_id)
    if not ok:
        raise HTTPException(status_code=400, detail="Cannot undo last record")
    return {"success": True}


@app.post("/api/backtest/run")
async def run_backtest_simulation(req: BacktestRequest):
    """
    백테스트 실행: 시세 다운로드 → 전략별 시뮬레이션 → 성과 지표 산출 → 차트 시리즈 반환
    """
    ticker_clean = req.ticker.strip().upper()
    try:
        # 시세 데이터 수집 (야후 파이낸스 & 로컬 SQLite 캐시) - 웅덩이 매매법(120일선) 지원을 위해 warmup_days=180 적용
        df_market = fetch_market_data(ticker_clean, req.start_date, req.end_date, warmup_days=180, use_adj_close=req.use_adj_close)
        if df_market.empty:
            raise HTTPException(status_code=400, detail=f"[{ticker_clean}] 기간 내 시세 데이터를 가져올 수 없습니다.")

        # 전략 시뮬레이션 일괄 실행
        strat_results = run_strategies(
            df_market=df_market,
            ticker=ticker_clean,
            capital=req.capital,
            start_date=req.start_date,
            end_date=req.end_date,
            strategy_names=req.strategies
        )

        response_data = {
            "ticker": ticker_clean,
            "capital": req.capital,
            "start_date": req.start_date,
            "end_date": req.end_date,
            "use_adj_close": req.use_adj_close,
            "strategies": []
        }

        for item in strat_results:
            name = item["name"]
            metrics = item["metrics"]
            df_res = item["df"]

            # 차트 시리즈 데이터 생성 (Date, Asset)
            chart_series = build_chart_series(df_res)
            
            # Drawdown (낙폭 MDD 추이) 계산
            cummax = df_res["Asset"].cummax()
            dd_series = ((df_res["Asset"] - cummax) / cummax * 100.0).round(2).tolist()

            response_data["strategies"].append({
                "name": name,
                "metrics": {
                    "initial_capital": float(metrics.get("initial_capital", req.capital)),
                    "final_asset": float(metrics.get("final_asset", 0.0)),
                    "total_return": float(metrics.get("total_return", 0.0)),
                    "cagr": float(metrics.get("cagr", 0.0)),
                    "mdd": float(metrics.get("mdd", 0.0)),
                    "sharpe": float(metrics.get("sharpe", 0.0)),
                    "calmar": float(metrics.get("calmar", 0.0)),
                    "final_cash": float(metrics.get("final_cash", 0.0)),
                    "final_hold": int(metrics.get("final_hold", 0)),
                    "trading_days": int(metrics.get("trading_days", len(df_res))),
                },
                "chart": {
                    "dates": chart_series["dates"],
                    "assets": chart_series["vals"],
                    "drawdowns": dd_series
                }
            })

        return sanitize_for_json(response_data)

    except Exception as e:
        print(f"백테스트 실행 오류: {e}")
        raise HTTPException(status_code=500, detail=f"백테스트 실행 중 오류 발생: {str(e)}")


@app.get("/api/autotrade/status")
async def get_autotrade_status():
    """오라클 서버 자동매매 봇 상태 조회"""
    return sanitize_for_json(AUTOTRADE_STATE)


@app.post("/api/autotrade/toggle")
async def toggle_autotrade():
    """오라클 서버 자동매매 봇 활성화 / 비활성화 토글"""
    AUTOTRADE_STATE["enabled"] = not AUTOTRADE_STATE["enabled"]
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status_str = "활성화 (Active)" if AUTOTRADE_STATE["enabled"] else "비활성화 (Disabled)"
    AUTOTRADE_STATE["status"] = status_str
    AUTOTRADE_STATE["logs"].insert(0, {
        "time": now_str,
        "msg": f"자동매매 상태 변경: {status_str}"
    })
    return sanitize_for_json(AUTOTRADE_STATE)


# -------------------------------------------------------------------
# Google Apps Script (Google Drive) 클라우드 동기화 라우트
# -------------------------------------------------------------------
class SyncConfigRequest(BaseModel):
    url: str
    enabled: bool = True


@app.get("/api/sync/status")
async def get_sync_status():
    """구글 드라이브 클라우드 동기화 상태 반환"""
    cfg = get_sync_config()
    return {
        "enabled": is_sync_enabled(),
        "url": cfg.get("web_app_url", ""),
        "last_sync_time": cfg.get("last_sync_time"),
        "last_sync_status": cfg.get("last_sync_status"),
        "last_sync_message": cfg.get("last_sync_message"),
    }


@app.post("/api/sync/pull")
async def sync_pull_from_drive():
    """구글 드라이브에서 최신 계좌 데이터 수동 다운로드 및 동기화"""
    ok, msg = sync_local_with_drive(am)
    return {"success": ok, "message": msg}


@app.post("/api/sync/push")
async def sync_push_to_drive():
    """로컬 계좌 데이터를 구글 드라이브로 수동 업로드"""
    accounts = am.load_accounts()
    ok, msg = upload_accounts_to_drive(accounts)
    return {"success": ok, "message": msg}


@app.post("/api/sync/test")
async def sync_test_connection(payload: SyncConfigRequest):
    """구글 앱스 스크립트 연결 Ping 테스트"""
    url = payload.url.strip()
    if not url:
        return {"success": False, "message": "Google Apps Script Web App URL을 입력해주세요."}
    ok, msg = test_connection(url)
    return {"success": ok, "message": msg}


@app.post("/api/sync/config")
async def update_sync_config(req: SyncConfigRequest):
    """구글 Apps Script Web App URL 및 활성화 여부 설정"""
    cfg = get_sync_config()
    cfg["web_app_url"] = req.url.strip()
    cfg["sync_enabled"] = req.enabled
    save_sync_config(cfg)
    ok, msg = sync_local_with_drive(am)
    return {"success": ok, "message": msg, "config": cfg}


# -------------------------------------------------------------------
# 텔레그램 봇 알림 설정 & 테스트 API
# -------------------------------------------------------------------
@app.get("/api/telegram/config")
async def get_tg_config():
    """텔레그램 알림 설정 조회"""
    cfg = get_telegram_config()
    token = cfg.get("bot_token", "")
    masked = f"{token[:6]}...{token[-4:]}" if len(token) > 12 else token
    return {
        "enabled": cfg.get("enabled", False),
        "bot_token": token,
        "masked_token": masked,
        "chat_id": cfg.get("chat_id", ""),
        "last_test_time": cfg.get("last_test_time"),
        "last_test_status": cfg.get("last_test_status"),
        "notify_on_orders": cfg.get("notify_on_orders", True)
    }


@app.post("/api/telegram/config")
async def save_tg_config(req: TelegramConfigRequest):
    """텔레그램 봇 토큰 및 챗 ID 저장"""
    cfg = get_telegram_config()
    cfg["bot_token"] = req.bot_token.strip()
    cfg["chat_id"] = req.chat_id.strip()
    cfg["enabled"] = req.enabled
    cfg["notify_on_orders"] = req.notify_on_orders
    save_telegram_config(cfg)
    return {"success": True, "message": "텔레그램 설정이 성공적으로 저장되었습니다."}


@app.post("/api/telegram/test")
async def test_tg_message(req: TelegramTestRequest):
    """텔레그램 연동 테스트 메시지 발송"""
    ok, msg = send_test_notification(bot_token=req.bot_token, chat_id=req.chat_id)
    return {"success": ok, "message": msg}



def background_cloud_sync_worker():
    """5분마다 구글 드라이브와 계좌 자동 양방향 동기화"""
    time.sleep(3)  # 앱 시작 직후 3초 대기
    if is_sync_enabled():
        try:
            print("[CloudSync] 서버 시작 시 구글 드라이브 계좌 자동 동기화 시도...")
            ok, msg = sync_local_with_drive(am)
            print(f"[CloudSync] 시작 동기화 결과: {ok} ({msg})")
        except Exception as e:
            print(f"[CloudSync] 시작 동기화 오류: {e}")

    while True:
        time.sleep(300)  # 5분 주기
        if is_sync_enabled():
            try:
                ok, msg = sync_local_with_drive(am)
                if ok:
                    print(f"[CloudSync Periodic] 자동 동기화 성공: {msg}")
            except Exception as e:
                print(f"[CloudSync Periodic] 주기적 동기화 오류: {e}")


# 백그라운드 동기화 스레드 시작
sync_thread = threading.Thread(target=background_cloud_sync_worker, daemon=True)
sync_thread.start()


# -------------------------------------------------------------------
# 로컬 직접 실행 진입점
# -------------------------------------------------------------------
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
