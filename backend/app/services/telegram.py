"""Telegram notification service — implémentation complète en spec-005."""
import structlog
from typing import Optional

from app.config import settings

logger = structlog.get_logger()


async def send_signal_notification(
    ticker: str,
    signal_type: str,
    strength: str,
    composite_score: float,
    confidence: float,
    reasoning: str,
    risks: list[str],
    invalidation: str,
    scores: dict,
    horizon: str,
) -> bool:
    """Envoie une notification Telegram pour un signal fort."""
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        logger.warning("Telegram not configured — skipping notification")
        return False

    # Implémentation complète dans spec-005
    logger.info("Signal notification queued", ticker=ticker, signal=signal_type, score=composite_score)
    return True


async def send_status_message(message: str) -> bool:
    """Envoie un message de statut système."""
    if not settings.telegram_bot_token:
        return False
    logger.info("Status message queued", length=len(message))
    return True
