"""
=====================================================================
텔레그램 봇 알림 모듈 (Telegram Notifier)
- (예약) 매수/매도 주문 발생 시 스마트폰 텔레그램 메시지 실시간 전송
- 일일 정산 완료 및 목표 수익 도달 알림
- BotFather 토큰 및 Chat ID 기반 무설치 경량 연동
=====================================================================
"""
import os
import json
from datetime import datetime
from typing import Optional, Dict, Any, Tuple, List
import requests

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DATA_DIR = os.path.join(BASE_DIR, "data")
CONFIG_FILE = os.path.join(DATA_DIR, "telegram_config.json")


def _ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


def get_telegram_config() -> Dict[str, Any]:
    """저장된 텔레그램 연동 설정을 불러옵니다."""
    _ensure_data_dir()
    default_config = {
        "enabled": False,
        "bot_token": "",
        "chat_id": "",
        "last_test_time": None,
        "last_test_status": None,
        "notify_on_orders": True,     # 주문 발생 시 알림
        "notify_on_settlement": True, # 정산 완료 시 알림
    }
    if not os.path.exists(CONFIG_FILE):
        return default_config
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            cfg = json.load(f)
            return {**default_config, **cfg}
    except Exception as e:
        print(f"[Telegram] 설정 파일 로드 오류: {e}")
        return default_config


def save_telegram_config(config: Dict[str, Any]):
    """텔레그램 설정을 파일에 저장합니다."""
    _ensure_data_dir()
    tmp_file = f"{CONFIG_FILE}.tmp"
    with open(tmp_file, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    os.replace(tmp_file, CONFIG_FILE)


def send_telegram_message(
    text: str,
    bot_token: Optional[str] = None,
    chat_id: Optional[str] = None,
    parse_mode: str = "HTML"
) -> Tuple[bool, str]:
    """
    텔레그램 봇 API를 통해 메시지를 전송합니다.
    bot_token, chat_id를 인자로 주지 않으면 저장된 설정을 사용합니다.
    """
    cfg = get_telegram_config()
    token = (bot_token or cfg.get("bot_token", "")).strip()
    cid = (chat_id or cfg.get("chat_id", "")).strip()

    if not token:
        return False, "텔레그램 봇 토큰(Bot Token)이 설정되지 않았습니다."
    if not cid:
        return False, "텔레그램 챗 ID(Chat ID)가 설정되지 않았습니다."

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": cid,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True
    }

    try:
        resp = requests.post(url, json=payload, timeout=10)
        res_data = resp.json()
        if resp.status_code == 200 and res_data.get("ok"):
            return True, "메시지가 성공적으로 전송되었습니다."
        else:
            err_desc = res_data.get("description", f"HTTP {resp.status_code}")
            return False, f"텔레그램 전송 실패: {err_desc}"
    except requests.exceptions.Timeout:
        return False, "텔레그램 서버 응답 시간 초과 (10초)"
    except Exception as ex:
        return False, f"텔레그램 전송 예외 발생: {str(ex)}"


def send_test_notification(bot_token: Optional[str] = None, chat_id: Optional[str] = None) -> Tuple[bool, str]:
    """연동 테스트용 환영 메시지를 발송합니다."""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    msg = (
        "<b>🔔 [JJ Invest] 텔레그램 알림 연동 테스트</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "축하합니다! 오라클 웹 서버와 텔레그램 연동이 정상적으로 완료되었습니다.\n\n"
        f"⏰ <b>테스트 일시</b>: {now_str}\n"
        "🤖 <b>연동 상태</b>: 정상 작동 (Active)\n\n"
        "앞으로 미국 증시 개장 전 <b>(예약) 매수/매도 주문표</b>가 발생하면 "
        "스마트폰 텔레그램으로 자동 안내됩니다."
    )
    ok, res_msg = send_telegram_message(msg, bot_token=bot_token, chat_id=chat_id)
    
    # 설정에 마지막 테스트 결과 기록
    cfg = get_telegram_config()
    cfg["last_test_time"] = now_str
    cfg["last_test_status"] = "SUCCESS" if ok else f"FAILED: {res_msg}"
    save_telegram_config(cfg)

    return ok, res_msg


def notify_order_generation(
    account_name: str,
    ticker: str,
    trade_date: str,
    mode: str,
    buy_orders: List[Dict[str, Any]],
    sell_orders: List[Dict[str, Any]],
    netting_info: Optional[Dict[str, Any]] = None,
    total_asset: Optional[float] = None,
    cash: Optional[float] = None
) -> Tuple[bool, str]:
    """
    (예약) 매수/매도 주문이 생성되었을 때 상세 내역을 텔레그램으로 발송합니다.
    """
    cfg = get_telegram_config()
    if not cfg.get("enabled", False) or not cfg.get("notify_on_orders", True):
        return False, "텔레그램 주문 알림이 비활성화되어 있습니다."

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    mode_icon = "🟢" if mode == "Normal" else ("🟡" if mode == "Safe" else "🔴")

    lines = [
        "<b>🚀 [JJ Invest] 당일 주문표 알림</b>",
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"💼 <b>계좌명</b>: {account_name}",
        f"🎯 <b>종목</b>: <code>{ticker}</code> | <b>적용일</b>: {trade_date}",
        f"🧭 <b>시장모드</b>: {mode_icon} {mode}",
        ""
    ]

    # 매수 주문 목록
    if buy_orders:
        lines.append(f"<b>📥 LOC 매수 주문 ({len(buy_orders)}건)</b>:")
        for idx, o in enumerate(buy_orders, 1):
            p = o.get('price', 0.0)
            q = o.get('qty', 0)
            sub_total = p * q
            lines.append(f"  • {idx}차: <b>${p:,.2f}</b> ({q}주) → ${sub_total:,.2f}")
    else:
        lines.append("📥 매수 주문: 없음")

    lines.append("")

    # 매도 주문 목록
    if sell_orders:
        lines.append(f"<b>📤 익절 매도 주문 ({len(sell_orders)}건)</b>:")
        for idx, o in enumerate(sell_orders, 1):
            p = o.get('price', 0.0)
            q = o.get('qty', 0)
            sub_total = p * q
            lines.append(f"  • {idx}차: <b>${p:,.2f}</b> ({q}주) → ${sub_total:,.2f}")
    else:
        lines.append("📤 매도 주문: 없음")

    # 상계(Netting) 요약이 있는 경우
    if netting_info:
        lines.append("")
        action = netting_info.get('action', '-')
        net_qty = netting_info.get('net_qty', 0)
        lines.append(f"⚖️ <b>주문 상계 요약</b>: {action} {net_qty}주")

    # 계좌 자산 요약
    if total_asset is not None and cash is not None:
        lines.append("")
        lines.append(f"💰 <b>예수금</b>: ${cash:,.2f} | <b>총자산</b>: ${total_asset:,.2f}")

    lines.append("━━━━━━━━━━━━━━━━━━━━━━")
    lines.append(f"⏰ 발송 일시: {now_str}")

    full_text = "\n".join(lines)
    return send_telegram_message(full_text)


def notify_rest_api_call(
    api_title: str,
    method: str,
    endpoint: str,
    status_text: str,
    success: bool,
    details: Optional[Dict[str, Any]] = None,
    error_msg: Optional[str] = None
) -> Tuple[bool, str]:
    """
    Open API Rest API 호출 발생 시 텔레그램으로 즉시 상세 알림을 강제 전송합니다.
    (모든 Open API Rest API 호출 래퍼 연동)
    """
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status_icon = "🟢" if success else "🔴"
    clean_method = (method or "REST").upper().strip()

    lines = [
        f"<b>{status_icon} [Open API 호출] {api_title}</b>",
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"🌐 <b>API 경로</b>: <code>{clean_method} {endpoint}</code>",
        f"📊 <b>호출 상태</b>: {'정상 완료 (SUCCESS)' if success else '오류 발생 (FAILED)'}",
        f"💬 <b>응답 요약</b>: {status_text}"
    ]

    if details:
        lines.append("")
        lines.append("📋 <b>세부 내용</b>:")
        for k, v in details.items():
            if v is not None and str(v).strip() != "":
                lines.append(f"  • {k}: <b>{v}</b>")

    if error_msg and not success:
        lines.append("")
        lines.append(f"⚠️ <b>에러 코드/메시지</b>:\n<code>{error_msg}</code>")

    lines.append("━━━━━━━━━━━━━━━━━━━━━━")
    lines.append(f"⏰ <b>발생 일시</b>: {now_str}")

    full_text = "\n".join(lines)
    return send_telegram_message(full_text)

