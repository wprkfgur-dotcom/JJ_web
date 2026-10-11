import sys
import os
import io

sys.stdout = io.TextIOWrapper(sys.stdout.detach(), encoding='utf-8')
sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

import pandas as pd
from core.data import fetch_market_data
from strategies.jongjong import JongJongStrategy
from tools.test_reserve_merge_backtest import JongJongReserveMergedStrategy
from core.metrics import calculate_metrics, calculate_yearly_stats, build_comparison_table

def analyze_periods():
    ticker = "SOXL"
    capital = 100000.0
    df_market = fetch_market_data(ticker, "2011-03-01", "2026-09-30", warmup_days=60)

    strat_orig = JongJongStrategy(initial_capital=capital, name="기존 종종이")
    strat_merged = JongJongReserveMergedStrategy(initial_capital=capital, variant='standard', name="Risk-Off 병합 종종이")

    df_orig = strat_orig.run(df_market, "2011-03-01", "2026-09-30")
    df_merged = strat_merged.run(df_market, "2011-03-01", "2026-09-30")

    # 주요 위기 국면 분석
    periods = [
        ("2011년 미국 신용등급 강등 폭락장", "2011-07-01", "2011-12-30"),
        ("2018년 미중 무역분쟁 및 긴축 급락장", "2018-09-01", "2019-03-29"),
        ("2020년 코로나19 펜데믹 폭락장", "2020-02-01", "2020-09-30"),
        ("2022년 금리인상 대폭락장 (역대 최장 Risk-Off)", "2022-01-03", "2022-12-30"),
        ("2025~2026년 최근 사이클", "2025-01-02", "2026-09-30"),
    ]

    print("="*80)
    print(" [주요 역사적 위기 국면별 성과 비교 (SOXL)]")
    print("="*80)

    for title, s_d, e_d in periods:
        sub_orig = df_orig[(df_orig['Date'] >= pd.Timestamp(s_d)) & (df_orig['Date'] <= pd.Timestamp(e_d))].copy()
        sub_merged = df_merged[(df_merged['Date'] >= pd.Timestamp(s_d)) & (df_merged['Date'] <= pd.Timestamp(e_d))].copy()
        
        start_asset_orig = sub_orig.iloc[0]['Asset']
        end_asset_orig = sub_orig.iloc[-1]['Asset']
        ret_orig = (end_asset_orig / start_asset_orig - 1.0) * 100
        
        start_asset_merged = sub_merged.iloc[0]['Asset']
        end_asset_merged = sub_merged.iloc[-1]['Asset']
        ret_merged = (end_asset_merged / start_asset_merged - 1.0) * 100

        mdd_orig = sub_orig['DD'].min() * 100
        mdd_merged = sub_merged['DD'].min() * 100

        print(f"\n▶ {title} ({s_d} ~ {e_d})")
        print(f"  - 기존 종종이       : 수익률 {ret_orig:+.2f}% | 기간 MDD: {mdd_orig:.2f}% | 시작 자산: ${start_asset_orig:,.0f} → 기말 자산: ${end_asset_orig:,.0f}")
        print(f"  - Risk-Off 병합 종종이: 수익률 {ret_merged:+.2f}% | 기간 MDD: {mdd_merged:.2f}% | 시작 자산: ${start_asset_merged:,.0f} → 기말 자산: ${end_asset_merged:,.0f}")

    # 연도별 수익률 비교 테이블
    y_orig = calculate_yearly_stats(df_orig, capital)
    y_merged = calculate_yearly_stats(df_merged, capital)

    print("\n" + "="*80)
    print(" [연도별 연간 수익률 및 MDD 정밀 비교]")
    print("="*80)
    print(f"{'연도':<6} | {'기존 종종이 수익률':<15} | {'기존 MDD':<10} | {'신규 병합 수익률':<15} | {'신규 MDD':<10} | {'초과 성과(p.p)':<12}")
    print("-" * 80)
    for i in range(len(y_orig)):
        row_o = y_orig.iloc[i]
        row_m = y_merged.iloc[i]
        ret_o = float(row_o['연간수익률'].replace('%', '').replace('+', ''))
        ret_m = float(row_m['연간수익률'].replace('%', '').replace('+', ''))
        diff = ret_m - ret_o
        print(f"{row_o['연도']:<6} | {row_o['연간수익률']:<15} | {row_o['연중MDD']:<10} | {row_m['연간수익률']:<15} | {row_m['연중MDD']:<10} | {diff:>+10.2f}%p")

if __name__ == "__main__":
    analyze_periods()
