"""
백테스트 성과 분석 및 전략 비교 통계 모듈 (Metrics & Performance Analytics)
"""
import numpy as np
import pandas as pd


def calculate_metrics(df_result: pd.DataFrame, initial_capital: float) -> dict:
    """
    단일 전략 결과 데이터프레임에서 주요 투자 성과 지표를 계산합니다.
    """
    if len(df_result) == 0:
        return {}

    final_asset = df_result.iloc[-1]['Asset']
    total_return = (final_asset / initial_capital - 1.0) * 100.0
    mdd = df_result['DD'].min() * 100.0

    # 기간 및 CAGR 계산
    start_date = df_result.iloc[0]['Date']
    end_date = df_result.iloc[-1]['Date']
    total_days = (end_date - start_date).days
    years = max(total_days / 365.25, 0.01)
    cagr = ((final_asset / initial_capital) ** (1.0 / years) - 1.0) * 100.0 if final_asset > 0 else -100.0

    # 일별 수익률 기반 샤프 지수 (연율화, 무위험 이자율 2% 가정)
    daily_returns = df_result['Asset'].pct_change().dropna()
    rf_daily = 0.02 / 252
    excess_returns = daily_returns - rf_daily
    sharpe = (excess_returns.mean() / excess_returns.std() * np.sqrt(252)) if excess_returns.std() > 0 else 0.0

    # Calmar Ratio (CAGR / |MDD|)
    calmar = (cagr / abs(mdd)) if abs(mdd) > 0 else 0.0

    # 최종 현금 및 보유 수량
    final_cash = df_result.iloc[-1].get('Cash', 0.0)
    final_hold = df_result.iloc[-1].get('Hold', 0)
    final_ak = df_result.iloc[-1].get('AK', None)
    final_ar = df_result.iloc[-1].get('AR', None)

    return {
        'initial_capital': initial_capital,
        'final_asset': final_asset,
        'total_return': total_return,
        'cagr': cagr,
        'mdd': mdd,
        'sharpe': sharpe,
        'calmar': calmar,
        'final_cash': final_cash,
        'final_hold': final_hold,
        'final_ak': final_ak,
        'final_ar': final_ar,
        'trading_days': len(df_result),
        'start_date': start_date,
        'end_date': end_date
    }


def calculate_yearly_stats(df_result: pd.DataFrame, initial_capital: float) -> pd.DataFrame:
    """
    연도별 수익률 및 연중 MDD 요약 테이블을 산출합니다.
    """
    df_temp = df_result.copy()
    df_temp['Year'] = df_temp['Date'].dt.year
    years = sorted(df_temp['Year'].unique())
    yearly_rows = []

    prev_end_asset = initial_capital

    for idx, y in enumerate(years):
        df_y = df_temp[df_temp['Year'] == y]
        start_asset = initial_capital if idx == 0 else prev_end_asset
        end_asset = df_y.iloc[-1]['Asset']
        strat_ret = (end_asset / start_asset - 1.0) * 100.0

        # 해당 연도 내에서의 고점 대비 최대 낙폭 (Yearly MDD)
        peaks = np.maximum.accumulate([start_asset] + df_y['Asset'].tolist())[1:]
        yearly_dds = (df_y['Asset'].values / peaks) - 1.0
        yearly_mdd = np.min(yearly_dds) * 100.0

        row = {
            '연도': str(y),
            '거래일수': len(df_y),
            '기초자산($)': f"${start_asset:,.0f}",
            '기말자산($)': f"${end_asset:,.0f}",
            '연간수익률': f"{strat_ret:+.2f}%",
            '연중MDD': f"{yearly_mdd:.2f}%"
        }

        # 전략별 모드 카운트 컬럼이 있는 경우 추가
        if 'Mode' in df_y.columns:
            mode_counts = df_y['Mode'].value_counts().to_dict()
            if any(k in mode_counts for k in ['Normal', 'Safe', 'Riskoff']):
                row['모드(N/S/R)'] = f"{mode_counts.get('Normal', 0)}/{mode_counts.get('Safe', 0)}/{mode_counts.get('Riskoff', 0)}"
            elif any(k in mode_counts for k in ['NORMAL', 'REVERSE']):
                row['모드(일반/리버스)'] = f"{mode_counts.get('NORMAL', 0)}/{mode_counts.get('REVERSE', 0)}"

        yearly_rows.append(row)
        prev_end_asset = end_asset

    return pd.DataFrame(yearly_rows)


def build_comparison_table(results_dict: dict) -> pd.DataFrame:
    """
    여러 전략의 성과 지표를 한눈에 비교하는 요약 데이터프레임을 생성합니다.

    Args:
        results_dict: {전략명: (df_result, initial_capital)}
    """
    rows = []
    for strat_name, (df_res, cap) in results_dict.items():
        m = calculate_metrics(df_res, cap)
        row = {
            '전략명': strat_name,
            '초기원금($)': f"${cap:,.0f}",
            '최종총자산($)': f"${m['final_asset']:,.0f}",
            '총수익률(%)': f"{m['total_return']:+.2f}%",
            'CAGR(%)': f"{m['cagr']:+.2f}%",
            '최대낙폭(MDD)': f"{m['mdd']:.2f}%",
            '샤프지수': f"{m['sharpe']:.2f}",
            '칼마비율': f"{m['calmar']:.2f}",
            '최종현금($)': f"${m['final_cash']:,.0f}",
            '보유수량(주)': f"{m['final_hold']:,}"
        }
        if m['final_ak'] is not None:
            row['위기준비금(AK)'] = f"${m['final_ak']:,.0f}"
        rows.append(row)

    return pd.DataFrame(rows)
