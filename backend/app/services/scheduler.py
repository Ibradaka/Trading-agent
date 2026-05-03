from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
import structlog
from datetime import datetime, time, timezone
import pytz

from app.config import settings

logger = structlog.get_logger()
_scheduler = AsyncIOScheduler(timezone="Europe/Paris")

PARIS_TZ = pytz.timezone("Europe/Paris")


def is_market_open() -> bool:
    """Vérifie si Euronext Paris est ouvert (approximation sans exchange_calendars)."""
    now = datetime.now(PARIS_TZ)
    if now.weekday() >= 5:  # Samedi ou Dimanche
        return False
    open_h, open_m = map(int, settings.market_open_cet.split(":"))
    close_h, close_m = map(int, settings.market_close_cet.split(":"))
    market_open = time(open_h, open_m)
    market_close = time(close_h, close_m)
    return market_open <= now.time() <= market_close


async def _run_market_data_pipeline() -> None:
    """Pipeline principal : fetch → indicators → patterns → risk/score."""
    if not is_market_open():
        logger.debug("Market closed — skipping refresh")
        return
    logger.info("Starting market data pipeline")
    try:
        from app.agents.market_data import fetch_all_active_assets
        from app.agents.technical import compute_all_indicators
        from app.agents.patterns import detect_all_patterns
        from app.agents.risk import filter_and_score_all
        await fetch_all_active_assets()
        await compute_all_indicators()
        await detect_all_patterns()
        await filter_and_score_all()
        # spec-003: LLM synthesis est intégré dans filter_and_score_all()
        logger.info("Market data pipeline completed")
    except Exception:
        logger.exception("Market data pipeline failed")


async def _run_sentiment_update() -> None:
    """Refresh sentiment RSS toutes les 15 min (heures de marché)."""
    if not is_market_open():
        return
    try:
        from app.agents.sentiment import update_all_sentiments
        await update_all_sentiments()
    except Exception:
        logger.exception("Sentiment update failed")


async def _run_macro_update() -> None:
    """Refresh macro FRED toutes les 6h."""
    try:
        from app.agents.macro import update_macro_context
        await update_macro_context()
    except Exception:
        logger.exception("Macro update failed")


async def _run_outcome_tracking() -> None:
    """Vérifie l'accuracy des signaux à J+5, J+10, J+20 (quotidien)."""
    try:
        from app.services.outcome_tracker import check_all_outcomes
        await check_all_outcomes()
    except Exception:
        logger.exception("Outcome tracking failed")


async def _run_daily_digest() -> None:
    """Digest Telegram matinal + flush signaux quiet hours."""
    try:
        from app.services.telegram import send_daily_digest
        await send_daily_digest()
    except Exception:
        logger.exception("Daily digest failed")


async def _run_flush_pending() -> None:
    """Flush signaux Telegram mis en attente pendant les quiet hours (07h00)."""
    try:
        from app.services.telegram import _flush_pending_signals
        await _flush_pending_signals()
    except Exception:
        logger.exception("Flush pending signals failed")


async def start_scheduler() -> None:
    refresh_min = settings.default_refresh_minutes

    _scheduler.add_job(
        _run_market_data_pipeline,
        trigger=IntervalTrigger(minutes=refresh_min),
        id="market_data_pipeline",
        replace_existing=True,
        max_instances=1,
    )

    _scheduler.add_job(
        _run_sentiment_update,
        trigger=IntervalTrigger(minutes=15),
        id="sentiment_update",
        replace_existing=True,
        max_instances=1,
    )

    _scheduler.add_job(
        _run_macro_update,
        trigger=IntervalTrigger(hours=6),
        id="macro_update",
        replace_existing=True,
        max_instances=1,
        next_run_time=datetime.now(timezone.utc),  # Run immediately at startup
    )

    _scheduler.add_job(
        _run_outcome_tracking,
        trigger=CronTrigger(hour=20, minute=0, timezone="Europe/Paris"),
        id="outcome_tracking",
        replace_existing=True,
        max_instances=1,
    )

    _scheduler.add_job(
        _run_daily_digest,
        trigger=CronTrigger(hour=8, minute=0, timezone="Europe/Paris"),
        id="daily_digest",
        replace_existing=True,
        max_instances=1,
    )

    _scheduler.add_job(
        _run_flush_pending,
        trigger=CronTrigger(hour=7, minute=0, timezone="Europe/Paris"),
        id="flush_pending_signals",
        replace_existing=True,
        max_instances=1,
    )

    _scheduler.start()
    logger.info("APScheduler started", refresh_minutes=refresh_min)


async def stop_scheduler() -> None:
    _scheduler.shutdown(wait=False)
    logger.info("APScheduler stopped")
