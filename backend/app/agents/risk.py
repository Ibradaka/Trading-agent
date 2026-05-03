"""
Risk & Confidence Agent — 5 filtres, calcul confiance (0-1), cooldown Redis,
écriture des signaux en DB, pub Redis.
"""
import asyncio
import structlog
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID, uuid4
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.services.redis_client import cache_get, cache_set, publish
from app.agents.watchlist_manager import get_active_tickers
from app.agents.technical import load_ohlc_df, compute_indicators
from app.scoring.technical import compute_technical_score, compute_momentum_score
from app.scoring.patterns import compute_pattern_score
from app.scoring.composite import compute_composite_score, compute_fusion_score

logger = structlog.get_logger()

_COOLDOWN_PREFIX = "cooldown:signal:"
_COOLDOWN_TTL = 4 * 3600  # 4h


# ──────────────────────────────────────────────
# Filtres
# ──────────────────────────────────────────────

@dataclass
class RiskAssessment:
    passed: bool
    confidence: float
    filters_passed: list[str] = field(default_factory=list)
    filters_failed: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)


def _volume_filter(ind: dict) -> tuple[bool, str]:
    v = ind.get("volume")
    vma = ind.get("volume_ma20")
    if v is None or not vma:
        return True, "volume_indisponible"
    ratio = v / vma
    if ratio < 0.30:
        return False, f"volume_faible_{ratio:.0%}_moyenne"
    return True, f"volume_ok_{ratio:.0%}_moyenne"


def _volatility_filter(ind: dict) -> tuple[bool, str]:
    atr = ind.get("atr")
    close = ind.get("close")
    if atr is None or not close:
        return True, "volatilite_indisponible"
    pct = atr / close
    if pct > 0.08:
        return False, f"volatilite_excessive_atr_{pct:.1%}"
    return True, f"volatilite_ok_atr_{pct:.1%}"


def _score_filter(composite_score: float) -> tuple[bool, str]:
    if 40.0 <= composite_score <= 60.0:
        return False, f"score_neutre_{composite_score:.0f}"
    return True, f"score_signal_{composite_score:.0f}"


def _trend_filter(ind: dict, signal_direction: str) -> tuple[bool, str]:
    """Cohérence entre la tendance EMA et la direction du signal."""
    ema20 = ind.get("ema20")
    ema50 = ind.get("ema50")
    close = ind.get("close")
    if any(v is None for v in [ema20, ema50, close]):
        return True, "trend_indisponible"

    bullish_trend = close > ema20 > ema50
    bearish_trend = close < ema20 < ema50

    if signal_direction == "BUY" and bearish_trend:
        return False, "signal_buy_contre_trend_baissier"
    if signal_direction == "SELL" and bullish_trend:
        return False, "signal_sell_contre_trend_haussier"
    return True, "trend_coherente"


async def _cooldown_filter(ticker: str) -> tuple[bool, str]:
    cached = await cache_get(f"{_COOLDOWN_PREFIX}{ticker}")
    if cached is not None:
        return False, "cooldown_signal_recent"
    return True, "pas_de_cooldown"


async def set_cooldown(ticker: str, hours: int = 4) -> None:
    await cache_set(
        f"{_COOLDOWN_PREFIX}{ticker}",
        {"at": datetime.now(timezone.utc).isoformat()},
        ttl=hours * 3600,
    )


# ──────────────────────────────────────────────
# Calcul de confiance
# ──────────────────────────────────────────────

def compute_confidence(
    technical_score: float,
    pattern_score: float,
    momentum_score: float,
    volume_ratio: float,
    patterns_count: int,
    atr_pct: float,
) -> float:
    """
    Confiance 0-1 basée sur la convergence des signaux et les conditions de marché.
    """
    conf = 0.50

    # Convergence technical + momentum + patterns → même direction
    directions = [
        1 if s > 55 else (-1 if s < 45 else 0)
        for s in [technical_score, momentum_score, pattern_score]
    ]
    non_neutral = [d for d in directions if d != 0]
    if non_neutral:
        agreement = sum(non_neutral) / len(non_neutral)
        if abs(agreement) > 0.9:
            conf += 0.20   # forte convergence
        elif abs(agreement) > 0.5:
            conf += 0.10
        elif abs(agreement) < 0:
            conf -= 0.15   # divergence

    # Volume
    if volume_ratio > 1.5:
        conf += 0.12
    elif volume_ratio > 1.2:
        conf += 0.06
    elif volume_ratio < 0.5:
        conf -= 0.08

    # Patterns multiples
    if patterns_count >= 3:
        conf += 0.08
    elif patterns_count >= 2:
        conf += 0.04

    # Volatilité idéale pour swing (1% – 4%)
    if 0.01 < atr_pct < 0.04:
        conf += 0.05
    elif atr_pct > 0.06:
        conf -= 0.10

    return max(0.05, min(0.95, conf))


# ──────────────────────────────────────────────
# Évaluation complète d'un signal
# ──────────────────────────────────────────────

async def assess_risk(
    ticker: str,
    indicators: dict,
    composite_score: float,
    technical_score: float,
    pattern_score: float,
    momentum_score: float,
    patterns: list[dict],
) -> RiskAssessment:

    passed_list: list[str] = []
    failed_list: list[str] = []
    reasons: list[str] = []

    signal_type = "BUY" if composite_score >= 65 else ("SELL" if composite_score <= 45 else "HOLD")

    # 1. Volume
    ok, msg = _volume_filter(indicators)
    (passed_list if ok else failed_list).append("volume")
    reasons.append(msg)

    # 2. Volatilité
    ok, msg = _volatility_filter(indicators)
    (passed_list if ok else failed_list).append("volatilite")
    reasons.append(msg)

    # 3. Cooldown
    ok, msg = await _cooldown_filter(ticker)
    (passed_list if ok else failed_list).append("cooldown")
    reasons.append(msg)

    # 4. Score non neutre
    ok, msg = _score_filter(composite_score)
    (passed_list if ok else failed_list).append("score")
    reasons.append(msg)

    # 5. Cohérence tendance (non bloquant pour HOLD)
    if signal_type != "HOLD":
        ok, msg = _trend_filter(indicators, signal_type)
        (passed_list if ok else failed_list).append("trend")
        reasons.append(msg)
    else:
        passed_list.append("trend")
        reasons.append("hold_trend_non_evalue")

    # Confiance
    close = indicators.get("close") or 1.0
    atr = indicators.get("atr") or 0.0
    volume = indicators.get("volume") or 0.0
    vma = indicators.get("volume_ma20") or 1.0
    confidence = compute_confidence(
        technical_score=technical_score,
        pattern_score=pattern_score,
        momentum_score=momentum_score,
        volume_ratio=volume / vma if vma > 0 else 1.0,
        patterns_count=len(patterns),
        atr_pct=atr / close if close > 0 else 0.0,
    )

    # Bloquants : volume, cooldown, score
    blocking = {"volume", "cooldown", "score"}
    hard_fails = [f for f in failed_list if f in blocking]
    passed = len(hard_fails) == 0

    return RiskAssessment(
        passed=passed,
        confidence=confidence,
        filters_passed=passed_list,
        filters_failed=failed_list,
        reasons=reasons,
    )


# ──────────────────────────────────────────────
# Persistance signal
# ──────────────────────────────────────────────

async def _write_signal(
    session: AsyncSession,
    asset_id: str,
    breakdown,
    fusion: dict,
    confidence: float,
    patterns: list[dict],
    indicators: dict,
    llm_result: dict | None = None,
) -> str:
    """Insère un signal et désactive les précédents."""
    signal_id = str(uuid4())
    now = datetime.now(timezone.utc)

    await session.execute(
        text("""
            UPDATE signals SET is_active = FALSE
            WHERE asset_id = :asset_id AND is_active = TRUE
        """),
        {"asset_id": asset_id},
    )

    bullish_patterns = [p["pattern_name"] for p in patterns if p.get("direction") == "bullish"]
    bearish_patterns = [p["pattern_name"] for p in patterns if p.get("direction") == "bearish"]

    # Fallback deterministic reasoning
    default_reasoning = (
        f"Score composite {breakdown.composite:.0f}/100 — "
        f"Technique {breakdown.technical:.0f} / Patterns {breakdown.patterns:.0f} / "
        f"Momentum {breakdown.momentum:.0f} / Macro {breakdown.macro:.0f} / Sentiment {breakdown.sentiment:.0f}. "
        f"Patterns haussiers : {', '.join(bullish_patterns) or 'aucun'}."
    )
    ema20 = indicators.get("ema20")
    default_invalidation = f"Clôture sous EMA20 ({ema20:.2f})" if ema20 else None

    if llm_result:
        reasoning = llm_result.get("reasoning") or default_reasoning
        invalidation = llm_result.get("invalidation_conditions") or default_invalidation
        horizon = llm_result.get("horizon") or "3-10 jours (swing trading)"
        risks_raw = llm_result.get("risks") or [f"• {p}" for p in bearish_patterns]
        llm_raw = llm_result.get("llm_raw_output")
    else:
        reasoning = default_reasoning
        invalidation = default_invalidation
        horizon = "3-10 jours (swing trading)"
        risks_raw = [f"• {p}" for p in bearish_patterns]
        llm_raw = None

    import json
    risks_json = json.dumps(risks_raw if risks_raw else [])
    llm_json = json.dumps(llm_raw) if llm_raw else "null"

    await session.execute(
        text("""
            INSERT INTO signals (
                id, asset_id, timestamp,
                signal_type, strength,
                composite_score, technical_score, pattern_score,
                sentiment_score, macro_score, momentum_score,
                confidence, reasoning, risks,
                invalidation_conditions, horizon,
                llm_raw_output, is_active
            ) VALUES (
                :id, :asset_id, :timestamp,
                :signal_type, :strength,
                :composite_score, :technical_score, :pattern_score,
                :sentiment_score, :macro_score, :momentum_score,
                :confidence, :reasoning, :risks::jsonb,
                :invalidation_conditions, :horizon,
                :llm_raw_output::jsonb, TRUE
            )
        """),
        {
            "id": signal_id,
            "asset_id": asset_id,
            "timestamp": now,
            "signal_type": fusion["signal_type"],
            "strength": fusion["signal_strength"],
            "composite_score": fusion["score"],
            "technical_score": breakdown.technical,
            "pattern_score": breakdown.patterns,
            "sentiment_score": breakdown.sentiment,
            "macro_score": breakdown.macro,
            "momentum_score": breakdown.momentum,
            "confidence": confidence,
            "reasoning": reasoning,
            "risks": risks_json,
            "invalidation_conditions": invalidation,
            "horizon": horizon,
            "llm_raw_output": llm_json,
        },
    )
    return signal_id


# ──────────────────────────────────────────────
# Entrée scheduler
# ──────────────────────────────────────────────

async def _load_recent_patterns(session: AsyncSession, asset_id: str) -> list[dict]:
    result = await session.execute(
        text("""
            SELECT pattern_name, direction, strength
            FROM detected_patterns
            WHERE asset_id = :asset_id
              AND timestamp >= NOW() - INTERVAL '48 hours'
            ORDER BY created_at DESC
            LIMIT 20
        """),
        {"asset_id": asset_id},
    )
    return [
        {"pattern_name": r.pattern_name, "direction": r.direction, "strength": float(r.strength or 0.5)}
        for r in result.fetchall()
    ]


async def filter_and_score_all() -> None:
    """
    Entrée scheduler — pour chaque asset actif :
      1. charge les indicateurs et patterns depuis la DB
      2. calcule les scores et évalue les filtres de risque
      3. écrit le signal si les filtres passent
      4. publie sur Redis
    """
    async with AsyncSessionLocal() as session:
        tickers = await get_active_tickers(session)

    if not tickers:
        return

    logger.info("Scoring signals", count=len(tickers))

    async def _process(ticker: str, asset_id: str) -> None:
        try:
            async with AsyncSessionLocal() as session:
                df = await load_ohlc_df(session, asset_id)
                patterns = await _load_recent_patterns(session, asset_id)

            if df.empty or len(df) < 26:
                return

            indicators = await asyncio.to_thread(compute_indicators, df)
            if indicators is None:
                return

            tech_score = compute_technical_score(indicators)
            mom_score = compute_momentum_score(indicators)
            pat_score = compute_pattern_score(patterns)

            # 3a. Scores contextuels depuis le cache Redis (défaut 50 si absent)
            from app.agents.sentiment import get_sentiment_score
            from app.agents.macro import get_macro_context
            sentiment_score, sentiment_narrative, sentiment_themes = await get_sentiment_score(ticker)
            macro_ctx = await get_macro_context()
            macro_score = float(macro_ctx["score"])
            macro_narrative = macro_ctx.get("narrative", "")
            macro_regime = macro_ctx.get("regime", "neutral")

            # 3b. Score composite existant (pour stockage et affichage des sous-scores)
            breakdown = compute_composite_score(
                technical=tech_score,
                patterns=pat_score,
                momentum=mom_score,
                macro=macro_score,
                sentiment=sentiment_score,
            )

            # 3c. Signal Fusion Engine — décision déterministe backtestable
            fusion = compute_fusion_score(breakdown)

            # 3d. Risk filters (utilise le fusion score pour cohérence)
            assessment = await assess_risk(
                ticker=ticker,
                indicators=indicators,
                composite_score=fusion["score"],
                technical_score=tech_score,
                pattern_score=pat_score,
                momentum_score=mom_score,
                patterns=patterns,
            )

            if not assessment.passed:
                logger.debug(
                    "Signal filtered",
                    ticker=ticker,
                    fusion_score=fusion["score"],
                    failed=assessment.filters_failed,
                )
                return

            # 3e. Confidence Engine
            from app.agents.confidence import compute_confidence
            confidence_ctx = compute_confidence(
                tech_composite=fusion["technical_composite"],
                sentiment_score=sentiment_score,
                macro_score=macro_score,
                has_fresh_sentiment=bool(sentiment_narrative),
                has_fresh_macro=(macro_ctx.get("fed_rate") is not None),
            )

            # 3f. LLM explanation (couche d'interprétabilité, non décisionnaire)
            from app.services.llm import explain_signal
            llm_result = await explain_signal(
                ticker=ticker,
                asset_name=ticker,
                fusion=fusion,
                breakdown=breakdown,
                indicators=indicators,
                patterns=patterns,
                sentiment_narrative=sentiment_narrative,
                macro_narrative=macro_narrative,
                macro_regime=macro_regime,
                confidence=confidence_ctx,
            )

            async with AsyncSessionLocal() as session:
                signal_id = await _write_signal(
                    session, asset_id, breakdown, fusion,
                    confidence_ctx["score"] / 100.0,  # normalise 0-1 pour la DB
                    patterns, indicators,
                    llm_result=llm_result,
                )
                await session.commit()

            await set_cooldown(ticker, hours=4)

            await publish(f"signal:updated:{ticker}", {
                "ticker": ticker,
                "signal_type": fusion["signal_type"],
                "strength": fusion["signal_strength"],
                "composite_score": fusion["score"],
                "confidence": confidence_ctx["score"] / 100.0,
                "confidence_label": confidence_ctx["label"],
                "macro_regime": macro_regime,
                "signal_id": signal_id,
            })

            logger.info(
                "Signal written",
                ticker=ticker,
                signal=fusion["signal_type"],
                fusion_score=fusion["score"],
                confidence_label=confidence_ctx["label"],
                macro_regime=macro_regime,
            )
        except Exception:
            logger.exception("Signal scoring failed", ticker=ticker)

    await asyncio.gather(*[_process(t, aid) for t, aid in tickers])
    logger.info("Scoring complete", count=len(tickers))
