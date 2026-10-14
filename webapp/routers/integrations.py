"""
외부 연동 라우터: 텔레그램 알림 설정 및 발송 테스트
(구글 드라이브 동기화는 서버 로컬 DB 전용 전환으로 완전 제거됨)
"""
from fastapi import APIRouter, HTTPException

from core.telegram_notifier import (
    get_telegram_config,
    save_telegram_config,
    send_test_notification,
)
from core.meritz_client import meritz_client
from ..config import am

from ..schemas import (
    TelegramConfigRequest,
    TelegramTestRequest,
    MeritzConfigRequest,
    MeritzTestRequest,
    MeritzOrderExecuteRequest,
)

router = APIRouter()


# -------------------------------------------------------------------
# 텔레그램 봇 알림 설정 & 테스트
# -------------------------------------------------------------------
@router.get("/api/telegram/config")
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
        "notify_on_orders": cfg.get("notify_on_orders", True),
    }


@router.post("/api/telegram/config")
async def save_tg_config(req: TelegramConfigRequest):
    """텔레그램 봇 토큰 및 챗 ID 저장"""
    cfg = get_telegram_config()
    cfg["bot_token"] = req.bot_token.strip()
    cfg["chat_id"] = req.chat_id.strip()
    cfg["enabled"] = req.enabled
    cfg["notify_on_orders"] = req.notify_on_orders
    save_telegram_config(cfg)
    return {"success": True, "message": "텔레그램 설정이 성공적으로 저장되었습니다."}


@router.post("/api/telegram/test")
async def test_tg_message(req: TelegramTestRequest):
    """텔레그램 연동 테스트 메시지 발송"""
    ok, msg = send_test_notification(bot_token=req.bot_token, chat_id=req.chat_id)
    return {"success": ok, "message": msg}


# -------------------------------------------------------------------
# 메리츠증권 Open API 설정 & 테스트
# -------------------------------------------------------------------
@router.get("/api/meritz/config")
async def get_meritz_config():
    """메리츠증권 API 설정 조회 (보안을 위해 App Key/Secret 마스킹 처리)"""
    cfg = meritz_client.load_config()
    key = cfg.get("app_key", "")
    sec = cfg.get("app_secret", "")
    masked_key = f"{key[:6]}...{key[-4:]}" if len(key) > 10 else ("(미설정)" if not key else "******")
    return {
        "enabled": cfg.get("enabled", False),
        "is_simulation": cfg.get("is_simulation", True),
        "app_key": key,
        "masked_app_key": masked_key,
        "has_secret": bool(sec),
        "account_number": cfg.get("account_number", "")
    }


@router.post("/api/meritz/config")
async def save_meritz_config(req: MeritzConfigRequest):
    """메리츠증권 App Key 및 App Secret 저장"""
    new_cfg = {
        "enabled": req.enabled,
        "is_simulation": req.is_simulation
    }
    if req.app_key.strip():
        new_cfg["app_key"] = req.app_key.strip()
    if req.app_secret.strip():
        new_cfg["app_secret"] = req.app_secret.strip()

    meritz_client.save_config(new_cfg)
    return {"success": True, "message": "메리츠증권 API 설정이 안전하게 저장되었습니다."}


@router.post("/api/meritz/test")
async def test_meritz_connection(req: MeritzTestRequest):
    """메리츠증권 토큰 발급 및 외화 잔고 조회 테스트"""
    if req.app_key and req.app_secret:
        meritz_client.save_config({
            "app_key": req.app_key.strip(),
            "app_secret": req.app_secret.strip()
        })

    if not meritz_client.is_configured():
        return {"success": False, "message": "메리츠 App Key 및 App Secret을 먼저 입력해주세요."}

    # 토큰 발급
    ok, token_or_err = meritz_client.get_access_token(force_refresh=True)
    if not ok:
        return {"success": False, "message": f"토큰 발급 실패: {token_or_err}"}

    # 외화 잔고 조회
    cur_res = meritz_client.get_overseas_currencies()
    usd_dep = cur_res.get("usd_deposit", 0.0)
    usd_ord = cur_res.get("usd_orderable", 0.0)

    return {
        "success": True,
        "token_prefix": f"{token_or_err[:8]}...",
        "usd_deposit": usd_dep,
        "usd_orderable": usd_ord,
        "message": f"메리츠 Open API 연동 성공! (USD 예수금: ${usd_dep:,.2f})"
    }


@router.post("/api/meritz/execute-orders")
async def execute_meritz_orders(req: MeritzOrderExecuteRequest):
    """지정된 계좌의 오늘 LOC 주문표를 메리츠증권으로 전송"""
    acc = next((a for a in am.load_accounts() if a["id"] == req.account_id), None)
    if not acc:
        raise HTTPException(status_code=404, detail="계좌를 찾을 수 없습니다.")

    details = am.compute_account_details(acc)
    buys = details.get("buy_orders") or []
    sells = details.get("sell_orders") or []
    ticker = req.symbol or acc.get("ticker", "SOXL")

    batch_res = meritz_client.execute_jongjong_orders_batch(
        symbol=ticker,
        formatted_buys=buys,
        formatted_sells=sells,
        dry_run=req.dry_run
    )
    return {
        "success": True,
        "results": batch_res,
        "message": f"[{ticker}] 총 {batch_res['total_success']}건 주문 접수 완료 (실패: {batch_res['total_failed']}건)"
    }


