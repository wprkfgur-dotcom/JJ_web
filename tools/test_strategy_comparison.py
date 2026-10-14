import sys
import os
import io

# UTF-8 출력 강제
sys.stdout = io.TextIOWrapper(sys.stdout.detach(), encoding='utf-8')
sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

import pandas as pd
from core.data import fetch_market_data
from core.strategy_registry import create_backtest_strategy
from core.metrics import build_comparison_table, calculate_yearly_stats

def analyze(ticker, start_date, end_date, capital=100000.0):
    df_market = fetch_market_data(ticker, start_date, end_date, warmup_days=60)
    strategies = [
        "종종이 기본전략",
        "무한매수법 v4.0",
        "VR 5.0 (밸류리밸런싱)",
        f"{ticker} 단순보유"
    ]
    results_dict = {}
    for name in strategies:
        strat = create_backtest_strategy(name, ticker, capital)
        df_res = strat.run(df_market, start_date, end_date)
        results_dict[name] = (df_res, capital)
    
    comp_df = build_comparison_table(results_dict)
    print(comp_df.to_string(index=False))
    return results_dict

if __name__ == "__main__":
    print("\n" + "="*80)
    print(" [1] SOXL 전체 기간 (2019-01-02 ~ 2026-09-30)")
    print("="*80)
    res_soxl_all = analyze("SOXL", "2019-01-02", "2026-09-30")
    
    print("\n" + "-"*80)
    print(" [1-1] SOXL 종종이 연도별 상세 성과")
    print("-"*80)
    print(calculate_yearly_stats(res_soxl_all["종종이 기본전략"][0], 100000.0).to_string(index=False))

    print("\n" + "-"*80)
    print(" [1-2] SOXL 무한매수법 v4 연도별 상세 성과")
    print("-"*80)
    print(calculate_yearly_stats(res_soxl_all["무한매수법 v4.0"][0], 100000.0).to_string(index=False))

    print("\n" + "="*80)
    print(" [2] SOXL 2022년 금리인상 대폭락장 (2022-01-03 ~ 2022-12-30)")
    print("="*80)
    analyze("SOXL", "2022-01-03", "2022-12-30")

    print("\n" + "="*80)
    print(" [3] TQQQ 전체 기간 (2019-01-02 ~ 2026-09-30)")
    print("="*80)
    res_tqqq_all = analyze("TQQQ", "2019-01-02", "2026-09-30")

    print("\n" + "="*80)
    print(" [4] TQQQ 2022년 금리인상 대폭락장 (2022-01-03 ~ 2022-12-30)")
    print("="*80)
    analyze("TQQQ", "2022-01-03", "2022-12-30")
