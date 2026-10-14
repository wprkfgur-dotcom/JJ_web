import sys
import os
import io
import copy

sys.stdout = io.TextIOWrapper(sys.stdout.detach(), encoding='utf-8')
sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

import numpy as np
import pandas as pd
from core.data import fetch_market_data
from strategies.jongjong import JongJongStrategy
from core.metrics import calculate_metrics

class TunableJongJongStrategy(JongJongStrategy):
    """
    Safe 진입/탈출 및 Riskoff 진입/오프셋 조건을 유연하게 변경할 수 있는 파라미터 튜닝용 종종이 클래스
    """
    def __init__(self,
                 safe_entry_drop1=-0.03,    # 20일선 위에서 하향 돌파 시 낙폭 기준 (기본 -3%)
                 safe_entry_drop2=-0.08,    # 5일선 위에서 급락 시 낙폭 기준 (기본 -8%)
                 safe_exit_bounce1=0.058,   # 탈출 1일 반등 기준 (기본 +5.8%)
                 safe_exit_bounce2=0.060,   # 탈출 2일 반등 기준 (기본 +6.0%)
                 safe_target_yield=0.0025,  # Safe 모드 목표수익률 (기본 0.25%)
                 safe_div=7.0,              # Safe 모드 분할수 (기본 7)
                 risk_dd_threshold=-0.08,   # Riskoff 계좌 DD 기준 (기본 -8%)
                 risk_drop_threshold=-0.15, # Riskoff 당일 급락 기준 (기본 -15%)
                 risk_buy_offset=-0.055,    # Riskoff 매수 오프셋 (기본 -5.5%)
                 **kwargs):
        super().__init__(**kwargs)
        self.safe_entry_drop1 = float(safe_entry_drop1)
        self.safe_entry_drop2 = float(safe_entry_drop2)
        self.safe_exit_bounce1 = float(safe_exit_bounce1)
        self.safe_exit_bounce2 = float(safe_exit_bounce2)
        self.risk_dd_threshold = float(risk_dd_threshold)
        self.risk_drop_threshold = float(risk_drop_threshold)
        self.risk_buy_offset = float(risk_buy_offset)
        
        self.div_rounds['Safe'] = float(safe_div)
        self.target_yields['Safe'] = float(safe_target_yield)

    def prepare_indicators(self, df_data: pd.DataFrame, start_date: str) -> pd.DataFrame:
        df = df_data.copy().reset_index(drop=True)
        trade_start_indices = df[df['Date'] >= pd.Timestamp(start_date)].index
        first_trade_idx = trade_start_indices[0] if len(trade_start_indices) > 0 else (len(df) - 1)
        db_start_idx = max(0, first_trade_idx - 25)
        df = df.iloc[db_start_idx:].reset_index(drop=True)

        closes = df['Close'].values
        n = len(df)
        ma5, ma20, g_col, h_col, i_col, j_col, db_mode = [], [], [], [], [], [], []

        for k in range(n):
            m5 = closes[k] if k < 4 else np.mean(closes[k-4:k+1])
            m20 = closes[k] if k < 19 else np.mean(closes[k-19:k+1])
            g = bool(m5 >= m20)
            h = bool(closes[k] >= m20)
            i_chg = 0.0 if k == 0 else (closes[k] / closes[k-1] - 1.0)
            j_chg = i_chg if k < 2 else (closes[k] / closes[k-2] - 1.0)

            ma5.append(m5)
            ma20.append(m20)
            g_col.append(g)
            h_col.append(h)
            i_col.append(i_chg)
            j_col.append(j_chg)

            if k < 3:
                db_mode.append('Normal')
            else:
                cond_safe = ((not h_col[k-3]) and h_col[k-2] and (i_col[k-1] <= self.safe_entry_drop1)) or \
                            (g_col[k-2] and (i_col[k-1] <= self.safe_entry_drop2))
                cond_norm = ((not g_col[k-2]) and (i_col[k-1] >= self.safe_exit_bounce1)) or \
                            ((not g_col[k-2]) and (j_col[k-1] >= self.safe_exit_bounce2))
                if cond_safe:
                    db_mode.append('Safe')
                elif cond_norm:
                    db_mode.append('Normal')
                else:
                    db_mode.append(db_mode[k-1])

        df['MA5'] = ma5
        df['MA20'] = ma20
        df['G'] = g_col
        df['H'] = h_col
        df['I'] = i_col
        df['J'] = j_col
        df['DB_Mode'] = db_mode
        return df

def run_experiment(df_market, ticker, start_date, end_date, scenarios, capital=100000.0):
    rows = []
    for sc_name, sc_params in scenarios.items():
        strat = TunableJongJongStrategy(initial_capital=capital, reserve_ratio=0.05, **sc_params)
        df_res = strat.run(df_market, start_date, end_date)
        m = calculate_metrics(df_res, capital)
        
        mode_counts = df_res['Mode'].value_counts().to_dict()
        n_cnt = mode_counts.get('Normal', 0)
        s_cnt = mode_counts.get('Safe', 0)
        r_cnt = mode_counts.get('Riskoff', 0)
        
        rows.append({
            "시나리오": sc_name,
            "최종자산($)": f"${m['final_asset']:,.0f}",
            "총수익률(%)": f"{m['total_return']:+.1f}%",
            "CAGR(%)": f"{m['cagr']:+.1f}%",
            "MDD(%)": f"{m['mdd']:.2f}%",
            "샤프지수": f"{m['sharpe']:.2f}",
            "칼마비율": f"{m['calmar']:.2f}",
            "모드일수(N/S/R)": f"{n_cnt}/{s_cnt}/{r_cnt}"
        })
    return pd.DataFrame(rows)

if __name__ == "__main__":
    df_soxl = fetch_market_data("SOXL", "2019-01-02", "2026-09-30", warmup_days=60)
    df_soxl_2022 = fetch_market_data("SOXL", "2022-01-03", "2022-12-30", warmup_days=60)

    # -------------------------------------------------------------
    # 실험 1: Safe 모드 탈출 조건 (반등 기준 변경)
    # -------------------------------------------------------------
    scenarios_exit = {
        "기본값 (1일+5.8% or 2일+6%)": dict(safe_exit_bounce1=0.058, safe_exit_bounce2=0.060),
        "빠른 탈출 (1일+3.5% or 2일+4%)": dict(safe_exit_bounce1=0.035, safe_exit_bounce2=0.040),
        "초고속 탈출 (1일+2% or 2일+2.5%)": dict(safe_exit_bounce1=0.020, safe_exit_bounce2=0.025),
        "보수적 탈출 (1일+8% or 2일+9%)": dict(safe_exit_bounce1=0.080, safe_exit_bounce2=0.090),
        "극보수 탈출 (1일+10% or 2일+12%)": dict(safe_exit_bounce1=0.100, safe_exit_bounce2=0.120),
    }

    print("\n" + "="*85)
    print(" [실험 1-A] SOXL 전체 기간 (2019~2026): Safe 모드 탈출(반등) 기준별 성과")
    print("="*85)
    print(run_experiment(df_soxl, "SOXL", "2019-01-02", "2026-09-30", scenarios_exit).to_string(index=False))

    print("\n" + "="*85)
    print(" [실험 1-B] SOXL 2022년 대폭락장: Safe 모드 탈출(반등) 기준별 성과")
    print("="*85)
    print(run_experiment(df_soxl_2022, "SOXL", "2022-01-03", "2022-12-30", scenarios_exit).to_string(index=False))

    # -------------------------------------------------------------
    # 실험 2: Safe 모드 진입 민감도 (낙폭 기준 변경)
    # -------------------------------------------------------------
    scenarios_entry = {
        "기본값 (-3% & -8%)": dict(safe_entry_drop1=-0.03, safe_entry_drop2=-0.08),
        "민감 진입 (조기경보: -2% & -5%)": dict(safe_entry_drop1=-0.02, safe_entry_drop2=-0.05),
        "초민감 진입 (-1% & -3%)": dict(safe_entry_drop1=-0.01, safe_entry_drop2=-0.03),
        "둔감 진입 (공격적: -5% & -12%)": dict(safe_entry_drop1=-0.05, safe_entry_drop2=-0.12),
        "Safe 모드 비활성화 (진입불가)": dict(safe_entry_drop1=-0.99, safe_entry_drop2=-0.99),
    }

    print("\n" + "="*85)
    print(" [실험 2-A] SOXL 전체 기간 (2019~2026): Safe 모드 진입 민감도별 성과")
    print("="*85)
    print(run_experiment(df_soxl, "SOXL", "2019-01-02", "2026-09-30", scenarios_entry).to_string(index=False))

    print("\n" + "="*85)
    print(" [실험 2-B] SOXL 2022년 대폭락장: Safe 모드 진입 민감도별 성과")
    print("="*85)
    print(run_experiment(df_soxl_2022, "SOXL", "2022-01-03", "2022-12-30", scenarios_entry).to_string(index=False))

    # -------------------------------------------------------------
    # 실험 3: Riskoff 조건 변경 (발동 임계치 및 매수 오프셋)
    # -------------------------------------------------------------
    scenarios_riskoff = {
        "기본값 (DD-8%, 일일-15%, 오프셋-5.5%)": dict(risk_dd_threshold=-0.08, risk_drop_threshold=-0.15, risk_buy_offset=-0.055),
        "조기 발동 (DD-5%, 일일-10%, 오프셋-5.5%)": dict(risk_dd_threshold=-0.05, risk_drop_threshold=-0.10, risk_buy_offset=-0.055),
        "늦은 발동 (DD-12%, 일일-20%, 오프셋-5.5%)": dict(risk_dd_threshold=-0.12, risk_drop_threshold=-0.20, risk_buy_offset=-0.055),
        "깊은 바닥 매수 (오프셋 -8.0%)": dict(risk_buy_offset=-0.08),
        "공격적 바닥 매수 (오프셋 -3.0%)": dict(risk_buy_offset=-0.03),
        "Riskoff 비활성화 (일일-99%)": dict(risk_drop_threshold=-0.99),
    }

    print("\n" + "="*85)
    print(" [실험 3-A] SOXL 전체 기간 (2019~2026): Riskoff 조건별 성과")
    print("="*85)
    print(run_experiment(df_soxl, "SOXL", "2019-01-02", "2026-09-30", scenarios_riskoff).to_string(index=False))

    print("\n" + "="*85)
    print(" [실험 3-B] SOXL 2022년 대폭락장: Riskoff 조건별 성과")
    print("="*85)
    print(run_experiment(df_soxl_2022, "SOXL", "2022-01-03", "2022-12-30", scenarios_riskoff).to_string(index=False))
