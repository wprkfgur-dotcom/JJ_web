"""
백테스트 라우터
"""
from fastapi import APIRouter, HTTPException

from core.backtest_runner import build_chart_series, run_strategies
from core.data import fetch_market_data

from ..schemas import BacktestRequest
from ..utils import sanitize_for_json

router = APIRouter()

# 웅덩이 매매법(120일선) 등 장기 이동평균 전략을 위해 시작일 이전 데이터를 충분히 확보한다.
WARMUP_DAYS = 180

METRIC_FLOAT_KEYS = ("total_return", "cagr", "mdd", "sharpe", "calmar", "final_cash", "final_asset")


def _build_strategy_payload(item: dict, capital: float) -> dict:
    """전략 1개의 시뮬레이션 결과를 응답 형태(지표 + 차트 시리즈)로 변환"""
    metrics, df_res = item["metrics"], item["df"]
    chart_series = build_chart_series(df_res)

    # Drawdown (낙폭 MDD 추이)
    cummax = df_res["Asset"].cummax()
    dd_series = ((df_res["Asset"] - cummax) / cummax * 100.0).round(2).tolist()

    return {
        "name": item["name"],
        "metrics": {
            "initial_capital": float(metrics.get("initial_capital", capital)),
            **{k: float(metrics.get(k, 0.0)) for k in METRIC_FLOAT_KEYS},
            "final_hold": int(metrics.get("final_hold", 0)),
            "trading_days": int(metrics.get("trading_days", len(df_res))),
        },
        "chart": {
            "dates": chart_series["dates"],
            "assets": chart_series["vals"],
            "drawdowns": dd_series,
        },
    }


@router.post("/api/backtest/run")
async def run_backtest_simulation(req: BacktestRequest):
    """백테스트 실행: 시세 다운로드 → 전략별 시뮬레이션 → 성과 지표 산출 → 차트 시리즈 반환"""
    ticker = req.ticker.strip().upper()
    try:
        df_market = fetch_market_data(
            ticker, req.start_date, req.end_date,
            warmup_days=WARMUP_DAYS, use_adj_close=req.use_adj_close,
        )
        if df_market.empty:
            raise HTTPException(status_code=400, detail=f"[{ticker}] 기간 내 시세 데이터를 가져올 수 없습니다.")

        # 비교군(무한매수법, VR5.0, 웅덩이 매매법, 단순보유법) 및 종종이 전략 기본 보장
        base_strategies = [
            "종종이 전략",
            "무한매수법 v4.0",
            "VR 5.0 (밸류리밸런싱)",
            "웅덩이 매매법",
            f"{ticker} 단순보유(B&H)",
        ]

        # 요청에 전략 목록이 있으면 순서를 존중하되, 누락된 비교군 전략들을 자동으로 추가
        target_strategies = list(req.strategies) if req.strategies else list(base_strategies)
        for bs in base_strategies:
            # 부분 문자열 매칭으로 중복 추가 방지
            bs_key = "종종" if "종종" in bs else ("무한" if "무한" in bs else ("VR" if "VR" in bs else ("웅덩이" if "웅덩이" in bs else "단순보유")))
            if not any(bs_key in existing for existing in target_strategies):
                target_strategies.append(bs)

        results = run_strategies(
            df_market=df_market,
            ticker=ticker,
            capital=req.capital,
            start_date=req.start_date,
            end_date=req.end_date,
            strategy_names=target_strategies,
            jongjong_params=req.jongjong_params,
        )

        return sanitize_for_json({
            "ticker": ticker,
            "capital": req.capital,
            "start_date": req.start_date,
            "end_date": req.end_date,
            "use_adj_close": req.use_adj_close,
            "strategies": [_build_strategy_payload(item, req.capital) for item in results],
        })

    except Exception as e:
        print(f"백테스트 실행 오류: {e}")
        raise HTTPException(status_code=500, detail=f"백테스트 실행 중 오류 발생: {str(e)}")
