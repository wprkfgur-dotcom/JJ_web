"""??? ? ?? ?? (????, ???, ?? ???, ?? ??, ?? ?? ??)."""
import sys
import subprocess
import re
from datetime import datetime, timedelta, timezone
import pandas as pd
import flet as ft

from mobile.theme import LOSS_RED, PROFIT_GREEN
from core.strategy_registry import get_target_yield


def copy_text_to_clipboard(page: ft.Page, text: str):
    """
    Windows 및 모바일(Android) 환경 모두에서 안전하게 클립보드에 텍스트를 복사합니다.
    """
    try:
        cb = ft.Clipboard()
        if hasattr(page, "services") and cb not in page.services:
            page.services.append(cb)
            page.update()
        if hasattr(page, "run_task"):
            page.run_task(cb.set, text)
        else:
            cb.set(text)
    except Exception as e:
        print(f"Clipboard copy error: {e}")

    if sys.platform == "win32":
        try:
            subprocess.run(["clip.exe"], input=text.encode("utf-16"), check=True)
        except Exception:
            pass



def show_toast(page: ft.Page, message: str, is_error: bool = False):
    """
    모바일 플로팅 토스트 알림을 표시합니다.
    """
    sb = ft.SnackBar(
        content=ft.Row(
            controls=[
                ft.Icon(
                    ft.Icons.ERROR_OUTLINE if is_error else ft.Icons.CHECK_CIRCLE_OUTLINE,
                    color=ft.Colors.WHITE,
                    size=20
                ),
                ft.Text(message, color=ft.Colors.WHITE, size=13, weight=ft.FontWeight.W_500, expand=True),
            ],
            spacing=8
        ),
        bgcolor=LOSS_RED if is_error else PROFIT_GREEN,
        open=True,
        duration=2500,
        behavior=ft.SnackBarBehavior.FLOATING,
        margin=ft.Margin.all(12)
    )
    page.overlay.append(sb)
    page.update()


def make_bug_report_mailto() -> str:
    """
    버그 리포트 전송을 위한 mailto URL을 생성합니다.
    수신인: wprkfgur@hotmail.com
    발신인: 기기 기본 이메일 계정
    본문: 발생 상황과 증상을 작성할 수 있는 템플릿 미리 완성
    """
    import urllib.parse
    recipient = "wprkfgur@hotmail.com"
    subject = "[종종이 투자앱] 버그 리포트 및 피드백"
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M')
    body = f"""[버그 리포트 / 문의 사항]

1. 발생 일시: {now_str}
2. 발생 화면 / 기능: (예: 계좌 상세 일일 정산 / 백테스트 / 계좌 생성 등)
3. 대상 종목 및 계좌명: 
4. 문제 상황 및 구체적인 증상:
(어떤 동작을 했을 때 어떤 오류나 이상 현상이 발생했는지 자유롭게 적어주세요)

------------------------------------
* 소중한 의견 감사합니다. 확인 후 신속히 반영하겠습니다."""

    query = urllib.parse.urlencode({
        'subject': subject,
        'body': body
    }, quote_via=urllib.parse.quote)
    return f"mailto:{recipient}?{query}"


def parse_picked_date_str(val, e_data=None) -> str:
    """
    Flutter/Flet DatePicker에서 반환되는 DateTime 객체 또는 ISO 문자열을
    한국 표준시(KST) 및 시스템 로컬 시간대 기준 YYYY-MM-DD 형식으로 안전하고 정확하게 변환합니다.
    (Flutter DatePicker가 로컬 자정을 UTC로 직렬화하여 전송할 때 하루 전날로 밀리는 현상을 완벽 방지)
    """
    if not val and not e_data:
        return ""
    dt = None
    if isinstance(val, (datetime, pd.Timestamp)):
        dt = val
    elif e_data:
        try:
            dt = datetime.fromisoformat(str(e_data).replace("Z", "+00:00"))
        except Exception:
            pass
    if dt is None:
        try:
            dt = datetime.fromisoformat(str(val).replace("Z", "+00:00"))
        except Exception:
            pass
    if dt is None:
        return str(val or e_data)[:10]

    if dt.tzinfo is not None:
        local_dt = dt.astimezone()
    else:
        local_dt = dt

    # 안드로이드/임베디드 환경이 시스템 로컬 타임존을 못 읽어 UTC로 남아있거나
    # 자정이 UTC 변환되어 오후/저녁(12~23시)으로 넘어온 경우 한국 표준시(KST, UTC+9) 보정
    if local_dt.hour >= 12:
        kst = timezone(timedelta(hours=9))
        if dt.tzinfo is not None:
            local_dt = dt.astimezone(kst)
        else:
            local_dt = (dt + timedelta(hours=12)).replace(hour=0, minute=0, second=0)

    return local_dt.strftime("%Y-%m-%d")


def compute_suggested_trades(
    close_p: float,
    buy_orders: list,
    sell_orders: list,
    unsold_lots: list = None,
    strategy_name: str = "",
    netting_info: dict = None
):
    """
    종가(close_p)를 기준으로 LOC 매수 및 매도 체결 수량을 산출합니다.
    - 매도:
      미매도 슬롯(unsold_lots)이 전달된 경우:
      1) 보유일수 >= 10영업일 (10일 만기 MOC 슬롯): 무조건 매도 체결
      2) 목표가 도달: 종가 >= 개별 슬롯 목표가(U) - 1e-4 인 모든 슬롯 전량 매도
      (퉁치기 슬롯을 포함하여 종가가 목표가 이상이 된 모든 슬롯이 자동 매도 체결됨)
      슬롯 정보가 없을 때는 기존 sell_orders 목록의 종가 >= 주문단가 수량 합산.
    - 매수:
      1) LOC 매수 주문 중 종가 <= 주문단가인 주문들의 수량 합산
      2) 퉁치기 슬롯(최저 목표가 슬롯)이 매도 체결되었으나 LOC 매수 주문이 0주인 경우:
         퉁치기 상계 원리에 따라 1회분 상계 매수 수량을 기본 제안
    """
    calc_buy_q = 0
    calc_sell_q = 0

    target_reached_lots = []
    min_u_lot = None

    if unsold_lots:
        for lot in unsold_lots:
            # R 수량 확인
            rq = lot.get('R')
            if rq is None:
                continue
            try:
                rq = int(rq)
            except Exception:
                continue
            if rq <= 0 or bool(lot.get('Sold', False)):
                continue

            # 목표가 U 확인
            u_val = lot.get('U')
            if u_val is None or pd.isna(u_val):
                bp = float(lot.get('BuyPrice', lot.get('Close', close_p)))
                t_yield = get_target_yield(strategy_name)
                u_val = bp * (1.0 + t_yield)
            else:
                u_val = float(u_val)

            # 보유 일수 확인
            h_days = int(lot.get('hold_days', 0))

            is_moc = (h_days >= 10)
            is_target_reached = (close_p >= u_val - 1e-4)

            if is_moc or is_target_reached:
                calc_sell_q += rq
                target_reached_lots.append(lot)

        valid_lots = [l for l in unsold_lots if int(l.get('R', 0)) > 0 and not bool(l.get('Sold', False))]
        if valid_lots:
            def _get_u(x):
                val = x.get('U')
                return float(val) if (val is not None and not pd.isna(val)) else 999999.0
            min_u_lot = min(valid_lots, key=_get_u)
    else:
        for s in sell_orders:
            sp = s.get('price')
            if sp is None:
                raw_p = str(s.get('주문단가', '0')).replace('$', '').replace(',', '').strip()
                sp = float(raw_p) if raw_p else 0.0
            sq = s.get('qty')
            if sq is None:
                raw_q = str(s.get('주문수량', '0')).replace('주', '').replace(',', '').strip()
                sq = int(raw_q) if raw_q else 0
            if sp > 0 and sq > 0 and close_p >= sp - 1e-4:
                calc_sell_q += sq

    for b in buy_orders:
        bp = b.get('price')
        if bp is None:
            raw_p = str(b.get('주문단가', '0')).replace('$', '').replace(',', '').strip()
            bp = float(raw_p) if raw_p else 0.0
        bq = b.get('qty')
        if bq is None:
            raw_q = str(b.get('주문수량', '0')).replace('주', '').replace(',', '').strip()
            bq = int(raw_q) if raw_q else 0
        if bp > 0 and bq > 0 and close_p <= bp + 1e-4:
            calc_buy_q += bq

    # 퉁치기 슬롯이 익절 체결되었는데 당일 LOC 매수 체결이 0주인 경우:
    # 퉁치기 상계 순매수 수량을 기본 제안 수량으로 자동 설정
    if calc_buy_q == 0 and min_u_lot is not None and min_u_lot in target_reached_lots:
        tung_q = int(min_u_lot.get('R', 0))
        if tung_q > 0:
            calc_buy_q = tung_q

    return calc_buy_q, calc_sell_q


def extract_pct_str(order: dict, ref_price: float) -> str:
    """
    주문 정보에서 가격 변동률 문자열(예: (-17.0%), (+2.7%))을 추출하거나 계산합니다.
    """
    for key in ['체결조건', '비고', '호가단계', '구분']:
        val = str(order.get(key, ''))
        m = re.search(r'\(([+-]?\d+\.?\d*%)\)', val)
        if m:
            return m.group(0)

    op = order.get('price')
    if op is None:
        try:
            op = float(str(order.get('주문단가', '0')).replace('$', '').replace(',', '').strip())
        except Exception:
            op = 0.0
    if op > 0 and ref_price > 0:
        diff = (op - ref_price) / ref_price * 100.0
        return f"({diff:+.1f}%)"
    return ""


# format_kr_date 는 core.trade_history 로 이관되었습니다 (하위 호환용 재노출)
from core.trade_history import format_kr_date

__all__ = ["format_kr_date"]

