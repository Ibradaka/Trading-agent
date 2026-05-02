"""
Macro Contextualizer — FRED API → macro score 0-100 → Redis cache 6h.
Indicators: FEDFUNDS (Fed rate), T10Y2Y (yield curve spread), T10YIE (inflation expectations).
"""
import asyncio
import structlog
from datetime import datetime, timezone, timedelta

import httpx
from sqlalchemy import text

from app.config import settings
from app.database import AsyncSessionLocal
from app.services.redis_client import cache_get, cache_set

logger = structlog.get_logger()

_CACHE_KEY = "macro:score:global"
_CACHE_TTL = 6 * 3600  # 6h


async def _fetch_fred(series_id: str) -> float | None:
    """Fetch the latest non-null observation for a FRED series."""
    if not settings.fred_api_key:
        return None
    url = (
        "https://api.stlouisfed.org/fred/series/observations"
        f"?series_id={series_id}&api_key={settings.fred_api_key}"
        "&file_type=json&sort_order=desc&limit=3"
    )
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(url)
            r.raise_for_status()
            for obs in r.json().get("observations", []):
                if obs.get("value") not in (".", None, ""):
                    return float(obs["value"])
    except Exception as e:
        logger.warning("FRED fetch failed", series=series_id, error=str(e))
    return None


def _compute_score(
    fed_rate: float | None,
    t10y2y: float | None,
    t10yie: float | None,
) -> tuple[float, str]:
    """
    Compute macro score 0-100 from monetary context.
    50 = neutral, >50 = accommodative (bullish), <50 = restrictive (bearish).
    """
    score = 50.0
    factors: list[str] = []

    if fed_rate is not None:
        if fed_rate < 2.0:
            score += 8
            factors.append(f"taux Fed accommodants ({fed_rate:.1f}%)")
        elif fed_rate < 3.5:
            score += 3
            factors.append(f"taux Fed modérés ({fed_rate:.1f}%)")
        elif fed_rate < 5.0:
            score -= 3
            factors.append(f"taux Fed élevés ({fed_rate:.1f}%)")
        else:
            score -= 8
            factors.append(f"taux Fed restrictifs ({fed_rate:.1f}%)")

    if t10y2y is not None:
        if t10y2y < -0.5:
            score -= 12
            factors.append(f"courbe inversée ({t10y2y:.2f}% → signal récession)")
        elif t10y2y < 0:
            score -= 5
            factors.append(f"courbe légèrement inversée ({t10y2y:.2f}%)")
        elif t10y2y > 1.0:
            score += 5
            factors.append(f"courbe normalisée ({t10y2y:.2f}%)")
        else:
            factors.append(f"courbe aplatie ({t10y2y:.2f}%)")

    if t10yie is not None:
        if t10yie > 3.0:
            score -= 5
            factors.append(f"inflation attendue élevée ({t10yie:.1f}%)")
        elif t10yie < 2.0:
            score += 5
            factors.append(f"inflation attendue maîtrisée ({t10yie:.1f}%)")
        else:
            factors.append(f"inflation attendue cible ({t10yie:.1f}%)")

    score = max(10.0, min(90.0, round(score, 1)))
    narrative = "Contexte macro : " + (", ".join(factors) if factors else "données insuffisantes")
    return score, narrative


async def get_macro_score() -> tuple[float, str]:
    """Returns (score 0-100, narrative). Falls back to (50, '') if no data."""
    cached = await cache_get(_CACHE_KEY)
    if cached:
        return float(cached["score"]), cached.get("narrative", "")
    return 50.0, ""


async def update_macro_context() -> None:
    """Scheduler job — fetch FRED indicators → compute score → cache in Redis + persist to DB."""
    logger.info("Updating macro context from FRED")

    results = await asyncio.gather(
        _fetch_fred("FEDFUNDS"),
        _fetch_fred("T10Y2Y"),
        _fetch_fred("T10YIE"),
        return_exceptions=True,
    )

    fed_rate = results[0] if isinstance(results[0], float) else None
    t10y2y = results[1] if isinstance(results[1], float) else None
    t10yie = results[2] if isinstance(results[2], float) else None

    score, narrative = _compute_score(fed_rate, t10y2y, t10yie)
    payload = {
        "score": score,
        "narrative": narrative,
        "fed_rate": fed_rate,
        "t10y2y": t10y2y,
        "t10yie": t10yie,
    }
    await cache_set(_CACHE_KEY, payload, _CACHE_TTL)

    now = datetime.now(timezone.utc)
    expires = now + timedelta(hours=6)
    async with AsyncSessionLocal() as session:
        for name, value, unit in [
            ("FEDFUNDS", fed_rate, "%"),
            ("T10Y2Y", t10y2y, "%"),
            ("T10YIE", t10yie, "%"),
        ]:
            if value is None:
                continue
            await session.execute(
                text("""
                    INSERT INTO macro_context (id, timestamp, indicator_name, value, unit, source, expires_at)
                    VALUES (gen_random_uuid(), :ts, :name, :val, :unit, 'FRED', :exp)
                """),
                {"ts": now, "name": name, "val": value, "unit": unit, "exp": expires},
            )
        await session.commit()

    logger.info(
        "Macro context updated",
        score=score,
        fed_rate=fed_rate,
        t10y2y=t10y2y,
        t10yie=t10yie,
    )
