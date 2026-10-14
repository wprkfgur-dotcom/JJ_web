"""
전략 레지스트리 (Strategy Registry)

전략 이름 문자열 → 전략 종류(kind) 판별, 목표 수익률, 백테스트용 전략 인스턴스 생성을
한 곳에서 관리합니다. UI/계좌 로직에 흩어져 있던 `"종종이" in name` 류의 분기를 대체합니다.

UI 의존성(색상 등)은 포함하지 않습니다.
"""
from typing import Optional

from strategies.jongjong import JongJongStrategy
from strategies.infinite_buying_v4 import InfiniteBuyingV4Strategy
from strategies.vr_v5 import ValueRebalancingV5Strategy
from strategies.buy_and_hold import BuyAndHoldStrategy
from strategies.puddle import PuddleStrategy

# 전략 종류 식별자
JONGJONG = "jongjong"
INFINITE = "infinite"
VR = "vr"
PUDDLE = "puddle"
BNH = "bnh"

# 계좌/백테스트에서 사용하는 표준 표시 이름
DISPLAY_NAMES = {
    JONGJONG: "종종이 기본전략",
    INFINITE: "무한매수법 v4.0",
    VR: "VR 5.0 (밸류리밸런싱)",
    PUDDLE: "웅덩이 매매법",
}

# 계좌 생성 시 선택 가능한 전략 목록 (표시 순서)
ACCOUNT_STRATEGY_OPTIONS = [DISPLAY_NAMES[JONGJONG], DISPLAY_NAMES[INFINITE], DISPLAY_NAMES[VR], DISPLAY_NAMES[PUDDLE]]

# 슬롯 목표가 계산용 기본 목표 수익률
TARGET_YIELD_JONGJONG = 0.0275
TARGET_YIELD_DEFAULT = 0.05


TARGET_YIELDS_JONGJONG = {
    'Normal': 0.0275,
    'Safe': 0.0025,
    'Riskoff': 0.0070
}


def classify_strategy(name: Optional[str]) -> str:
    """전략 이름 문자열로 전략 종류를 판별합니다.

    기존 분기 규칙과 동일한 우선순위를 따릅니다: 종종이 → 무한 → VR → 웅덩이 → 단순보유.
    """
    s = str(name or "")
    if "종종이" in s:
        return JONGJONG
    if "무한" in s:
        return INFINITE
    if "VR" in s.upper():
        return VR
    if "웅덩이" in s or "PUDDLE" in s.upper():
        return PUDDLE
    return BNH


def is_jongjong(name: Optional[str]) -> bool:
    return classify_strategy(name) == JONGJONG


def is_vr(name: Optional[str]) -> bool:
    return classify_strategy(name) == VR


def is_infinite(name: Optional[str]) -> bool:
    return classify_strategy(name) == INFINITE


def is_puddle(name: Optional[str]) -> bool:
    return classify_strategy(name) == PUDDLE


def get_target_yield(name: Optional[str], mode: Optional[str] = None) -> float:
    """슬롯 목표가(U)가 없을 때 사용하는 목표 수익률 (전략 및 종종이 모드 반영)."""
    if is_jongjong(name):
        if mode:
            m_cap = str(mode).capitalize()
            return TARGET_YIELDS_JONGJONG.get(m_cap, TARGET_YIELD_JONGJONG)
        return TARGET_YIELD_JONGJONG
    return TARGET_YIELD_DEFAULT


def bnh_display_name(ticker: str) -> str:
    return f"{ticker} 단순보유(B&H)"


def create_backtest_strategy(name: str, ticker: str, capital: float, jongjong_params: Optional[dict] = None):
    """백테스트용 전략 인스턴스를 생성합니다 (종종이 맞춤 파라미터 지원)."""
    kind = classify_strategy(name)
    if kind == JONGJONG:
        if jongjong_params:
            try:
                reserve_ratio = float(jongjong_params.get("reserve_ratio", 0.05))
                fee_rate = float(jongjong_params.get("fee_rate", 0.0005))
                max_hold_days = int(jongjong_params.get("max_hold_days", 10))
                div_rounds = jongjong_params.get("div_rounds") or {
                    'Normal': float(jongjong_params.get("normal_splits", 8.0)),
                    'Safe': float(jongjong_params.get("safe_splits", 7.0)),
                    'Riskoff': float(jongjong_params.get("riskoff_splits", 5.0)),
                }
                target_yields = jongjong_params.get("target_yields") or {
                    'Normal': float(jongjong_params.get("normal_target_yield", 0.0275)),
                    'Safe': float(jongjong_params.get("safe_target_yield", 0.0025)),
                    'Riskoff': float(jongjong_params.get("riskoff_target_yield", 0.0070)),
                }
                return JongJongStrategy(
                    initial_capital=capital,
                    reserve_ratio=reserve_ratio,
                    fee_rate=fee_rate,
                    max_hold_days=max_hold_days,
                    div_rounds=div_rounds,
                    target_yields=target_yields,
                    name=name if "종종이" in name else "종종이 전략",
                )
            except Exception as e:
                print(f"[create_backtest_strategy] Error configuring JongJongStrategy: {e}")
        return JongJongStrategy(initial_capital=capital, reserve_ratio=0.05, name="종종이 기본전략")
    if kind == INFINITE:
        return InfiniteBuyingV4Strategy(ticker=ticker, initial_capital=capital, divisions=40)
    if kind == VR:
        return ValueRebalancingV5Strategy(ticker=ticker, initial_capital=capital, g_value=10.0, band_pct=0.15)
    if kind == PUDDLE:
        return PuddleStrategy(name="웅덩이 매매법", ticker=ticker, initial_capital=capital)
    return BuyAndHoldStrategy(name=bnh_display_name(ticker), initial_capital=capital)
