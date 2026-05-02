"""
Seed de démarrage — crée la watchlist par défaut si aucune n'existe.
Idempotent : ne s'exécute qu'une seule fois (si 0 watchlist en base).
"""
import asyncio
import uuid
import structlog
from sqlalchemy import select, func

from app.database import AsyncSessionLocal
from app.models.db import Watchlist, Asset, WatchlistAsset
from app.services.yfinance_session import yf_chart, yf_quote_summary

logger = structlog.get_logger()

DEFAULT_TICKERS = [
    ("ISLN.L", "iShares Physical Silver ETC", True),
    ("NVDA", "NVIDIA Corporation", False),
]


def _fetch_info(ticker: str) -> dict:
    meta = yf_chart(ticker)
    summary = yf_quote_summary(ticker)
    price_data = summary.get("price", {})
    profile = summary.get("summaryProfile", {}) or summary.get("assetProfile", {})
    return {
        "price": (price_data.get("regularMarketPrice") or {}).get("raw") or meta.get("regularMarketPrice"),
        "currency": price_data.get("currency") or meta.get("currency"),
        "exchange": price_data.get("exchange") or meta.get("exchangeName"),
        "name": price_data.get("longName") or price_data.get("shortName") or meta.get("symbol") or ticker,
        "sector": profile.get("sector"),
        "country": profile.get("country"),
    }


async def _seed_ticker(session, watchlist, ticker: str, notes: str, pea: bool) -> None:
    info = await asyncio.to_thread(_fetch_info, ticker)
    if not info["price"]:
        logger.warning("Seed: ticker sans prix", ticker=ticker)
        return

    existing = (await session.execute(select(Asset).where(Asset.ticker == ticker))).scalar_one_or_none()
    if existing is None:
        existing = Asset(
            id=uuid.uuid4(),
            ticker=ticker,
            name=info["name"],
            asset_type="equity",
            exchange=info["exchange"],
            currency=info["currency"],
            sector=info["sector"],
            country=info["country"],
            is_pea_eligible=pea,
            metadata_={"current_price": info["price"]},
        )
        session.add(existing)
        await session.flush()

    already_linked = (await session.execute(
        select(WatchlistAsset).where(
            WatchlistAsset.watchlist_id == watchlist.id,
            WatchlistAsset.asset_id == existing.id,
        )
    )).scalar_one_or_none()

    if not already_linked:
        session.add(WatchlistAsset(watchlist_id=watchlist.id, asset_id=existing.id, notes=notes))
        await session.flush()
        logger.info("Seed: ticker ajouté", ticker=ticker, price=info["price"])


async def run_seed() -> None:
    try:
        async with AsyncSessionLocal() as session:
            count = (await session.execute(select(func.count(Watchlist.id)))).scalar()

            if count == 0:
                watchlist = Watchlist(
                    id=uuid.uuid4(),
                    name="Mon PEA",
                    description="Métaux précieux & Tech — ETCs iShares + NASDAQ",
                    refresh_interval_minutes=15,
                    signal_threshold=70,
                )
                session.add(watchlist)
                await session.flush()
            else:
                watchlist = (await session.execute(select(Watchlist))).scalar_one()

            for ticker, notes, pea in DEFAULT_TICKERS:
                await _seed_ticker(session, watchlist, ticker, notes, pea)

            await session.commit()
            logger.info("Seed terminé", watchlist=watchlist.name)

    except Exception as e:
        logger.warning("Seed ignoré (race condition ou déjà effectué)", error=str(e))
