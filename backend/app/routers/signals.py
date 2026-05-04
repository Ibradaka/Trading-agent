from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, text
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


@router.get("/recent")
async def get_recent_signals(
    limit: int = Query(default=50, le=200),
    db: AsyncSession = Depends(get_session),
):
    """Signaux récents BUY/SELL toutes watchlists, avec outcome si disponible."""
    from app.services.outcome_tracker import get_recent_signals_with_outcomes
    return await get_recent_signals_with_outcomes(limit=limit)


@router.get("/active")
async def get_active_signals(db: AsyncSession = Depends(get_session)):
    """Retourne tous les signaux BUY/SELL actifs triés par score décroissant."""
    result = await db.execute(
        select(Signal, Asset)
        .join(Asset, Asset.id == Signal.asset_id)
        .where(
            Signal.is_active == True,
            Signal.signal_type.in_(["BUY", "SELL"]),
        )
        .order_by(desc(Signal.composite_score))
        .limit(20)
    )
    rows = result.all()
    return [_format_signal(signal, asset) for signal, asset in rows]


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


@router.get("/{signal_id}/outcome")
async def get_signal_outcome(signal_id: str, db: AsyncSession = Depends(get_session)):
    """Retourne les outcomes disponibles pour un signal (J+5, J+10, J+20)."""
    result = await db.execute(
        text("""
            SELECT days_elapsed, actual_return_pct, was_correct, outcome_checked_at
            FROM signal_outcomes
            WHERE signal_id = :sid
            ORDER BY days_elapsed ASC
        """),
        {"sid": signal_id},
    )
    rows = result.fetchall()
    return [
        {
            "days_elapsed": r.days_elapsed,
            "return_pct": float(r.actual_return_pct) if r.actual_return_pct is not None else None,
            "was_correct": r.was_correct,
            "checked_at": r.outcome_checked_at.isoformat() if r.outcome_checked_at else None,
        }
        for r in rows
    ]


@router.get("/watchlist/{watchlist_id}")
async def get_watchlist_signals(watchlist_id: UUID, db: AsyncSession = Depends(get_session)):
    """Retourne les derniers signaux actifs pour tous les actifs d'une watchlist.
    Fallback sur le cache Redis pour les actifs sans signal DB (HOLD courant)."""
    from app.services.redis_client import cache_get

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

        if signal:
            signal_payload = _format_signal(signal, asset)
        else:
            # Fallback Redis : affiche l'état HOLD courant du pipeline
            cached = await cache_get(f"signal:{asset.ticker.upper()}")
            if cached:
                signal_payload = {
                    "id": None,
                    "ticker": asset.ticker,
                    "asset_name": asset.name,
                    "signal_type": cached.get("signal_type", "HOLD"),
                    "strength": cached.get("signal_strength", "weak"),
                    "composite_score": cached.get("fusion_score"),
                    "confidence": cached.get("confidence"),
                    "asset_label": cached.get("asset_label", "unknown"),
                    "scores": {
                        "technical": cached.get("technical_score"),
                        "patterns": cached.get("pattern_score"),
                        "sentiment": cached.get("sentiment_score"),
                        "macro": cached.get("macro_score"),
                        "momentum": cached.get("momentum_score"),
                    },
                    "reasoning": None,
                    "risks": None,
                    "invalidation_conditions": None,
                    "horizon": None,
                    "timestamp": cached.get("timestamp"),
                    "is_active": True,
                }
            else:
                signal_payload = None

        signals_data.append({
            "ticker": asset.ticker,
            "name": asset.name,
            "is_pea_eligible": asset.is_pea_eligible,
            "asset_type": asset.asset_type,
            "signal": signal_payload,
        })

    return signals_data
