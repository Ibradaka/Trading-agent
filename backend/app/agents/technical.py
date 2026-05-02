"""
Technical Analysis Agent — indicateurs pandas-ta, upsert DB, pub Redis.
"""
import asyncio
import structlog
import pandas as pd
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

try:
    import pandas_ta as ta
    _TA_AVAILABLE = True
except ImportError:
    ta = None
    _TA_AVAILABLE = False

from app.database import AsyncSessionLocal
from app.services.redis_client import publish
from app.agents.watchlist_manager import get_active_tickers
from app.scoring.technical import compute_technical_score, compute_momentum_score

logger = structlog.get_logger()


async def load_ohlc_df(
    session: AsyncSession,
    asset_id: str,
    timeframe: str = "1d",
    limit: int = 250,
) -> pd.DataFrame:
    """Charge les N dernières bougies depuis la DB (ordre chronologique)."""
    result = await session.execute(
        text("""
            SELECT timestamp, open, high, low, close, volume
            FROM ohlc_data
            WHERE asset_id = :asset_id AND timeframe = :timeframe
            ORDER BY timestamp DESC
            LIMIT :limit
        """),
        {"asset_id": asset_id, "timeframe": timeframe, "limit": limit},
    )
    rows = result.fetchall()
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df = df.sort_values("timestamp").set_index("timestamp")
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def _last(series: "pd.Series | None") -> float | None:
    if series is None or series.empty:
        return None
    val = series.iloc[-1]
    return float(val) if pd.notna(val) else None


def _last_col(df_part: "pd.DataFrame | None", col: str) -> float | None:
    if df_part is None or col not in df_part.columns:
        return None
    return _last(df_part[col])


def compute_indicators(df: pd.DataFrame) -> dict | None:
    """
    Calcule tous les indicateurs techniques sur le DataFrame OHLC.
    Synchrone — appeler via asyncio.to_thread pour ne pas bloquer l'event loop.
    Retourne None si les données sont insuffisantes (< 26 bougies).
    """
    if not _TA_AVAILABLE:
        raise RuntimeError("pandas-ta non installé — pip install pandas-ta")
    if len(df) < 26:
        return None

    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]

    ema20 = ta.ema(close, length=20)
    ema50 = ta.ema(close, length=50)
    ema200 = ta.ema(close, length=200)
    sma20 = ta.sma(close, length=20)
    sma50 = ta.sma(close, length=50)
    sma200 = ta.sma(close, length=200)

    rsi = ta.rsi(close, length=14)
    macd_df = ta.macd(close, fast=12, slow=26, signal=9)
    stoch_df = ta.stoch(high, low, close, k=14, d=3)
    willr = ta.willr(high, low, close, length=14)

    bb_df = ta.bbands(close, length=20, std=2)
    atr = ta.atr(high, low, close, length=14)

    obv = ta.obv(close, volume)
    adx_df = ta.adx(high, low, close, length=14)

    # Noms de colonnes générés par pandas-ta
    macd_col  = "MACD_12_26_9"
    macds_col = "MACDs_12_26_9"
    macdh_col = "MACDh_12_26_9"
    stochk_col = "STOCHk_14_3_3"
    stochd_col = "STOCHd_14_3_3"
    bbl_col   = "BBL_20_2.0"
    bbm_col   = "BBM_20_2.0"
    bbu_col   = "BBU_20_2.0"
    adx_col   = "ADX_14"

    # Valeur précédente de macd_histogram (pour détecter le croisement)
    prev_macd_hist = None
    if macd_df is not None and macdh_col in macd_df.columns and len(macd_df) >= 2:
        val = macd_df[macdh_col].iloc[-2]
        prev_macd_hist = float(val) if pd.notna(val) else None

    prev_stoch_k = None
    if stoch_df is not None and stochk_col in stoch_df.columns and len(stoch_df) >= 2:
        val = stoch_df[stochk_col].iloc[-2]
        prev_stoch_k = float(val) if pd.notna(val) else None

    vol_series = volume.tail(20)
    volume_ma20 = float(vol_series.mean()) if len(vol_series) >= 5 else None

    return {
        # Trend
        "ema20":  _last(ema20),
        "ema50":  _last(ema50),
        "ema200": _last(ema200),
        "sma20":  _last(sma20),
        "sma50":  _last(sma50),
        "sma200": _last(sma200),
        # Momentum
        "rsi":            _last(rsi),
        "macd":           _last_col(macd_df, macd_col),
        "macd_signal":    _last_col(macd_df, macds_col),
        "macd_histogram": _last_col(macd_df, macdh_col),
        "stoch_k":        _last_col(stoch_df, stochk_col),
        "stoch_d":        _last_col(stoch_df, stochd_col),
        "williams_r":     _last(willr),
        # Volatility
        "bb_upper":  _last_col(bb_df, bbu_col),
        "bb_middle": _last_col(bb_df, bbm_col),
        "bb_lower":  _last_col(bb_df, bbl_col),
        "atr":       _last(atr),
        # Volume
        "obv": _last(obv),
        "adx": _last_col(adx_df, adx_col),
        # Extras pour scoring
        "close":           float(df["close"].iloc[-1]),
        "volume":          float(df["volume"].iloc[-1]),
        "volume_ma20":     volume_ma20,
        "prev_macd_histogram": prev_macd_hist,
        "prev_stoch_k":    prev_stoch_k,
    }


async def upsert_indicators(
    session: AsyncSession,
    asset_id: str,
    timestamp: object,
    indicators: dict,
    timeframe: str = "1d",
) -> None:
    await session.execute(
        text("""
            INSERT INTO technical_indicators (
                asset_id, timestamp, timeframe,
                ema20, ema50, ema200, sma20, sma50, sma200,
                rsi, macd, macd_signal, macd_histogram,
                stoch_k, stoch_d, williams_r,
                bb_upper, bb_middle, bb_lower,
                atr, obv, adx
            ) VALUES (
                :asset_id, :timestamp, :timeframe,
                :ema20, :ema50, :ema200, :sma20, :sma50, :sma200,
                :rsi, :macd, :macd_signal, :macd_histogram,
                :stoch_k, :stoch_d, :williams_r,
                :bb_upper, :bb_middle, :bb_lower,
                :atr, :obv, :adx
            )
            ON CONFLICT (asset_id, timestamp, timeframe) DO UPDATE SET
                ema20 = EXCLUDED.ema20, ema50 = EXCLUDED.ema50, ema200 = EXCLUDED.ema200,
                sma20 = EXCLUDED.sma20, sma50 = EXCLUDED.sma50, sma200 = EXCLUDED.sma200,
                rsi = EXCLUDED.rsi, macd = EXCLUDED.macd,
                macd_signal = EXCLUDED.macd_signal, macd_histogram = EXCLUDED.macd_histogram,
                stoch_k = EXCLUDED.stoch_k, stoch_d = EXCLUDED.stoch_d,
                williams_r = EXCLUDED.williams_r,
                bb_upper = EXCLUDED.bb_upper, bb_middle = EXCLUDED.bb_middle,
                bb_lower = EXCLUDED.bb_lower,
                atr = EXCLUDED.atr, obv = EXCLUDED.obv, adx = EXCLUDED.adx
        """),
        {
            "asset_id": asset_id,
            "timestamp": timestamp,
            "timeframe": timeframe,
            **{k: indicators.get(k) for k in [
                "ema20", "ema50", "ema200", "sma20", "sma50", "sma200",
                "rsi", "macd", "macd_signal", "macd_histogram",
                "stoch_k", "stoch_d", "williams_r",
                "bb_upper", "bb_middle", "bb_lower",
                "atr", "obv", "adx",
            ]},
        },
    )


async def compute_all_indicators() -> None:
    """Entrée scheduler — calcule les indicateurs pour tous les assets actifs."""
    async with AsyncSessionLocal() as session:
        tickers = await get_active_tickers(session)

    if not tickers:
        return

    logger.info("Computing indicators", count=len(tickers))

    async def _process(ticker: str, asset_id: str) -> None:
        try:
            async with AsyncSessionLocal() as session:
                df = await load_ohlc_df(session, asset_id)

            if df.empty or len(df) < 26:
                logger.debug("Insufficient OHLC data", ticker=ticker, rows=len(df))
                return

            indicators = await asyncio.to_thread(compute_indicators, df)
            if indicators is None:
                return

            tech_score = compute_technical_score(indicators)
            mom_score = compute_momentum_score(indicators)
            timestamp = df.index[-1].to_pydatetime()

            async with AsyncSessionLocal() as session:
                await upsert_indicators(session, asset_id, timestamp, indicators)
                await session.commit()

            await publish(f"indicators:updated:{ticker}", {
                "ticker": ticker,
                "technical_score": round(tech_score, 1),
                "momentum_score": round(mom_score, 1),
                "rsi": indicators.get("rsi"),
                "macd_histogram": indicators.get("macd_histogram"),
            })
            logger.debug("Indicators computed", ticker=ticker, tech=tech_score, mom=mom_score)
        except Exception:
            logger.exception("Indicator computation failed", ticker=ticker)

    await asyncio.gather(*[_process(t, aid) for t, aid in tickers])
    logger.info("Indicators done", count=len(tickers))
