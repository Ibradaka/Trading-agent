"""
Pattern Detection Agent — chandeliers japonais (pandas-ta CDL) + figures chartistes custom.
Patterns détectés : engulfing, hammer, doji, morning/evening star, trois soldats/corbeaux,
double bottom/top, support/résistance dynamiques.
"""
import asyncio
import structlog
from datetime import timezone
from uuid import uuid4
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
from app.agents.technical import load_ohlc_df

logger = structlog.get_logger()


# ──────────────────────────────────────────────
# Chandeliers japonais via pandas-ta
# ──────────────────────────────────────────────

STRENGTH_BY_FAMILY: dict[str, float] = {
    "3WHITESOLDIERS": 0.90,
    "3BLACKCROWS":    0.90,
    "MORNINGSTAR":    0.88,
    "EVENINGSTAR":    0.88,
    "ENGULFING":      0.82,
    "HAMMER":         0.72,
    "SHOOTINGSTAR":   0.72,
    "INVERTEDHAMMER": 0.62,
    "HARAMI":         0.60,
    "MARUBOZU":       0.58,
    "DOJI":           0.35,
}


def _detect_cdl_patterns(df: pd.DataFrame) -> list[dict]:
    """Détecte les chandeliers sur les 3 dernières bougies via pandas-ta."""
    if not _TA_AVAILABLE or len(df) < 10:
        return []

    try:
        cdl = ta.cdl_pattern(df["open"], df["high"], df["low"], df["close"], name="all")
    except Exception as e:
        logger.debug("CDL detection error", error=str(e))
        return []

    if cdl is None or cdl.empty:
        return []

    results = []
    recent = cdl.tail(3)

    for col in recent.columns:
        non_zero = recent[col][recent[col] != 0]
        if non_zero.empty:
            continue

        last_val = non_zero.iloc[-1]
        last_ts = non_zero.index[-1]
        if hasattr(last_ts, "to_pydatetime"):
            last_ts = last_ts.to_pydatetime()

        direction = "bullish" if last_val > 0 else ("bearish" if last_val < 0 else "neutral")

        # Extraire le nom de famille pour trouver la force
        raw = col.replace("CDL_", "").upper()
        family = raw.split("_")[0]
        strength = STRENGTH_BY_FAMILY.get(family, 0.50)

        pattern_label = col.replace("CDL_", "").replace("_", " ").title()

        results.append({
            "timestamp": last_ts,
            "pattern_name": pattern_label,
            "direction": direction,
            "strength": strength,
            "description": f"Chandelier {pattern_label} ({direction})",
        })

    return results


# ──────────────────────────────────────────────
# Figures chartistes custom
# ──────────────────────────────────────────────

def _local_minima(series: pd.Series, order: int = 2) -> list[tuple[int, float]]:
    minima = []
    s = series.values
    for i in range(order, len(s) - order):
        if all(s[i] < s[i - k] for k in range(1, order + 1)) and \
           all(s[i] < s[i + k] for k in range(1, order + 1)):
            minima.append((i, float(s[i])))
    return minima


def _local_maxima(series: pd.Series, order: int = 2) -> list[tuple[int, float]]:
    maxima = []
    s = series.values
    for i in range(order, len(s) - order):
        if all(s[i] > s[i - k] for k in range(1, order + 1)) and \
           all(s[i] > s[i + k] for k in range(1, order + 1)):
            maxima.append((i, float(s[i])))
    return maxima


def _detect_double_bottom(df: pd.DataFrame, window: int = 60) -> list[dict]:
    """Double bottom (W) : deux creux similaires (±3%) séparés d'au moins 10 bougies."""
    if len(df) < window:
        return []

    recent_df = df.tail(window)
    lows = _local_minima(recent_df["low"], order=2)
    if len(lows) < 2:
        return []

    results = []
    close = float(df["close"].iloc[-1])

    for j in range(len(lows) - 1):
        idx1, v1 = lows[j]
        idx2, v2 = lows[j + 1]
        if idx2 - idx1 < 10:
            continue
        if abs(v1 - v2) / max(v1, v2) < 0.03 and close > max(v1, v2) * 1.005:
            results.append({
                "timestamp": df.index[-1].to_pydatetime(),
                "pattern_name": "Double Bottom",
                "direction": "bullish",
                "strength": 0.80,
                "description": f"Double creux ~{(v1 + v2) / 2:.2f} — breakout confirmé",
            })
            break   # un seul pattern par cycle

    return results


def _detect_double_top(df: pd.DataFrame, window: int = 60) -> list[dict]:
    """Double top (M) : deux sommets similaires (±3%) séparés d'au moins 10 bougies."""
    if len(df) < window:
        return []

    recent_df = df.tail(window)
    highs = _local_maxima(recent_df["high"], order=2)
    if len(highs) < 2:
        return []

    results = []
    close = float(df["close"].iloc[-1])

    for j in range(len(highs) - 1):
        idx1, v1 = highs[j]
        idx2, v2 = highs[j + 1]
        if idx2 - idx1 < 10:
            continue
        if abs(v1 - v2) / max(v1, v2) < 0.03 and close < min(v1, v2) * 0.995:
            results.append({
                "timestamp": df.index[-1].to_pydatetime(),
                "pattern_name": "Double Top",
                "direction": "bearish",
                "strength": 0.80,
                "description": f"Double sommet ~{(v1 + v2) / 2:.2f} — breakout baissier",
            })
            break

    return results


def _detect_support_resistance(
    df: pd.DataFrame,
    window: int = 50,
    tolerance: float = 0.02,
) -> list[dict]:
    """
    Identifie les niveaux de support/résistance via les pivots locaux.
    Retourne un pattern si le prix actuel est dans la zone de tolérance.
    """
    if len(df) < window:
        return []

    recent_df = df.tail(window)
    close = float(df["close"].iloc[-1])
    results = []

    pivot_highs = [v for _, v in _local_maxima(recent_df["high"], order=3)]
    pivot_lows  = [v for _, v in _local_minima(recent_df["low"],  order=3)]

    for level in pivot_highs:
        if abs(close - level) / level < tolerance:
            direction = "bearish" if close <= level else "bullish"
            results.append({
                "timestamp": df.index[-1].to_pydatetime(),
                "pattern_name": "Resistance",
                "direction": direction,
                "strength": 0.60,
                "description": f"Prix proche résistance {level:.2f}",
            })
            break

    for level in pivot_lows:
        if abs(close - level) / level < tolerance:
            direction = "bullish" if close >= level else "bearish"
            results.append({
                "timestamp": df.index[-1].to_pydatetime(),
                "pattern_name": "Support",
                "direction": direction,
                "strength": 0.60,
                "description": f"Prix proche support {level:.2f}",
            })
            break

    return results


def detect_all_patterns_sync(df: pd.DataFrame) -> list[dict]:
    """Point d'entrée synchrone — combine tous les détecteurs."""
    patterns: list[dict] = []
    patterns.extend(_detect_cdl_patterns(df))
    patterns.extend(_detect_double_bottom(df))
    patterns.extend(_detect_double_top(df))
    patterns.extend(_detect_support_resistance(df))
    return patterns


# ──────────────────────────────────────────────
# Persistance DB
# ──────────────────────────────────────────────

async def upsert_patterns(
    session: AsyncSession,
    asset_id: str,
    patterns: list[dict],
) -> None:
    """Supprime les patterns récents (48h) et réinsère."""
    # Purge les patterns des 48 dernières heures pour cet asset
    await session.execute(
        text("""
            DELETE FROM detected_patterns
            WHERE asset_id = :asset_id
              AND timestamp >= NOW() - INTERVAL '48 hours'
        """),
        {"asset_id": asset_id},
    )

    for p in patterns:
        ts = p["timestamp"]
        # Garantir que le timestamp est timezone-aware
        if hasattr(ts, "tzinfo") and ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)

        await session.execute(
            text("""
                INSERT INTO detected_patterns
                    (id, asset_id, timestamp, pattern_name, direction, strength, description)
                VALUES
                    (:id, :asset_id, :timestamp, :pattern_name, :direction, :strength, :description)
            """),
            {
                "id": str(uuid4()),
                "asset_id": asset_id,
                "timestamp": ts,
                "pattern_name": p["pattern_name"],
                "direction": p["direction"],
                "strength": p["strength"],
                "description": p.get("description", ""),
            },
        )


# ──────────────────────────────────────────────
# Entrée scheduler
# ──────────────────────────────────────────────

async def detect_all_patterns() -> None:
    """Détecte les patterns pour tous les assets actifs."""
    async with AsyncSessionLocal() as session:
        tickers = await get_active_tickers(session)

    if not tickers:
        return

    logger.info("Detecting patterns", count=len(tickers))

    async def _process(ticker: str, asset_id: str) -> None:
        try:
            async with AsyncSessionLocal() as session:
                df = await load_ohlc_df(session, asset_id, limit=120)

            if df.empty or len(df) < 20:
                return

            patterns = await asyncio.to_thread(detect_all_patterns_sync, df)

            async with AsyncSessionLocal() as session:
                await upsert_patterns(session, asset_id, patterns)
                await session.commit()

            if patterns:
                await publish(f"patterns:updated:{ticker}", {
                    "ticker": ticker,
                    "count": len(patterns),
                    "names": [p["pattern_name"] for p in patterns[:5]],
                })

            logger.debug("Patterns done", ticker=ticker, count=len(patterns))
        except Exception:
            logger.exception("Pattern detection failed", ticker=ticker)

    await asyncio.gather(*[_process(t, aid) for t, aid in tickers])
    logger.info("Patterns complete", count=len(tickers))
    from app.services.redis_client import agent_heartbeat
    await agent_heartbeat("patterns", f"{len(tickers)} actifs")
