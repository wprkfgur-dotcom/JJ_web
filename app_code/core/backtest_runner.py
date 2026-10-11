"""
백테스트 실행 엔진 (UI 비의존)

시세 데이터 → 전략별 시뮬레이션 → 성과 지표 → 차트 시리즈 데이터 생성까지의 순수 로직입니다.
UI는 진행 상황 콜백(on_progress)과 결과 dict만 사용합니다.
"""
from typing import Callable, Dict, List, Optional, Sequence

import pandas as pd

from core.metrics import calculate_metrics
from core.strategy_registry import create_backtest_strategy


def run_strategies(
    df_market: pd.DataFrame,
    ticker: str,
    capital: float,
    start_date: str,
    end_date: str,
    strategy_names: Sequence[str],
    on_progress: Optional[Callable[[str], None]] = None,
) -> List[Dict]:
    """선택된 전략들을 순서대로 실행하고 결과 목록을 반환합니다.

    Returns:
        [{'name': str, 'metrics': dict, 'df': DataFrame}, ...]  (입력 순서 유지)
    """
    results = []
    for name in strategy_names:
        if on_progress:
            on_progress(name)
        strat = create_backtest_strategy(name, ticker, capital)
        df_s = strat.run(df_market, start_date, end_date)
        results.append({
            'name': name,
            'metrics': calculate_metrics(df_s, capital),
            'df': df_s,
        })
    return results


def build_chart_series(df_result: pd.DataFrame) -> Dict[str, list]:
    """전략 결과 DataFrame을 차트용 날짜 라벨/자산 값 리스트로 변환합니다.

    1년(365행) 초과 시 '%y/%m', 이하이면 '%m/%d' 형식의 라벨을 사용합니다.
    """
    date_fmt = '%y/%m' if len(df_result) > 365 else '%m/%d'
    return {
        'dates': [pd.to_datetime(d).strftime(date_fmt) for d in df_result['Date']],
        'vals': df_result['Asset'].values.tolist(),
    }
