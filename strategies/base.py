"""
전략 추상 기본 클래스 (Base Strategy)
모든 백테스트 전략은 이 클래스를 상속받아 run() 메서드를 구현합니다.
"""
from abc import ABC, abstractmethod
import pandas as pd
import numpy as np


class BaseStrategy(ABC):
    """
    모든 투자 전략의 기본 클래스.
    """

    def __init__(self, name: str, initial_capital: float = 200000.0,
                 fee_rate: float = 0.0005, sec_fee: float = 0.0000278):
        self.name = name
        self.initial_capital = float(initial_capital)
        self.fee_rate = float(fee_rate)
        self.sec_fee = float(sec_fee)

    @abstractmethod
    def run(self, df_data: pd.DataFrame, start_date: str, end_date: str) -> pd.DataFrame:
        """
        시세 데이터(df_data)를 입력받아 전략 백테스트를 수행하고 일별 결과 데이터프레임을 반환합니다.

        반환 데이터프레임 필수 포함 컬럼:
        - Date: 일자 (Timestamp)
        - Close: 당일 종가
        - Cash: 보유 현금 ($)
        - Hold: 보유 주식 수량 (주)
        - Asset: 총자산 가치 (Cash + Close * Hold, $)
        - DD: 누적 고점 대비 낙폭 (비율, 예: -0.15)
        """

    @staticmethod
    def compute_drawdown(asset_series: pd.Series, initial_capital: float) -> pd.Series:
        """
        자산 곡선으로부터 고점 대비 최대 낙폭(Drawdown) 비율을 계산합니다.
        """
        peaks = np.maximum.accumulate([initial_capital] + asset_series.tolist())[1:]
        return (asset_series.values / peaks) - 1.0
