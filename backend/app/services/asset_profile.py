"""
Asset Profile Service — stocke et charge le profil de fiabilité d'un actif.
Calculé après chaque backtest, consommé par le pipeline de scoring live.
"""
import json
from datetime import datetime, timezone

from app.services.redis_client import cache_get, cache_set

_PROFILE_PREFIX = "asset_profile:"
_PROFILE_TTL = 30 * 24 * 3600  # 30 jours

# Paramètres de scoring adaptatifs par label de diagnostic
_PARAMS_BY_LABEL: dict[str, dict] = {
    "robust": {
        "min_fusion_score":    61.0,
        "min_confidence":      0.35,
        "cooldown_hours":      4,
        "max_confidence_label": "high",
    },
    "noisy": {
        "min_fusion_score":    65.0,
        "min_confidence":      0.50,
        "cooldown_hours":      6,
        "max_confidence_label": "medium",
    },
    "over_traded": {
        "min_fusion_score":    68.0,
        "min_confidence":      0.55,
        "cooldown_hours":      8,
        "max_confidence_label": "low",
    },
    "unstable": {
        "min_fusion_score":    65.0,
        "min_confidence":      0.50,
        "cooldown_hours":      6,
        "max_confidence_label": "medium",
    },
    "bearish_asset": {
        "min_fusion_score":    65.0,
        "min_confidence":      0.55,
        "cooldown_hours":      8,
        "max_confidence_label": "low",
    },
    "mixed": {
        "min_fusion_score":    62.0,
        "min_confidence":      0.40,
        "cooldown_hours":      5,
        "max_confidence_label": "medium",
    },
}

_DEFAULT_PARAMS = _PARAMS_BY_LABEL["robust"]


async def save_asset_profile(ticker: str, label: str, recommendation: str, label_reason: str) -> None:
    """Persiste le profil diagnostique d'un actif en Redis après backtest."""
    params = _PARAMS_BY_LABEL.get(label, _DEFAULT_PARAMS)
    profile = {
        "ticker": ticker,
        "label": label,
        "recommendation": recommendation,
        "label_reason": label_reason,
        "params": params,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await cache_set(f"{_PROFILE_PREFIX}{ticker}", profile, _PROFILE_TTL)


async def load_asset_profile(ticker: str) -> dict:
    """
    Charge le profil d'un actif depuis Redis.
    Retourne les paramètres par défaut (robust) si aucun profil n'existe.
    """
    profile = await cache_get(f"{_PROFILE_PREFIX}{ticker}")
    if profile:
        return profile
    return {
        "ticker": ticker,
        "label": "unknown",
        "recommendation": "monitor",
        "label_reason": "Aucun backtest effectué",
        "params": _DEFAULT_PARAMS,
        "updated_at": None,
    }


async def get_all_profiles(tickers: list[str]) -> list[dict]:
    """Charge les profils de plusieurs actifs en parallèle."""
    import asyncio
    return await asyncio.gather(*[load_asset_profile(t) for t in tickers])
