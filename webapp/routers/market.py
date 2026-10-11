"""
서버/증시 상태, 시세 조회, 자동매매 봇 라우터
"""
import sys
from datetime import datetime, timedelta

from fastapi import APIRouter

from core.data import fetch_market_data
from core.strategy_registry import ACCOUNT_STRATEGY_OPTIONS

from ..state import AUTOTRADE_STATE
from ..utils import get_market_status, sanitize_for_json

router = APIRouter()


@router.get("/api/status")
async def get_server_status():
    """서버 및 증시 상태, 지원 전략 옵션 반환"""
    return {
        "status": "online",
        "platform": sys.platform,
        "python_version": sys.version.split()[0],
        "market": get_market_status(),
        "strategy_options": ACCOUNT_STRATEGY_OPTIONS,
        "autotrade": AUTOTRADE_STATE,
    }


@router.get("/api/market/quote/{ticker}")
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
                "cached": True,
            }
    except Exception as e:
        print(f"시세 조회 예외: {e}")

    return {"ticker": ticker_clean, "close": 0.0, "change_pct": 0.0, "cached": False}


@router.get("/api/autotrade/status")
async def get_autotrade_status():
    """오라클 서버 자동매매 봇 상태 조회"""
    return sanitize_for_json(AUTOTRADE_STATE)


@router.post("/api/autotrade/toggle")
async def toggle_autotrade():
    """오라클 서버 자동매매 봇 활성화 / 비활성화 토글"""
    AUTOTRADE_STATE["enabled"] = not AUTOTRADE_STATE["enabled"]
    status_str = "활성화 (Active)" if AUTOTRADE_STATE["enabled"] else "비활성화 (Disabled)"
    AUTOTRADE_STATE["status"] = status_str
    AUTOTRADE_STATE["logs"].insert(0, {
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "msg": f"자동매매 상태 변경: {status_str}",
    })
    return sanitize_for_json(AUTOTRADE_STATE)
