"""
Market Data Agent — collecte OHLC via yfinance, upsert TimescaleDB, pub Redis.
"""
import asyncio
import structlog
import pandas as pd
import yfinance as yf
from sqlalchemy import text
from app.services.yfinance_session import get_yf_session, yf_chart
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.services.redis_client import publish
from app.agents.watchlist_manager import get_active_tickers

logger = structlog.get_logger()

TIMEFRAME_PARAMS: dict[str, dict] = {
    "1d":  {"period": "1y",  "interval": "1d"},
    "1h":  {"period": "60d", "interval": "1h"},
    "15m": {"period": "5d",  "interval": "15m"},
}


def _yf_history(ticker: str, period: str, interval: str) -> pd.DataFrame:
    """Synchrone — appeler via asyncio.to_thread."""
    yfobj = yf.Ticker(ticker, session=get_yf_session())
    df = yfobj.history(period=period, interval=interval, auto_adjust=True)
    if df.empty:
        return df
    df.index = pd.to_datetime(df.index, utc=True)
    df.columns = [c.lower() for c in df.columns]
    return df[["open", "high", "low", "close", "volume"]]


async def fetch_ohlc(ticker: str, timeframe: str = "1d") -> pd.DataFrame:
    """Retourne un DataFrame OHLC indexé par timestamp UTC."""
    params = TIMEFRAME_PARAMS.get(timeframe, TIMEFRAME_PARAMS["1d"])
    return await asyncio.to_thread(_yf_history, ticker, params["period"], params["interval"])


async def upsert_ohlc(session: AsyncSession, asset_id: str, df: pd.DataFrame, timeframe: str = "1d") -> int:
    """
    Upsert OHLC en batch via raw SQL.
    ON CONFLICT DO UPDATE garantit l'idempotence.
    Retourne le nombre de lignes traitées.
    """
    if df.empty:
        return 0

    rows = [
        {
            "asset_id": asset_id,
            "timestamp": ts.to_pydatetime(),
            "timeframe": timeframe,
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": float(row["volume"]),
            "adj_close": float(row["close"]),
        }
        for ts, row in df.iterrows()
    ]

    await session.execute(
        text("""
            INSERT INTO ohlc_data
                (asset_id, timestamp, timeframe, open, high, low, close, volume, adj_close)
            VALUES
                (:asset_id, :timestamp, :timeframe, :open, :high, :low, :close, :volume, :adj_close)
            ON CONFLICT (asset_id, timestamp, timeframe) DO UPDATE SET
                open      = EXCLUDED.open,
                high      = EXCLUDED.high,
                low       = EXCLUDED.low,
                close     = EXCLUDED.close,
                volume    = EXCLUDED.volume,
                adj_close = EXCLUDED.adj_close
        """),
        rows,
    )
    return len(rows)


async def fetch_all_active_assets() -> None:
    """
    Entrée scheduler — fetch OHLC journalier pour tous les assets actifs,
    publie sur Redis après chaque mise à jour.
    Max 5 fetches simultanés pour ne pas surcharger yfinance.
    """
    async with AsyncSessionLocal() as session:
        tickers = await get_active_tickers(session)

    if not tickers:
        logger.debug("No active tickers — skipping OHLC fetch")
        return

    logger.info("Starting OHLC fetch", count=len(tickers))
    sem = asyncio.Semaphore(5)

    async def _process(ticker: str, asset_id: str) -> None:
        async with sem:
            try:
                df = await fetch_ohlc(ticker, timeframe="1d")
                if df.empty:
                    logger.warning("Empty OHLC from yfinance", ticker=ticker)
                    return
                async with AsyncSessionLocal() as session:
                    count = await upsert_ohlc(session, asset_id, df, "1d")
                    await session.commit()
                await publish(f"data:updated:{ticker}", {"ticker": ticker, "rows": count})
                logger.debug("OHLC updated", ticker=ticker, rows=count)
            except Exception:
                logger.exception("OHLC fetch failed", ticker=ticker)

    await asyncio.gather(*[_process(t, aid) for t, aid in tickers])
    logger.info("OHLC fetch complete", count=len(tickers))
    from app.services.redis_client import agent_heartbeat
    await agent_heartbeat("market_data", f"{len(tickers)} actifs")
