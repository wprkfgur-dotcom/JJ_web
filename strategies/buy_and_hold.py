"""
단순 보유 (Buy & Hold) 전략 모듈
첫 거래일에 전액 매수 후 만기까지 그대로 보유하는 벤치마크 전략입니다.
"""
import pandas as pd
from .base import BaseStrategy


class BuyAndHoldStrategy(BaseStrategy):
    """
    첫날 전액 매수 후 지속 보유하는 기준 벤치마크 전략.
    """

    def __init__(self, initial_capital: float = 200000.0,
                 fee_rate: float = 0.0005, sec_fee: float = 0.0000278,
                 name: str = "Buy & Hold"):
        super().__init__(name=name, initial_capital=initial_capital,
                         fee_rate=fee_rate, sec_fee=sec_fee)

    def run(self, df_data: pd.DataFrame, start_date: str, end_date: str) -> pd.DataFrame:
        df_period = df_data[(df_data['Date'] >= pd.Timestamp(start_date)) &
                            (df_data['Date'] <= pd.Timestamp(end_date))].copy().reset_index(drop=True)

        if len(df_period) == 0:
            raise ValueError(f"지정한 기간({start_date} ~ {end_date})에 거래 데이터가 없습니다.")

        first_close = df_period.loc[0, 'Close']
        # 첫날 매수 수수료 반영 매수 가능 주수 계산
        effective_price = first_close * (1.0 + self.fee_rate)
        shares = int(self.initial_capital / effective_price)
        used_cash = shares * effective_price
        cash = self.initial_capital - used_cash

        records = []
        for idx in range(len(df_period)):
            d = df_period.loc[idx, 'Date']
            c = df_period.loc[idx, 'Close']
            # 매도 수수료 가상 반영 순자산
            gross_equity = c * shares
            net_equity = gross_equity * (1.0 - self.fee_rate - self.sec_fee) if idx == len(df_period) - 1 else gross_equity
            asset = cash + net_equity

            records.append({
                'Date': d,
                'Close': c,
                'Cash': cash,
                'Hold': shares,
                'Asset': asset,
                'Profit': 0.0
            })

        df_res = pd.DataFrame(records)
        df_res['DD'] = self.compute_drawdown(df_res['Asset'], self.initial_capital)
        return df_res
