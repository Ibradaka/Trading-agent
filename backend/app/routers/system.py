"""
Settings router — lecture/écriture configuration dynamique via Redis hash.
Toutes les valeurs survivent aux redémarrages (Redis volume Docker persistant).
"""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter

from app.config import settings
from app.services.redis_client import get_redis

router = APIRouter()

_SETTINGS_KEY = "settings:global"
_PANIC_KEY = "system:panic"

_DEFAULTS = {
    "telegram_enabled": "true",
    "panic_mode": "false",
    "alert_threshold": "0.70",
    "min_confidence": "0.40",
    "cooldown_minutes": "120",
    "quiet_start": "22",
    "quiet_end": "7",
    "daily_digest": "true",
    "buy_threshold": "65.0",
    "sell_threshold": "45.0",
}


async def _load() -> dict:
    r = get_redis()
    stored = await r.hgetall(_SETTINGS_KEY)
    merged = {**_DEFAULTS, **stored}
    return {
        "telegram_enabled": merged["telegram_enabled"] == "true",
        "panic_mode": merged["panic_mode"] == "true",
        "alert_threshold": float(merged["alert_threshold"]),
        "min_confidence": float(merged["min_confidence"]),
        "cooldown_minutes": int(merged["cooldown_minutes"]),
        "quiet_start": int(merged["quiet_start"]),
        "quiet_end": int(merged["quiet_end"]),
        "daily_digest": merged["daily_digest"] == "true",
        "buy_threshold": float(merged["buy_threshold"]),
        "sell_threshold": float(merged["sell_threshold"]),
    }


async def get_settings() -> dict:
    """Utilisé par d'autres modules (telegram, risk)."""
    return await _load()


async def is_panic_mode() -> bool:
    r = get_redis()
    val = await r.hget(_SETTINGS_KEY, "panic_mode")
    return val == "true"


@router.get("")
async def read_settings():
    return await _load()


@router.patch("")
async def update_settings(body: dict):
    r = get_redis()
    allowed = set(_DEFAULTS.keys())
    to_save = {}
    for k, v in body.items():
        if k not in allowed:
            continue
        if isinstance(v, bool):
            to_save[k] = "true" if v else "false"
        else:
            to_save[k] = str(v)
    if to_save:
        await r.hset(_SETTINGS_KEY, mapping=to_save)
    return await _load()


@router.post("/panic")
async def toggle_panic():
    current = await is_panic_mode()
    new_val = not current
    r = get_redis()
    await r.hset(_SETTINGS_KEY, "panic_mode", "true" if new_val else "false")
    return {"panic_mode": new_val}


@router.get("/status")
async def system_status():
    """État opérationnel global du système."""
    from app.services.redis_client import cache_get
    from app.services.scheduler import is_market_open
    from app.database import AsyncSessionLocal
    from sqlalchemy import text

    cfg = await _load()

    # Dernier signal en DB
    last_signal_at = None
    try:
        async with AsyncSessionLocal() as session:
            row = await session.execute(
                text("SELECT MAX(created_at) FROM signals")
            )
            val = row.scalar()
            if val:
                last_signal_at = val.isoformat()
    except Exception:
        pass

    # Cache sentiment
    sentiment_cached = await cache_get("sentiment:cache:global") is not None

    # Cache macro
    macro_cached = await cache_get("macro:cache:global") is not None

    return {
        "panic_mode": cfg["panic_mode"],
        "telegram_enabled": cfg["telegram_enabled"],
        "market_open": is_market_open(),
        "last_signal_at": last_signal_at,
        "sentiment_available": sentiment_cached,
        "macro_available": macro_cached,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


_AGENT_META = {
    "market_data": {"label": "Market Data",  "icon": "📥"},
    "technical":   {"label": "Technical",    "icon": "📊"},
    "patterns":    {"label": "Patterns",     "icon": "🕯"},
    "sentiment":   {"label": "Sentiment",    "icon": "📰"},
    "macro":       {"label": "Macro FRED",   "icon": "🏦"},
    "risk_score":  {"label": "Risk/Score",   "icon": "⚡"},
    "llm":         {"label": "LLM",          "icon": "🤖"},
}


@router.get("/agents")
async def agents_status():
    """Statut de la dernière exécution de chaque agent (lu depuis Redis)."""
    from app.services.redis_client import cache_get
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    result = []

    for agent_id, meta in _AGENT_META.items():
        hb = await cache_get(f"agent:heartbeat:{agent_id}")
        if hb:
            last_run = datetime.fromisoformat(hb["last_run"])
            elapsed_s = int((now - last_run).total_seconds())
            if elapsed_s < 60:
                ago = "à l'instant"
            elif elapsed_s < 3600:
                ago = f"il y a {elapsed_s // 60} min"
            else:
                ago = f"il y a {elapsed_s // 3600}h"
            result.append({
                "id": agent_id,
                "label": meta["label"],
                "icon": meta["icon"],
                "status": hb["status"],
                "last_run": hb["last_run"],
                "elapsed_seconds": elapsed_s,
                "ago": ago,
                "result": hb["result"],
            })
        else:
            result.append({
                "id": agent_id,
                "label": meta["label"],
                "icon": meta["icon"],
                "status": "unknown",
                "last_run": None,
                "elapsed_seconds": None,
                "ago": "jamais",
                "result": "—",
            })

    return result
