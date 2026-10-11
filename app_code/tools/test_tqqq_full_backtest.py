import sys
import os
import io

sys.stdout = io.TextIOWrapper(sys.stdout.detach(), encoding='utf-8')
sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

import pandas as pd
from core.data import fetch_market_data
from strategies.jongjong import JongJongStrategy
from core.metrics import calculate_metrics, calculate_yearly_stats, build_comparison_table

def run_tqqq_comparison():
    ticker = "TQQQ"
    start_date = "2010-02-12"
    end_date = "2026-09-30"
    capital = 100000.0

    print(f"[{ticker}] {start_date} ~ {end_date} 시세 데이터 수집 및 분석 시작...")
    df_market = fetch_market_data(ticker, start_date, end_date, warmup_days=60)
    print(f"데이터 준비 완료: 총 {len(df_market)} 행")

    # 1. 기존 종종이 (위기준비금 병합 없음, Cash 풀 혼용)
    strat_orig = JongJongStrategy(initial_capital=capital, reserve_merge_on_riskoff=False, name="기존 종종이")
    df_orig = strat_orig.run(df_market, start_date, end_date)

    # 2. 새로운 종종이 (위기준비금 격리 보관 & Risk-Off 시 전액 병합)
    strat_new = JongJongStrategy(initial_capital=capital, reserve_merge_on_riskoff=True, name="신규 종종이 (Risk-Off 병합)")
    df_new = strat_new.run(df_market, start_date, end_date)

    # 결과 테이블
    results_dict = {
        strat_orig.name: (df_orig, capital),
        strat_new.name: (df_new, capital)
    }

    print("\n" + "="*85)
    print(f" [TQQQ 전체 기간 백테스트 종합 비교] ({start_date} ~ {end_date}, 16.6년)")
    print("="*85)
    comp_df = build_comparison_table(results_dict)
    print(comp_df.to_string(index=False))

    # 연도별 비교
    y_orig = calculate_yearly_stats(df_orig, capital)
    y_new = calculate_yearly_stats(df_new, capital)

    print("\n" + "="*85)
    print(" [연도별 상세 성과 정밀 비교 (2010 ~ 2026)]")
    print("="*85)
    print(f"{'연도':<6} | {'기존 종종이 수익률':<15} | {'기존 MDD':<10} | {'신규 종종이 수익률':<15} | {'신규 MDD':<10} | {'초과 성과(p.p)':<12}")
    print("-" * 85)
    for i in range(len(y_orig)):
        row_o = y_orig.iloc[i]
        row_n = y_new.iloc[i]
        ret_o = float(row_o['연간수익률'].replace('%', '').replace('+', ''))
        ret_n = float(row_n['연간수익률'].replace('%', '').replace('+', ''))
        diff = ret_n - ret_o
        print(f"{row_o['연도']:<6} | {row_o['연간수익률']:<15} | {row_o['연중MDD']:<10} | {row_n['연간수익률']:<15} | {row_n['연중MDD']:<10} | {diff:>+10.2f}%p")

    # 주요 위기 국면별 성과
    periods = [
        ("2010년 남유럽 재정위기 (Flash Crash)", "2010-04-01", "2010-10-29"),
        ("2011년 미국 신용등급 강등 폭락장", "2011-07-01", "2011-12-30"),
        ("2015~2016년 중국 위안화 쇼크 & 유가 폭락", "2015-08-01", "2016-04-29"),
        ("2018년 미중 무역분쟁 및 긴축 급락장", "2018-09-01", "2019-03-29"),
        ("2020년 코로나19 팬데믹 대폭락장", "2020-02-01", "2020-09-30"),
        ("2022년 금리인상 대폭락장 (역대 최장 Risk-Off)", "2022-01-03", "2022-12-30"),
        ("2024~2026년 최근 AI 랠리 & 변동성", "2024-01-02", "2026-09-30")
    ]

    print("\n" + "="*85)
    print(" [주요 역사적 위기 국면별 심층 분석]")
    print("="*85)
    for title, s_d, e_d in periods:
        sub_o = df_orig[(df_orig['Date'] >= pd.Timestamp(s_d)) & (df_orig['Date'] <= pd.Timestamp(e_d))]
        sub_n = df_new[(df_new['Date'] >= pd.Timestamp(s_d)) & (df_new['Date'] <= pd.Timestamp(e_d))]
        if sub_o.empty or sub_n.empty:
            continue
        start_o = sub_o.iloc[0]['Asset']
        end_o = sub_o.iloc[-1]['Asset']
        ret_o = (end_o / start_o - 1.0) * 100
        mdd_o = sub_o['DD'].min() * 100

        start_n = sub_n.iloc[0]['Asset']
        end_n = sub_n.iloc[-1]['Asset']
        ret_n = (end_n / start_n - 1.0) * 100
        mdd_n = sub_n['DD'].min() * 100

        print(f"\n▶ {title} ({s_d} ~ {e_d})")
        print(f"  - 기존 종종이: 수익률 {ret_o:+.2f}% | 기간 MDD: {mdd_o:.2f}% | ${start_o:,.0f} → ${end_o:,.0f}")
        print(f"  - 신규 종종이: 수익률 {ret_n:+.2f}% | 기간 MDD: {mdd_n:.2f}% | ${start_n:,.0f} → ${end_n:,.0f}")

    # 병합 발생 이벤트
    merge_events = df_new[df_new['MergedAK'] > 0]
    print("\n" + "="*85)
    print(f" [Risk-Off 위기준비금 병합 이벤트 내역 (총 {len(merge_events)}회)]")
    print("="*85)
    for _, r in merge_events.iterrows():
        print(f"날짜: {r['Date'].strftime('%Y-%m-%d')} | 병합된 AK: ${r['MergedAK']:,.2f} | TQQQ 종가: ${r['Close']:.2f} | 당시 AR: ${r['AR']:,.2f}")

if __name__ == "__main__":
    run_tqqq_comparison()
