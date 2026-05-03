"""
Outcome Tracker — vérifie l'accuracy des signaux à J+5, J+10, J+20.
Job quotidien à 20h CET. Ne recalcule aucun signal.
"""
import asyncio
import structlog
from datetime import datetime, timezone, timedelta

import yfinance as yf
from sqlalchemy import text

from app.database import AsyncSessionLocal
from app.services.yfinance_session import get_yf_session

logger = structlog.get_logger()


def _fetch_latest_close(ticker: str) -> float | None:
    """Prix de clôture le plus récent (synchrone — via asyncio.to_thread)."""
    try:
        df = yf.Ticker(ticker, session=get_yf_session()).history(
            period="5d", interval="1d", auto_adjust=True
        )
        if df.empty:
            return None
        return float(df.iloc[-1]["Close"])
    except Exception:
        return None


async def _check_outcomes_for_days(days: int) -> int:
    """
    Cherche les signaux créés il y a ~N jours et écrit leur outcome.
    La fenêtre est ±1 jour pour absorber weekends et jours fériés.
    """
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(days=days + 1)
    window_end = now - timedelta(days=days - 1)

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("""
                SELECT
                    s.id, s.timestamp, s.signal_type,
                    a.ticker,
                    o.close AS price_at_signal
                FROM signals s
                JOIN assets a ON a.id = s.asset_id
                LEFT JOIN ohlc_data o
                    ON  o.asset_id = s.asset_id
                    AND DATE(o.timestamp AT TIME ZONE 'UTC') = DATE(s.timestamp AT TIME ZONE 'UTC')
                    AND o.timeframe = '1d'
                WHERE s.timestamp BETWEEN :start AND :end
                  AND s.signal_type IN ('BUY', 'SELL')
                  AND NOT EXISTS (
                    SELECT 1 FROM signal_outcomes so
                    WHERE so.signal_id = s.id AND so.days_elapsed = :days
                  )
            """),
            {"start": window_start, "end": window_end, "days": days},
        )
        rows = result.fetchall()

    if not rows:
        return 0

    logger.info("Checking signal outcomes", days=days, count=len(rows))
    checked = 0

    for row in rows:
        if row.price_at_signal is None:
            logger.debug("No OHLC price at signal date, skipping", ticker=row.ticker, days=days)
            continue

        price_now = await asyncio.to_thread(_fetch_latest_close, row.ticker)
        if price_now is None:
            continue

        actual_days = (now - row.timestamp).days
        actual_return_pct = (price_now - row.price_at_signal) / row.price_at_signal * 100
        was_correct = (
            (row.signal_type == "BUY" and actual_return_pct > 0) or
            (row.signal_type == "SELL" and actual_return_pct < 0)
        )

        async with AsyncSessionLocal() as session:
            try:
                await session.execute(
                    text("""
                        INSERT INTO signal_outcomes
                            (signal_id, outcome_checked_at, price_at_signal, price_at_check,
                             actual_return_pct, was_correct, days_elapsed)
                        VALUES
                            (:sid, :checked_at, :p_signal, :p_check, :ret, :correct, :days)
                        ON CONFLICT (signal_id, outcome_checked_at) DO NOTHING
                    """),
                    {
                        "sid": str(row.id),
                        "checked_at": now,
                        "p_signal": row.price_at_signal,
                        "p_check": price_now,
                        "ret": round(actual_return_pct, 4),
                        "correct": was_correct,
                        "days": actual_days,
                    },
                )
                await session.commit()
                checked += 1
            except Exception:
                logger.exception("Failed to write outcome", signal_id=str(row.id))

    return checked


async def check_all_outcomes() -> None:
    """Entrée scheduler — vérifie J+5, J+10, J+20."""
    logger.info("Starting outcome tracking")
    total = 0
    for days in [5, 10, 20]:
        n = await _check_outcomes_for_days(days)
        total += n
    logger.info("Outcome tracking complete", total=total)


async def get_accuracy_stats() -> dict:
    """Stats globales d'accuracy depuis signal_outcomes."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(text("""
            SELECT
                COUNT(*)                                                      AS total,
                COUNT(*) FILTER (WHERE so.was_correct = TRUE)                AS correct,
                COUNT(*) FILTER (WHERE s.signal_type = 'BUY')                AS n_buy,
                COUNT(*) FILTER (WHERE s.signal_type = 'BUY'
                                   AND so.was_correct = TRUE)                AS correct_buy,
                COUNT(*) FILTER (WHERE s.signal_type = 'SELL')               AS n_sell,
                COUNT(*) FILTER (WHERE s.signal_type = 'SELL'
                                   AND so.was_correct = TRUE)                AS correct_sell,
                ROUND(AVG(so.actual_return_pct)::numeric, 2)                 AS avg_return,
                ROUND(AVG(so.actual_return_pct)
                      FILTER (WHERE so.was_correct = TRUE)::numeric, 2)      AS avg_return_correct,
                ROUND(AVG(so.actual_return_pct)
                      FILTER (WHERE so.was_correct = FALSE)::numeric, 2)     AS avg_return_incorrect,
                -- Calibration
                COUNT(*) FILTER (WHERE s.confidence >= 0.70)                 AS n_high,
                COUNT(*) FILTER (WHERE s.confidence >= 0.70
                                   AND so.was_correct = TRUE)                AS correct_high,
                COUNT(*) FILTER (WHERE s.confidence >= 0.45
                                   AND s.confidence < 0.70)                  AS n_med,
                COUNT(*) FILTER (WHERE s.confidence >= 0.45
                                   AND s.confidence < 0.70
                                   AND so.was_correct = TRUE)                AS correct_med
            FROM signal_outcomes so
            JOIN signals s ON s.id = so.signal_id
            WHERE s.signal_type IN ('BUY', 'SELL')
        """))
        row = result.fetchone()

    if not row or not row.total:
        return {"total_signals_tracked": 0, "message": "Aucun outcome disponible — revenez dans 5 jours"}

    def _pct(num, den):
        return round(float(num) / float(den) * 100, 1) if den and float(den) > 0 else None

    return {
        "total_signals_tracked": row.total,
        "global_accuracy_pct": _pct(row.correct, row.total),
        "buy_accuracy_pct": _pct(row.correct_buy, row.n_buy),
        "sell_accuracy_pct": _pct(row.correct_sell, row.n_sell),
        "avg_return_all_pct": float(row.avg_return) if row.avg_return else None,
        "avg_return_correct_pct": float(row.avg_return_correct) if row.avg_return_correct else None,
        "avg_return_incorrect_pct": float(row.avg_return_incorrect) if row.avg_return_incorrect else None,
        "calibration": {
            "high_confidence": {"n": row.n_high, "accuracy_pct": _pct(row.correct_high, row.n_high)},
            "medium_confidence": {"n": row.n_med, "accuracy_pct": _pct(row.correct_med, row.n_med)},
        },
    }


async def get_ticker_accuracy(ticker: str) -> dict:
    """Accuracy par ticker."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("""
                SELECT
                    COUNT(*)                                           AS total,
                    COUNT(*) FILTER (WHERE so.was_correct = TRUE)     AS correct,
                    ROUND(AVG(so.actual_return_pct)::numeric, 2)      AS avg_return,
                    ROUND(MIN(so.actual_return_pct)::numeric, 2)      AS min_return,
                    ROUND(MAX(so.actual_return_pct)::numeric, 2)      AS max_return
                FROM signal_outcomes so
                JOIN signals s  ON s.id  = so.signal_id
                JOIN assets   a ON a.id  = s.asset_id
                WHERE a.ticker = :ticker AND s.signal_type IN ('BUY', 'SELL')
            """),
            {"ticker": ticker.upper()},
        )
        row = result.fetchone()

    if not row or not row.total:
        return {"ticker": ticker.upper(), "total_tracked": 0}

    return {
        "ticker": ticker.upper(),
        "total_tracked": row.total,
        "accuracy_pct": round(float(row.correct) / float(row.total) * 100, 1),
        "avg_return_pct": float(row.avg_return) if row.avg_return else None,
        "min_return_pct": float(row.min_return) if row.min_return else None,
        "max_return_pct": float(row.max_return) if row.max_return else None,
    }


async def get_recent_signals_with_outcomes(limit: int = 50) -> list[dict]:
    """Signaux récents avec leur meilleur outcome disponible (pour la page /history)."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("""
                SELECT
                    s.id, s.timestamp, s.signal_type, s.strength,
                    s.composite_score, s.confidence, s.reasoning,
                    a.ticker, a.name AS asset_name,
                    so.actual_return_pct, so.was_correct, so.days_elapsed,
                    so.outcome_checked_at
                FROM signals s
                JOIN assets a ON a.id = s.asset_id
                LEFT JOIN LATERAL (
                    SELECT actual_return_pct, was_correct, days_elapsed, outcome_checked_at
                    FROM signal_outcomes
                    WHERE signal_id = s.id
                    ORDER BY days_elapsed DESC
                    LIMIT 1
                ) so ON TRUE
                WHERE s.signal_type IN ('BUY', 'SELL')
                ORDER BY s.timestamp DESC
                LIMIT :limit
            """),
            {"limit": limit},
        )
        rows = result.fetchall()

    return [
        {
            "id": str(r.id),
            "ticker": r.ticker,
            "asset_name": r.asset_name,
            "signal_type": r.signal_type,
            "strength": r.strength,
            "composite_score": r.composite_score,
            "confidence": r.confidence,
            "reasoning": r.reasoning,
            "timestamp": r.timestamp.isoformat() if r.timestamp else None,
            "outcome": {
                "return_pct": float(r.actual_return_pct) if r.actual_return_pct is not None else None,
                "was_correct": r.was_correct,
                "days_elapsed": r.days_elapsed,
                "checked_at": r.outcome_checked_at.isoformat() if r.outcome_checked_at else None,
            } if r.actual_return_pct is not None else None,
        }
        for r in rows
    ]
