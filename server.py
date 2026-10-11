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

class LoginRequest(BaseModel):
    username: str = Field(..., example="huxley")
    password: str = Field(..., example="lee0320")


# -------------------------------------------------------------------
# HTML 메인 페이지 라우트
# -------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_file = BASE_DIR / "web" / "templates" / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=404, detail="Frontend index.html not found")
    return FileResponse(index_file)


# -------------------------------------------------------------------
# 사용자 인증 (Auth) API 라우트
# -------------------------------------------------------------------
@app.post("/api/auth/login")
async def login(req: LoginRequest):
    """사용자 로그인 처리 (계정: huxley / PW: lee0320) 및 전용 계좌 연동"""
    username = req.username.strip()
    password = req.password.strip()

    if username.lower() == "huxley" and password == "lee0320":
        token = "jj_token_huxley_auth_session_9941"
        accounts = am.load_accounts()
        linked = [a["id"] for a in accounts if a.get("owner") == "huxley" or a["id"] == "acc_20261001203651_7121"]
        return {
            "success": True,
            "token": token,
            "user": {
                "username": "huxley",
                "name": "Huxley",
                "role": "Master Trader",
                "linked_accounts": linked,
                "login_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        }
    raise HTTPException(status_code=401, detail="아이디 또는 비밀번호가 올바르지 않습니다.")


@app.get("/api/auth/me")
async def check_current_user(request: Request):
    """현재 로그인 세션 검증 및 연동 계좌 상태 확인"""
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.replace("Bearer ", "").strip()
    
    if "huxley" in token or token == "jj_token_huxley_auth_session_9941":
        accounts = am.load_accounts()
        linked = [a["id"] for a in accounts if a.get("owner") == "huxley" or a["id"] == "acc_20261001203651_7121"]
        return {
            "authenticated": True,
            "user": {
                "username": "huxley",
                "name": "Huxley",
                "role": "Master Trader",
                "linked_accounts": linked
            }
        }
    return {"authenticated": False}


@app.post("/api/auth/logout")
async def logout():
    """로그아웃 처리"""
    return {"success": True, "message": "성공적으로 로그아웃되었습니다."}


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
async def list_accounts():
    """등록된 계좌 목록 및 종합 포트폴리오 요약 반환"""
    raw_accounts = am.load_accounts()
    processed_list = []

    total_portfolio_asset = 0.0
    total_portfolio_cash = 0.0
    total_portfolio_seed = 0.0

    for acc in raw_accounts:
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
                "owner": acc.get("owner", "huxley"),
                "is_my_account": (acc.get("owner", "huxley") == "huxley"),
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
                "owner": acc.get("owner", "huxley"),
                "is_my_account": (acc.get("owner", "huxley") == "huxley"),
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
            "account_count": len(processed_list)
        },
        "accounts": processed_list
    }


@app.get("/api/accounts/{acc_id}")
async def get_account_detail(acc_id: str):
    """특정 계좌의 주문표, 미매도 슬롯, 매매일지, 입출금 상세 내역 반환"""
    accounts = am.load_accounts()
    target = next((a for a in accounts if a["id"] == acc_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="Account not found")

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
async def create_account(req: CreateAccountRequest):
    """신규 계좌 생성"""
    new_acc = am.add_account(
        name=req.name,
        strategy=req.strategy,
        ticker=req.ticker,
        start_date=req.start_date,
        initial_seed=req.initial_seed,
        memo=req.memo or "",
        reserve_ratio=req.reserve_ratio
    )
    return {"success": True, "account": new_acc}


@app.put("/api/accounts/{acc_id}")
async def update_account(acc_id: str, req: UpdateAccountRequest):
    """계좌 설정(명칭, 위기준비금 비율, 메모 등) 수정"""
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
async def delete_account(acc_id: str):
    """계좌 삭제"""
    ok = am.delete_account(acc_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Account not found")
    return {"success": True, "deleted_id": acc_id}


@app.post("/api/accounts/{acc_id}/advance-day")
async def advance_account_day(acc_id: str):
    """계좌 운용 날짜를 다음 미국 개장일로 진행 (장전 주문대기 모드로 전환)"""
    res = am.advance_next_day(acc_id)
    if not res:
        raise HTTPException(status_code=404, detail="Account not found")
    return {"success": True, "account": res}


@app.post("/api/accounts/{acc_id}/close-settlement")
async def record_close_settlement(acc_id: str, req: SettlementRequest):
    """미국 장마감 후 당일 종가 및 체결 수량 입력 정산"""
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
async def add_account_adjustment(acc_id: str, req: AdjustmentRequest):
    """계좌 입금(DEPOSIT) 또는 출금(WITHDRAW, 세금 등) 기록"""
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
async def undo_last_trade(acc_id: str):
    """마지막 거래일 기록 취소 (Undo)"""
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
        # 시세 데이터 수집 (야후 파이낸스 & 로컬 SQLite 캐시)
        df_market = fetch_market_data(ticker_clean, req.start_date, req.end_date, warmup_days=60)
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


@app.post("/api/sync/config")
async def update_sync_config(req: SyncConfigRequest):
    """구글 Apps Script Web App URL 및 활성화 여부 설정"""
    cfg = get_sync_config()
    cfg["web_app_url"] = req.url.strip()
    cfg["sync_enabled"] = req.enabled
    save_sync_config(cfg)
    ok, msg = sync_local_with_drive(am)
    return {"success": ok, "message": msg, "config": cfg}


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
