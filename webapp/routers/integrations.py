"""
외부 연동 라우터: 구글 드라이브(Apps Script) 동기화, 텔레그램 알림 + 백그라운드 동기화 워커
"""
import threading
import time

from fastapi import APIRouter

from core.cloud_sync import (
    get_sync_config,
    is_sync_enabled,
    save_sync_config,
    sync_local_with_drive,
    test_connection,
    upload_accounts_to_drive,
)
from core.telegram_notifier import (
    get_telegram_config,
    save_telegram_config,
    send_test_notification,
)

from ..config import am
from ..schemas import SyncConfigRequest, TelegramConfigRequest, TelegramTestRequest

router = APIRouter()

SYNC_INTERVAL_SEC = 300  # 5분


# -------------------------------------------------------------------
# Google Apps Script (Google Drive) 클라우드 동기화
# -------------------------------------------------------------------
@router.get("/api/sync/status")
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


@router.post("/api/sync/pull")
async def sync_pull_from_drive():
    """구글 드라이브에서 최신 계좌 데이터 수동 다운로드 및 동기화"""
    ok, msg = sync_local_with_drive(am)
    return {"success": ok, "message": msg}


@router.post("/api/sync/push")
async def sync_push_to_drive():
    """로컬 계좌 데이터를 구글 드라이브로 수동 업로드"""
    ok, msg = upload_accounts_to_drive(am.load_accounts())
    return {"success": ok, "message": msg}


@router.post("/api/sync/test")
async def sync_test_connection(payload: SyncConfigRequest):
    """구글 앱스 스크립트 연결 Ping 테스트"""
    url = payload.url.strip()
    if not url:
        return {"success": False, "message": "Google Apps Script Web App URL을 입력해주세요."}
    ok, msg = test_connection(url)
    return {"success": ok, "message": msg}


@router.post("/api/sync/config")
async def update_sync_config(req: SyncConfigRequest):
    """구글 Apps Script Web App URL 및 활성화 여부 설정"""
    cfg = get_sync_config()
    cfg["web_app_url"] = req.url.strip()
    cfg["sync_enabled"] = req.enabled
    save_sync_config(cfg)
    ok, msg = sync_local_with_drive(am)
    return {"success": ok, "message": msg, "config": cfg}


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
# 백그라운드 동기화 워커
# -------------------------------------------------------------------
def _background_cloud_sync_worker():
    """서버 시작 직후 1회 + 5분마다 구글 드라이브와 계좌 자동 양방향 동기화"""
    time.sleep(3)  # 앱 시작 직후 3초 대기
    if is_sync_enabled():
        try:
            print("[CloudSync] 서버 시작 시 구글 드라이브 계좌 자동 동기화 시도...")
            ok, msg = sync_local_with_drive(am)
            print(f"[CloudSync] 시작 동기화 결과: {ok} ({msg})")
        except Exception as e:
            print(f"[CloudSync] 시작 동기화 오류: {e}")

    while True:
        time.sleep(SYNC_INTERVAL_SEC)
        if not is_sync_enabled():
            continue
        try:
            ok, msg = sync_local_with_drive(am)
            if ok:
                print(f"[CloudSync Periodic] 자동 동기화 성공: {msg}")
        except Exception as e:
            print(f"[CloudSync Periodic] 주기적 동기화 오류: {e}")


def start_background_sync() -> threading.Thread:
    """백그라운드 동기화 데몬 스레드 시작"""
    thread = threading.Thread(target=_background_cloud_sync_worker, daemon=True)
    thread.start()
    return thread
