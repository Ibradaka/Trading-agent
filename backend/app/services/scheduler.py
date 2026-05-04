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


async def _run_backtest_all() -> None:
    """Lance le backtest sur tous les actifs actifs pour calculer leur profil (label).
    Tourne au démarrage et chaque dimanche à 06h00."""
    try:
        from app.agents.watchlist_manager import get_active_tickers
        from app.database import AsyncSessionLocal
        from app.backtesting.engine import run_backtest

        async with AsyncSessionLocal() as session:
            tickers = await get_active_tickers(session)

        if not tickers:
            return

        logger.info("Auto-backtest starting", count=len(tickers))
        for ticker, _ in tickers:
            try:
                await run_backtest(ticker, period="2y", min_fusion_score=60.0, horizon_days=20)
                logger.info("Auto-backtest done", ticker=ticker)
            except Exception:
                logger.exception("Auto-backtest failed", ticker=ticker)

        logger.info("Auto-backtest complete", count=len(tickers))
    except Exception:
        logger.exception("Auto-backtest job failed")


async def _run_score_refresh_offhours() -> None:
    """Rafraîchit le cache signal Redis hors heures de marché (données DB existantes).
    Évite que les scores disparaissent overnight."""
    if is_market_open():
        return  # Le pipeline principal s'en charge
    try:
        from app.agents.macro import update_macro_context
        from app.agents.risk import filter_and_score_all
        await update_macro_context()
        await filter_and_score_all()
        logger.debug("Off-hours score cache refreshed")
    except Exception:
        logger.exception("Off-hours score refresh failed")


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
        _run_backtest_all,
        trigger=CronTrigger(day_of_week="sun", hour=6, minute=0, timezone="Europe/Paris"),
        id="auto_backtest",
        replace_existing=True,
        max_instances=1,
        next_run_time=datetime.now(timezone.utc),  # Lance immédiatement au démarrage
    )

    _scheduler.add_job(
        _run_score_refresh_offhours,
        trigger=IntervalTrigger(hours=2),
        id="score_refresh_offhours",
        replace_existing=True,
        max_instances=1,
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
