from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from uuid import UUID

from app.database import get_session
from app.models.db import Signal, Asset, Watchlist, WatchlistAsset

router = APIRouter()


def _format_signal(signal: Signal, asset: Asset) -> dict:
    return {
        "id": str(signal.id),
        "ticker": asset.ticker,
        "asset_name": asset.name,
        "signal_type": signal.signal_type,
        "strength": signal.strength,
        "composite_score": signal.composite_score,
        "confidence": signal.confidence,
        "scores": {
            "technical": signal.technical_score,
            "patterns": signal.pattern_score,
            "sentiment": signal.sentiment_score,
            "macro": signal.macro_score,
            "momentum": signal.momentum_score,
        },
        "reasoning": signal.reasoning,
        "risks": signal.risks,
        "invalidation_conditions": signal.invalidation_conditions,
        "horizon": signal.horizon,
        "timestamp": signal.timestamp.isoformat() if signal.timestamp else None,
        "is_active": signal.is_active,
    }


@router.get("/{ticker}/latest")
async def get_latest_signal(ticker: str, db: AsyncSession = Depends(get_session)):
    """Retourne le dernier signal actif pour un ticker."""
    asset_result = await db.execute(select(Asset).where(Asset.ticker == ticker.upper()))
    asset = asset_result.scalar_one_or_none()
    if not asset:
        raise HTTPException(status_code=404, detail=f"Asset {ticker} not found")

    signal_result = await db.execute(
        select(Signal)
        .where(Signal.asset_id == asset.id, Signal.is_active == True)
        .order_by(desc(Signal.timestamp))
        .limit(1)
    )
    signal = signal_result.scalar_one_or_none()
    if not signal:
        return {"ticker": ticker.upper(), "signal": None, "message": "No signal generated yet"}

    return _format_signal(signal, asset)


@router.get("/{ticker}/history")
async def get_signal_history(
    ticker: str,
    limit: int = Query(default=20, le=100),
    db: AsyncSession = Depends(get_session),
):
    """Retourne l'historique des signaux pour un ticker."""
    asset_result = await db.execute(select(Asset).where(Asset.ticker == ticker.upper()))
    asset = asset_result.scalar_one_or_none()
    if not asset:
        raise HTTPException(status_code=404, detail=f"Asset {ticker} not found")

    signals_result = await db.execute(
        select(Signal)
        .where(Signal.asset_id == asset.id)
        .order_by(desc(Signal.timestamp))
        .limit(limit)
    )
    signals = signals_result.scalars().all()
    return [_format_signal(s, asset) for s in signals]


@router.get("/watchlist/{watchlist_id}")
async def get_watchlist_signals(watchlist_id: UUID, db: AsyncSession = Depends(get_session)):
    """Retourne les derniers signaux actifs pour tous les actifs d'une watchlist."""
    wl_result = await db.execute(select(Watchlist).where(Watchlist.id == watchlist_id))
    if not wl_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Watchlist not found")

    result = await db.execute(
        select(Asset, WatchlistAsset)
        .join(WatchlistAsset, WatchlistAsset.asset_id == Asset.id)
        .where(WatchlistAsset.watchlist_id == watchlist_id, WatchlistAsset.is_active == True)
    )
    assets = result.all()

    signals_data = []
    for asset, wa in assets:
        signal_result = await db.execute(
            select(Signal)
            .where(Signal.asset_id == asset.id, Signal.is_active == True)
            .order_by(desc(Signal.timestamp))
            .limit(1)
        )
        signal = signal_result.scalar_one_or_none()
        signals_data.append({
            "ticker": asset.ticker,
            "name": asset.name,
            "is_pea_eligible": asset.is_pea_eligible,
            "asset_type": asset.asset_type,
            "signal": _format_signal(signal, asset) if signal else None,
        })

    return signals_data
