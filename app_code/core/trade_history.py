"""
거래내역(슬롯 라이프사이클) 표 계산 모듈 (UI 비의존)

한 행 = 하나의 매수 슬롯. 계좌 상세 화면의 4섹션 표
(거래일자/종가/변동률/모드 , 매수량/목표가 , 매도일/매도가 , 손익금액/손익률/누적손익)
에 표시할 값을 순수 데이터로 계산합니다. 색상 등 표현은 UI에서 결정합니다.
"""
from datetime import datetime
from typing import Dict, List, Optional

from core.strategy_registry import get_target_yield
from strategies.jongjong import round_up


def format_kr_date(date_val) -> str:
    """
    날짜를 한국 요일 표기 형식('MM.DD.(요일)')으로 변환합니다.
    예: '2026-09-28' -> '09.28.(월)'
    """
    if not date_val:
        return "-"
    try:
        s = str(date_val).strip()[:10]
        dt = datetime.strptime(s, "%Y-%m-%d")
        weekdays = ["월", "화", "수", "목", "금", "토", "일"]
        return f"{dt.strftime('%m.%d.')}({weekdays[dt.weekday()]})"
    except Exception:
        return str(date_val)[:10]


def compute_cumulative_profits(records: List[Dict]) -> Dict[int, Optional[float]]:
    """시간순(인덱스 0부터) 누적 실현손익. 매도 완료 행만 값이 있고, 나머지는 None."""
    cum: Dict[int, Optional[float]] = {}
    running = 0.0
    for i, rec in enumerate(records):
        p_val = rec.get('Profit')
        if bool(rec.get('Sold', False)) and p_val is not None:
            try:
                running += float(p_val)
            except Exception:
                pass
            cum[i] = running
        else:
            cum[i] = None
    return cum


def _to_float(val, default: float = 0.0) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def build_trade_rows(records: List[Dict], strategy_name: str, kr_date_fn=format_kr_date) -> List[Dict]:
    """거래기록 리스트를 표 행 데이터로 변환합니다 (최신순 정렬).

    각 행 dict 키:
        idx, date_kr, close, chg (float), chg_str, mode,
        buy_qty, target_price,
        is_sold, is_holding, sell_date_str, sell_price_str,
        profit (float|None), profit_str, profit_rate_str,
        cum_profit (float|None), cum_str
    """
    rows: List[Dict] = []
    if not records:
        return rows

    cum_profits = compute_cumulative_profits(records)
    n = len(records)

    for orig_idx in range(n - 1, -1, -1):
        r = records[orig_idx]
        close = _to_float(r.get('Close', 0.0))

        # 변동률: 값이 없거나(0 이면서 첫 행이 아님) 전일 종가로 재계산
        chg_val = r.get('Chg')
        if chg_val is None or (chg_val == 0.0 and orig_idx > 0):
            prev_close = _to_float(records[orig_idx - 1].get('Close', 0.0)) if orig_idx > 0 else 0.0
            chg_val = (close / prev_close - 1.0) if prev_close > 0 else 0.0
        chg = _to_float(chg_val)
        chg_str = f"{chg * 100:+.2f}%" if (orig_idx > 0 or chg != 0.0) else "-"

        mode = str(r.get('Mode', 'Normal'))

        # 매수 정보
        buy_qty = int(r.get('BuyQty', r.get('R', 0)) or 0)
        target = _to_float(r.get('U')) if r.get('U') is not None else 0.0
        if target == 0.0 and buy_qty > 0:
            target = round_up(close * (1.0 + get_target_yield(strategy_name)), 2)

        # 매도 정보
        is_sold = bool(r.get('Sold', False)) and (r.get('W') is not None)
        sell_price = 0.0
        if is_sold:
            sell_date_str = kr_date_fn(r.get('W'))
            sell_price = _to_float(r.get('X', 0.0))
            sell_price_str = f"${sell_price:.2f}"
        else:
            if buy_qty > 0:
                hold_days = n - 1 - int(r.get('t', orig_idx))
                sell_date_str = f"보유중({hold_days}d)"
            else:
                sell_date_str = "-"
            sell_price_str = "-"

        # 손익 정보
        profit = None
        profit_str = "-"
        profit_rate_str = "-"
        if is_sold and r.get('Profit') is not None:
            profit = _to_float(r.get('Profit'))
            profit_str = f"{profit:+,.0f}$"
            if r.get('ProfitRate') is not None:
                pr = _to_float(r.get('ProfitRate'))
            else:
                bp = _to_float(r.get('BuyPrice', close))
                pr = ((sell_price / bp - 1.0) * 100.0) if (bp > 0 and sell_price > 0) else 0.0
            profit_rate_str = f"{pr:+.1f}%"

        cum = cum_profits.get(orig_idx)
        rows.append({
            'idx': orig_idx,
            'date_kr': kr_date_fn(str(r.get('Date', ''))),
            'close': close,
            'chg': chg,
            'chg_str': chg_str,
            'mode': mode,
            'buy_qty': buy_qty,
            'target_price': target,
            'is_sold': is_sold,
            'is_holding': (not is_sold) and buy_qty > 0,
            'sell_date_str': sell_date_str,
            'sell_price_str': sell_price_str,
            'profit': profit,
            'profit_str': profit_str,
            'profit_rate_str': profit_rate_str,
            'cum_profit': cum,
            'cum_str': f"{cum:+,.0f}$" if cum is not None else "-",
        })
    return rows
