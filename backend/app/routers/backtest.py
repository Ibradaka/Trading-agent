import asyncio
from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.backtesting.engine import run_backtest
from app.services.outcome_tracker import get_accuracy_stats, get_ticker_accuracy

router = APIRouter()


@router.get("/stats")
async def accuracy_stats():
    """Stats globales d'accuracy depuis les outcomes trackés."""
    return await get_accuracy_stats()


@router.get("/{ticker}/accuracy")
async def ticker_accuracy(ticker: str):
    """Accuracy pour un ticker spécifique."""
    return await get_ticker_accuracy(ticker)


class MultiBacktestRequest(BaseModel):
    tickers: list[str]
    period: str = "5y"
    horizon_days: int = 20
    min_score: float = 65.0


@router.post("/multi")
async def multi_backtest(body: MultiBacktestRequest):
    """
    Backtest simultané sur plusieurs tickers.
    Retourne les résultats individuels + un tableau comparatif avec labels et recommandations.
    """
    tickers = [t.upper().strip() for t in body.tickers[:10]]  # max 10

    results = await asyncio.gather(*[
        run_backtest(t, period=body.period, min_fusion_score=body.min_score, horizon_days=body.horizon_days)
        for t in tickers
    ])

    comparison = []
    for r in results:
        if r.get("error"):
            comparison.append({"ticker": r.get("ticker", "?"), "error": r["error"]})
            continue
        m = r.get("metrics", {})
        d = r.get("diagnostics", {})
        comparison.append({
            "ticker": r["ticker"],
            "n_signals": r["total_signals"],
            "buy": r["buy_signals"],
            "sell": r["sell_signals"],
            "win_rate_pct": m.get("win_rate_pct"),
            "avg_return_pct": m.get("avg_return_pct"),
            "sharpe": m.get("sharpe_ratio"),
            "max_drawdown_pct": m.get("max_drawdown_pct"),
            "cumulative_return_pct": m.get("cumulative_return_pct"),
            "signal_freq_per_year": d.get("signal_quality", {}).get("signal_frequency_per_year"),
            "false_signal_rate_pct": d.get("signal_quality", {}).get("false_signal_rate_pct"),
            "stability_delta_pct": d.get("signal_quality", {}).get("stability_delta_pct"),
            "label": d.get("label"),
            "label_reason": d.get("label_reason"),
            "recommendation": d.get("recommendation"),
            "recommendation_reason": d.get("recommendation_reason"),
            "buy_win_rate_pct": d.get("by_signal_type", {}).get("BUY", {}).get("win_rate_pct"),
            "sell_win_rate_pct": d.get("by_signal_type", {}).get("SELL", {}).get("win_rate_pct"),
            "top_pattern": next(iter(d.get("patterns_analysis", {})), None),
        })

    # Triage : robustes d'abord, exclusions en dernier
    _order = {"robust": 0, "noisy": 1, "mixed": 2, "unstable": 3, "over_traded": 4, "bearish_asset": 5}
    comparison_sorted = sorted(
        [c for c in comparison if not c.get("error")],
        key=lambda x: _order.get(x.get("label", "mixed"), 2),
    )
    errors = [c for c in comparison if c.get("error")]

    return {
        "results": list(results),
        "comparison": comparison_sorted + errors,
    }


@router.get("/{ticker}")
async def backtest_ticker(
    ticker: str,
    period: str = Query(default="5y", description="Période yfinance : 1y, 2y, 5y"),
    horizon_days: int = Query(default=20, description="Horizon de mesure du retour (jours)"),
    min_score: float = Query(default=65.0, description="Score fusion minimum pour générer un signal"),
):
    """Lance un backtest walk-forward sur l'historique yfinance. Peut prendre quelques secondes."""
    return await run_backtest(
        ticker.upper(),
        period=period,
        min_fusion_score=min_score,
        horizon_days=horizon_days,
    )
