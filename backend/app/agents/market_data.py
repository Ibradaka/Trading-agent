"""
Market Data Agent — collecte OHLC via curl_cffi (contourne blocage datacenter), upsert DB, pub Redis.
"""
import asyncio
import structlog
import pandas as pd
from sqlalchemy import text
from app.services.yfinance_session import get_yf_session
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.services.redis_client import publish
from app.agents.watchlist_manager import get_active_tickers

logger = structlog.get_logger()

TIMEFRAME_PARAMS: dict[str, dict] = {
    "1d":  {"interval": "1d", "range": "1y"},
    "1h":  {"interval": "1h", "range": "60d"},
    "15m": {"interval": "15m", "range": "5d"},
}


def _yf_history(ticker: str, interval: str, range_: str) -> pd.DataFrame:
    """Synchrone — fetch OHLC via curl_cffi direct (pas yf.Ticker)."""
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
        f"?interval={interval}&range={range_}"
    )
    try:
        r = get_yf_session().get(url, timeout=20)
        result = (r.json().get("chart", {}).get("result") or [None])[0]
        if not result:
            return pd.DataFrame()
        timestamps = result.get("timestamp") or []
        q = (result.get("indicators", {}).get("quote") or [{}])[0]
        adj_list = (result.get("indicators", {}).get("adjclose") or [{}])[0].get("adjclose") or []
        rows = []
        for i, ts in enumerate(timestamps):
            close_raw = q.get("close", [])[i] if i < len(q.get("close", [])) else None
            close_adj = adj_list[i] if adj_list and i < len(adj_list) else close_raw
            if close_adj is None:
                continue
            rows.append({
                "timestamp": pd.Timestamp(ts, unit="s", tz="UTC"),
                "open":   q.get("open",   [])[i] if i < len(q.get("open",   [])) else None,
                "high":   q.get("high",   [])[i] if i < len(q.get("high",   [])) else None,
                "low":    q.get("low",    [])[i] if i < len(q.get("low",    [])) else None,
                "close":  close_adj,
                "volume": q.get("volume", [])[i] if i < len(q.get("volume", [])) else 0,
            })
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows).set_index("timestamp")
        return df[["open", "high", "low", "close", "volume"]]
    except Exception as e:
        logger.warning("curl_cffi fetch failed", ticker=ticker, error=str(e))
        return pd.DataFrame()


async def fetch_ohlc(ticker: str, timeframe: str = "1d") -> pd.DataFrame:
    """Retourne un DataFrame OHLC indexé par timestamp UTC."""
    params = TIMEFRAME_PARAMS.get(timeframe, TIMEFRAME_PARAMS["1d"])
    return await asyncio.to_thread(_yf_history, ticker, params["interval"], params["range"])


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
