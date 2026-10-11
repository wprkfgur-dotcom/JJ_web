"""
차트 시각화 모듈 (Visualizer)
단일 전략 상세 분석 및 여러 전략 간의 비교 차트 출력을 지원합니다.
"""
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.ticker as ticker
import platform

# 윈도우 한글 폰트(맑은 고딕) 및 마이너스 부호 깨짐 방지 설정
if platform.system() == 'Windows':
    plt.rcParams['font.family'] = 'Malgun Gothic'
plt.rcParams['axes.unicode_minus'] = False


# 고대비 시각화 색상 팔레트
COLORS = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']


def plot_comparison(results_dict: dict, ticker_symbol: str,
                    save_chart: bool = True, chart_filename: str = 'backtest_result.png',
                    show_chart: bool = True):
    """
    여러 전략의 백테스트 결과를 상하 2분할 차트로 시각화합니다.
    - 상단 (ax1): 각 전략별 총자산(Asset) 성장 곡선
    - 하단 (ax2): 각 전략별 고점 대비 낙폭(Drawdown %) 곡선
    """
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 9), gridspec_kw={'height_ratios': [2.5, 1]}, sharex=True)

    first_key = list(results_dict.keys())[0]
    first_df, first_cap = results_dict[first_key]

    # 상단 그래프: 전략별 자산 성장 곡선
    for idx, (strat_name, (df_res, cap)) in enumerate(results_dict.items()):
        color = COLORS[idx % len(COLORS)]
        ax1.plot(df_res['Date'], df_res['Asset'], label=f"{strat_name} ($)", color=color, linewidth=2.0)

        # 종종이 전략인 경우 AR(시드)과 AK(위기준비금) 곡선 함께 표시
        if 'AR' in df_res.columns and 'AK' in df_res.columns and ('기본전략' in strat_name or len(results_dict) <= 3):
            ax1.plot(df_res['Date'], df_res['AR'], label=f"Active Seed ({strat_name}, $)", color='#2ca02c', linestyle=':', linewidth=1.4)
            ax1.plot(df_res['Date'], df_res['AK'], label=f"Crisis Reserve ({strat_name}, $)", color='#9467bd', linestyle='-.', linewidth=1.2)

    ax1.axhline(first_cap, color='gray', linestyle='-', linewidth=0.8, alpha=0.5, label=f'Initial Capital (${first_cap:,.0f})')
    title_suffix = "Comparison" if len(results_dict) > 1 else list(results_dict.keys())[0]
    ax1.set_title(f"Backtest Asset Curve {title_suffix} ({ticker_symbol})", fontsize=14, fontweight='bold', pad=12)
    ax1.set_ylabel("Asset Value ($)", fontsize=11)
    ax1.yaxis.set_major_formatter(ticker.StrMethodFormatter('${x:,.0f}'))
    ax1.grid(True, linestyle='--', alpha=0.4)
    ax1.legend(loc='upper left', fontsize=10)

    # 하단 그래프: 전략별 낙폭(Drawdown %) 곡선
    for idx, (strat_name, (df_res, _)) in enumerate(results_dict.items()):
        color = COLORS[idx % len(COLORS)]
        dd_pct = df_res['DD'] * 100.0
        if len(results_dict) == 1:
            ax2.fill_between(df_res['Date'], dd_pct, 0, color=color, alpha=0.25)
        ax2.plot(df_res['Date'], dd_pct, label=f"{strat_name} DD", color=color, linewidth=1.2)

    ax2.set_title("Drawdown Comparison (DD %)", fontsize=12, fontweight='bold', pad=8)
    ax2.set_ylabel("Drawdown (%)", fontsize=11)
    ax2.set_xlabel("Date", fontsize=11)
    ax2.yaxis.set_major_formatter(ticker.StrMethodFormatter('{x:.0f}%'))
    ax2.grid(True, linestyle='--', alpha=0.4)
    ax2.legend(loc='lower left', fontsize=9)

    ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    plt.xticks(rotation=0)
    plt.tight_layout()

    if save_chart and chart_filename:
        plt.savefig(chart_filename, dpi=150)
        print(f"📈 차트 이미지가 '{chart_filename}' 파일로 저장되었습니다.")

    if show_chart:
        plt.show()
