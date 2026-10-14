"""
=====================================================================
라오어 밸류리밸런싱 (Value Rebalancing) VR 5.0 전략 모듈
=====================================================================
공식 방법론 문서 완벽 반영:
1. 핵심 개념:
   - V (Value): 목표 평가액 가이드라인. 2주(10영업일)마다 갱신되는 가치 곡선.
   - Pool: 보유 현금 (주식 매수를 위한 예수금).
   - G (Gradient): V의 상승 기울기 결정 인자 (분모, 기본 G=10.0, 인출식 G=20.0).
   - 최소/최대 밴드: V * 0.85 ~ V * 1.15 (±15% 기본, 옵션으로 ±10%, ±5% 가능).
   - 사이클: 2주(10거래일)에 1회 결산 및 V 갱신.

2. V 갱신 공식 (매 2주 결산 시점):
   V_next = V + (Pool / G) ± (적립금 or 인출금)
   - 적립식: + 적립금 (Pool 사용 한도: 75%)
   - 거치식: 0 (Pool 사용 한도: 50%)
   - 인출식: - 인출금 (Pool 사용 한도: 25%)

3. 2주치 예약 주문표 (기간예약 주문):
   - 하단 밴드 V_min = V * (1 - band_pct)
   - 상단 밴드 V_max = V * (1 + band_pct)
   - 매수점: P_buy(n) = V_min / n (현재 보유수량 n에서 1주씩 추가 매수할 때의 가격)
     -> 누적 매수금액이 usable_pool (Pool * 사용한도)에 도달할 때까지 산출
   - 매도점: P_sell(n) = V_max / n (현재 보유수량 n에서 1주씩 매도할 때의 가격)
=====================================================================
"""
from typing import List, Dict, Any, Tuple
import pandas as pd
from .base import BaseStrategy


class ValueRebalancingV5Strategy(BaseStrategy):
    """
    라오어 밸류리밸런싱 VR 5.0 전략 클래스
    """

    def __init__(self,
                 ticker: str = 'TQQQ',
                 initial_capital: float = 200000.0,
                 g_value: float = 10.0,
                 band_pct: float = 0.15,
                 pool_usage_limit: float = 0.50,
                 vr_type: str = '거치식',             # '거치식', '적립식', '인출식'
                 deposit_per_cycle: float = 0.0,       # 사이클당 적립/인출액 ($)
                 initial_pool_ratio: float = 0.15,     # 초기 현금(Pool) 비중 (기본 15%, 85% 주식 매수)
                 cycle_trading_days: int = 10,         # 2주 = 10 영업일
                 fee_rate: float = 0.0005,
                 sec_fee: float = 0.0000278,
                 name: str = "VR 5.0 (밸류리밸런싱)"):
        super().__init__(name=name, initial_capital=initial_capital,
                         fee_rate=fee_rate, sec_fee=sec_fee)
        self.ticker = str(ticker).upper()
        self.g_value = float(g_value) if float(g_value) > 0 else 10.0
        self.band_pct = float(band_pct)
        self.vr_type = str(vr_type).strip()
        self.deposit_per_cycle = float(deposit_per_cycle)
        self.initial_pool_ratio = float(initial_pool_ratio)
        self.cycle_trading_days = int(cycle_trading_days)

        # 유형별 기본 Pool 사용 한도 적용
        if pool_usage_limit is not None and pool_usage_limit > 0:
            self.pool_usage_limit = float(pool_usage_limit)
        else:
            if '적립' in self.vr_type:
                self.pool_usage_limit = 0.75
            elif '인출' in self.vr_type:
                self.pool_usage_limit = 0.25
            else:
                self.pool_usage_limit = 0.50

    def calculate_order_ladder(
        self,
        v_val: float,
        current_hold: int,
        pool_cash: float,
        pool_usage_limit: float = None,
        current_price: float = None,
        max_orders: int = 15
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        현재 V값, 보유 수량, 현금 풀을 바탕으로 2주 동안 유효한 매수/매도 예약 주문표를 산출합니다.
        동일한 센트(가격)는 묶어서 수량을 합산하며, 사용자가 보기 쉽도록 호가대별로 정렬합니다.
        """
        limit_ratio = pool_usage_limit if pool_usage_limit is not None else self.pool_usage_limit
        usable_pool = max(0.0, float(pool_cash) * limit_ratio)
        v_min = v_val * (1.0 - self.band_pct)
        v_max = v_val * (1.0 + self.band_pct)

        # 1. 매수 주문표 (P_buy = V_min / n)
        buy_orders_dict: Dict[float, int] = {}
        accum_cost = 0.0
        if current_hold <= 0 and current_price and current_price > 0:
            n_shares = max(1, int(v_min / current_price))
        else:
            n_shares = max(1, current_hold)

        # 최대 500주 또는 usable_pool 소진까지 순차적 가격대 산출
        for _ in range(500):
            p_buy = round(v_min / n_shares, 2)
            if p_buy <= 0.01:
                break
            if accum_cost + p_buy > usable_pool:
                break
            buy_orders_dict[p_buy] = buy_orders_dict.get(p_buy, 0) + 1
            accum_cost += p_buy
            n_shares += 1

        formatted_buys = []
        accum_b_qty = 0
        sorted_buy_prices = sorted(buy_orders_dict.keys(), reverse=True)
        for idx, p in enumerate(sorted_buy_prices):
            q = buy_orders_dict[p]
            accum_b_qty += q
            amt = p * q
            formatted_buys.append({
                '호가단계': f"{idx+1}차 매수예약",
                '주문유형': '기간예약 매수',
                '주문단가': f"${p:.2f}",
                '주문수량': f"{q:,}주",
                '누적수량': f"{accum_b_qty:,}주",
                '예상금액': f"${amt:,.2f}",
                '체결조건': f"주가 ≤ ${p:.2f} (하단 밴드 진입)",
                '비고': f"VR 5.0 하단 매수 (사용 Pool: ${amt:,.2f})",
                'price': p,
                'qty': q
            })

        # 2. 매도 주문표 (P_sell = V_max / n)
        sell_orders_dict: Dict[float, int] = {}
        n_sell = current_hold
        for _ in range(min(current_hold, 500)):
            if n_sell <= 0:
                break
            p_sell = round(v_max / n_sell, 2)
            sell_orders_dict[p_sell] = sell_orders_dict.get(p_sell, 0) + 1
            n_sell -= 1

        formatted_sells = []
        accum_s_qty = 0
        sorted_sell_prices = sorted(sell_orders_dict.keys())
        for idx, p in enumerate(sorted_sell_prices):
            q = sell_orders_dict[p]
            accum_s_qty += q
            amt = p * q
            formatted_sells.append({
                '구분': f"{idx+1}차 매도예약",
                '주문유형': '기간예약 매도',
                '주문단가': f"${p:.2f}",
                '주문수량': f"{q:,}주",
                '누적수량': f"{accum_s_qty:,}주",
                '예상금액': f"${amt:,.2f}",
                '체결조건': f"주가 ≥ ${p:.2f} (상단 밴드 돌파)",
                '비고': f"VR 5.0 상단 익절 (Pool 회수: +${amt:,.2f})",
                'price': p,
                'qty': q
            })

        # 너무 많을 경우 사용자 인터페이스를 위해 가장 체결 가능성 높은 상위 max_orders건 제한
        if len(formatted_buys) > max_orders:
            formatted_buys = formatted_buys[:max_orders]
        if len(formatted_sells) > max_orders:
            formatted_sells = formatted_sells[:max_orders]

        return formatted_buys, formatted_sells

    def run(self, df_data: pd.DataFrame, start_date: str, end_date: str) -> pd.DataFrame:
        """
        주어진 기간 동안 VR 5.0 2주 사이클 매매 시뮬레이션을 수행하고 일별 결과 데이터프레임을 반환합니다.
        """
        df_period = df_data[(df_data['Date'] >= pd.Timestamp(start_date)) &
                            (df_data['Date'] <= pd.Timestamp(end_date))].copy().reset_index(drop=True)

        if len(df_period) == 0:
            raise ValueError(f"지정한 기간({start_date} ~ {end_date})에 '{self.ticker}' 거래 데이터가 없습니다.")

        # 초기 자산 배분 (초기 주식 매수 + 현금 풀 격리)
        p0 = float(df_period.loc[0, 'Close'])
        stock_seed = self.initial_capital * (1.0 - self.initial_pool_ratio)
        effective_buy_p = p0 * (1.0 + self.fee_rate)
        hold = int(stock_seed / effective_buy_p) if effective_buy_p > 0 else 0
        used_cash = hold * effective_buy_p
        cash = max(0.0, self.initial_capital - used_cash)

        # 초기 V 설정: 초기 주식 평가금 기준
        v_val = hold * p0 if hold > 0 else self.initial_capital * (1.0 - self.initial_pool_ratio)

        records = []
        cycle_len = self.cycle_trading_days

        # 2주치 예약 주문 버퍼
        active_buys: List[Dict[str, Any]] = []
        active_sells: List[Dict[str, Any]] = []

        dates = df_period['Date'].values
        closes = df_period['Close'].values
        highs = df_period['High'].values if 'High' in df_period.columns else closes
        lows = df_period['Low'].values if 'Low' in df_period.columns else closes

        cycle_count = 0

        for i in range(len(df_period)):
            d = dates[i]
            close_p = float(closes[i])
            high_p = float(highs[i])
            low_p = float(lows[i])

            # -------------------------------------------------------------
            # [A] 2주(10거래일) 사이클 시작: V 갱신 & 예약 주문표 재계산
            # -------------------------------------------------------------
            if i % cycle_len == 0:
                cycle_count += 1
                if i > 0:
                    # 이전 사이클 종료 후 정산 및 V 업데이트
                    cash_before = cash
                    if '적립' in self.vr_type:
                        cash += self.deposit_per_cycle
                        v_val = v_val + (cash_before / self.g_value) + self.deposit_per_cycle
                    elif '인출' in self.vr_type:
                        cash = max(0.0, cash - self.deposit_per_cycle)
                        v_val = max(0.0, v_val + (cash_before / self.g_value) - self.deposit_per_cycle)
                    else:  # 거치식
                        v_val = v_val + (cash_before / self.g_value)

                # 2주치 예약 주문 산출
                raw_buys, raw_sells = self.calculate_order_ladder(
                    v_val=v_val,
                    current_hold=hold,
                    pool_cash=cash,
                    pool_usage_limit=self.pool_usage_limit,
                    max_orders=200
                )
                # 시뮬레이션용 active 주문으로 복사
                active_buys = [{'price': b['price'], 'qty': b['qty'], 'filled': False} for b in raw_buys]
                active_sells = [{'price': s['price'], 'qty': s['qty'], 'filled': False} for s in raw_sells]

            # -------------------------------------------------------------
            # [B] 일일 장중 체결 시뮬레이션 (2주 기간예약 주문)
            # -------------------------------------------------------------
            day_profit = 0.0

            # 1. 매도 체결 검사 (당일 고가가 매도가 이상 도달 시)
            for s in active_sells:
                if not s['filled'] and high_p >= s['price'] - 1e-4 and hold > 0:
                    q_to_sell = min(hold, s['qty'])
                    if q_to_sell > 0:
                        proceeds = q_to_sell * s['price'] * (1.0 - self.fee_rate - self.sec_fee)
                        cash += proceeds
                        hold -= q_to_sell
                        s['filled'] = True

            # 2. 매수 체결 검사 (당일 저가가 매수가 이하 도달 시)
            for b in active_buys:
                if not b['filled'] and low_p <= b['price'] + 1e-4:
                    cost_per_share = b['price'] * (1.0 + self.fee_rate)
                    max_buyable = int(cash / cost_per_share) if cost_per_share > 0 else 0
                    q_to_buy = min(b['qty'], max_buyable)
                    if q_to_buy > 0:
                        total_cost = q_to_buy * cost_per_share
                        cash -= total_cost
                        hold += q_to_buy
                        s_filled = (q_to_buy == b['qty'])
                        b['filled'] = s_filled

            gross_equity = hold * close_p
            asset = cash + gross_equity
            v_min = v_val * (1.0 - self.band_pct)
            v_max = v_val * (1.0 + self.band_pct)

            records.append({
                'Date': d,
                'Close': close_p,
                'Cash': cash,
                'Hold': hold,
                'Asset': asset,
                'V': v_val,
                'V_min': v_min,
                'V_max': v_max,
                'Pool': cash,
                'Cycle': cycle_count,
                'DayInCycle': (i % cycle_len) + 1,
                'Profit': day_profit
            })

        df_res = pd.DataFrame(records)
        df_res['DD'] = self.compute_drawdown(df_res['Asset'], self.initial_capital)
        return df_res
