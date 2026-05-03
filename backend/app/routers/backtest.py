from fastapi import APIRouter, Query

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
