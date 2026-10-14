"""
웅덩이 매매법 (Puddle Trading Strategy) 모듈
주가가 하락 후 바닥(웅덩이)을 형성할 때, 이동평균선(20/60/120일)과 RSI 지표를 활용해
단계적으로 분할 매수하여 평단가를 낮추고 장기 복리 효과를 극대화하는 전략입니다.

주요 매수 단계:
- 1차 매수: 20일선 터치 시, 당시 보유 현금의 10%를 2회 분할 매수
- 2차 매수: 60일선 터치 시, 당시 보유 현금의 50%를 5일 균등 분할 매수
- 3차 매수: 120일선 터치 시, 당시 보유 현금의 50%를 5일 균등 분할 매수
- 4차 매수: 120일선 터치 + RSI 35 이하 시, 남은 현금 100%를 5일 균등 분할 매수 (올인)
"""
import numpy as np
import pandas as pd
from .base import BaseStrategy


class PuddleStrategy(BaseStrategy):
    """
    이동평균선(20, 60, 120일)과 RSI(14)를 활용한 4단계 웅덩이 분할 매수 전략.
    """

    def __init__(self, ticker: str = "QLD", initial_capital: float = 200000.0,
                 fee_rate: float = 0.0005, sec_fee: float = 0.0000278,
                 name: str = "웅덩이 매매법"):
        super().__init__(name=name, initial_capital=initial_capital,
                         fee_rate=fee_rate, sec_fee=sec_fee)
        self.ticker = ticker

    def run(self, df_data: pd.DataFrame, start_date: str, end_date: str) -> pd.DataFrame:
        df = df_data.copy().sort_values('Date').reset_index(drop=True)

        if len(df) == 0:
            raise ValueError(f"지정한 기간({start_date} ~ {end_date})에 시세 데이터가 없습니다.")

        # 1. 기술적 지표 계산 (전체 데이터 기반, warmup 기간 활용)
        df['MA20'] = df['Close'].rolling(window=20).mean()
        df['MA60'] = df['Close'].rolling(window=60).mean()
        df['MA120'] = df['Close'].rolling(window=120).mean()

        # RSI 14 (Wilder's Exponential Moving Average Smoothing)
        delta = df['Close'].diff()
        gain = delta.where(delta > 0, 0.0)
        loss = -delta.where(delta < 0, 0.0)
        avg_gain = gain.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        df['RSI'] = (100 - (100 / (1 + rs))).fillna(50.0)

        # 2. 백테스트 분석 기간 슬라이싱
        df_period = df[(df['Date'] >= pd.Timestamp(start_date)) &
                       (df['Date'] <= pd.Timestamp(end_date))].copy().reset_index(drop=True)

        if len(df_period) == 0:
            raise ValueError(f"지정한 기간({start_date} ~ {end_date})에 필터링된 데이터가 없습니다.")

        cash = float(self.initial_capital)
        hold = 0

        # 각 웅덩이 진행 상태 (True: 웅덩이 내부, False: 웅덩이 탈출 상태)
        in_puddle_20 = False
        in_puddle_60 = False
        in_puddle_120 = False
        in_puddle_rsi = False

        # 분할 매수 계획 큐: [{'remaining_days': int, 'daily_amount': float, 'stage': int}]
        buy_plans = []
        records = []

        for idx in range(len(df_period)):
            row = df_period.iloc[idx]
            d = row['Date']
            c = float(row['Close'])
            low = float(row.get('Low', c))
            ma20 = float(row['MA20']) if pd.notnull(row['MA20']) else c
            ma60 = float(row['MA60']) if pd.notnull(row['MA60']) else c
            ma120 = float(row['MA120']) if pd.notnull(row['MA120']) else c
            rsi = float(row['RSI'])

            # -------------------------------------------------------------
            # [단계 1] 신규 웅덩이 트리거 판정 (우선순위: 4차 -> 3차 -> 2차 -> 1차)
            # -------------------------------------------------------------
            # 4차 웅덩이: 120일선 터치 + RSI <= 35
            if low <= ma120 and rsi <= 35:
                if not in_puddle_rsi:
                    in_puddle_rsi = True
                    in_puddle_120 = True
                    in_puddle_60 = True
                    in_puddle_20 = True
                    alloc = cash * 1.0  # 남은 현금 100%
                    if alloc > 10.0:
                        buy_plans.append({'remaining_days': 5, 'daily_amount': alloc / 5.0, 'stage': 4})

            # 3차 웅덩이: 120일선 터치
            elif low <= ma120:
                if not in_puddle_120:
                    in_puddle_120 = True
                    in_puddle_60 = True
                    in_puddle_20 = True
                    alloc = cash * 0.50  # 현금의 50%
                    if alloc > 10.0:
                        buy_plans.append({'remaining_days': 5, 'daily_amount': alloc / 5.0, 'stage': 3})

            # 2차 웅덩이: 60일선 터치
            elif low <= ma60:
                if not in_puddle_60:
                    in_puddle_60 = True
                    in_puddle_20 = True
                    alloc = cash * 0.50  # 현금의 50%
                    if alloc > 10.0:
                        buy_plans.append({'remaining_days': 5, 'daily_amount': alloc / 5.0, 'stage': 2})

            # 1차 웅덩이: 20일선 터치
            elif low <= ma20:
                if not in_puddle_20:
                    in_puddle_20 = True
                    alloc = cash * 0.10  # 현금의 10%
                    if alloc > 10.0:
                        buy_plans.append({'remaining_days': 2, 'daily_amount': alloc / 2.0, 'stage': 1})

            # -------------------------------------------------------------
            # [단계 2] 당일 분할 매수 집행
            # -------------------------------------------------------------
            today_buy_cash = 0.0
            for plan in list(buy_plans):
                amt = min(plan['daily_amount'], cash - today_buy_cash)
                if amt > 0:
                    today_buy_cash += amt
                plan['remaining_days'] -= 1
                if plan['remaining_days'] <= 0:
                    buy_plans.remove(plan)

            if today_buy_cash > 0 and cash >= today_buy_cash:
                effective_price = c * (1.0 + self.fee_rate)
                shares_to_buy = int(today_buy_cash / effective_price)
                if shares_to_buy > 0:
                    used = shares_to_buy * effective_price
                    cash -= used
                    hold += shares_to_buy

            # -------------------------------------------------------------
            # [단계 3] 당일 종가 기준 웅덩이 탈출(회복) 판정
            # 주가가 이평선 위로 회복하면 다음 하락 시 새 웅덩이로 감지
            # -------------------------------------------------------------
            if c > ma20:
                in_puddle_20 = False
            if c > ma60:
                in_puddle_60 = False
            if c > ma120:
                in_puddle_120 = False
            if c > ma120 or rsi > 35:
                in_puddle_rsi = False

            # 당일 총자산 계산 (마지막 날 매도 수수료 가상 반영)
            gross_equity = c * hold
            net_equity = gross_equity * (1.0 - self.fee_rate - self.sec_fee) if idx == len(df_period) - 1 else gross_equity
            asset = cash + net_equity

            records.append({
                'Date': d,
                'Close': c,
                'Cash': cash,
                'Hold': hold,
                'Asset': asset,
                'Profit': 0.0
            })

        df_res = pd.DataFrame(records)
        df_res['DD'] = self.compute_drawdown(df_res['Asset'], self.initial_capital)
        return df_res
