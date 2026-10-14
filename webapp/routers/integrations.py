"""
외부 연동 라우터: 텔레그램 알림 설정 및 발송 테스트
(구글 드라이브 동기화는 서버 로컬 DB 전용 전환으로 완전 제거됨)
"""
from fastapi import APIRouter

from core.telegram_notifier import (
    get_telegram_config,
    save_telegram_config,
    send_test_notification,
)

from ..schemas import TelegramConfigRequest, TelegramTestRequest

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
