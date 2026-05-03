"""
Telegram bot — alertes signaux, commandes, digest quotidien.
Consomme uniquement les outputs du Signal Fusion Engine (Redis pub/sub + DB).
Ne recalcule jamais de signaux.
"""
import asyncio
import json
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import httpx
import structlog
from sqlalchemy import text

from app.config import settings
from app.database import AsyncSessionLocal
from app.services.redis_client import cache_get, cache_set, get_redis

logger = structlog.get_logger()

_COOLDOWN_PREFIX = "cooldown:telegram:"
_COOLDOWN_TTL = 2 * 3600  # 2h
_PAUSE_PREFIX = "pause:telegram:"
_PENDING_PREFIX = "pending:telegram:"

PARIS_TZ = ZoneInfo("Europe/Paris")

_QUIET_START = 22  # 22h00
_QUIET_END = 7     # 07h00

_listener_task: asyncio.Task | None = None
_polling_task: asyncio.Task | None = None


# ──────────────────────────────────────────────
# HTTP helpers
# ──────────────────────────────────────────────

async def _tg_post(method: str, payload: dict) -> dict | None:
    if not settings.telegram_bot_token:
        return None
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/{method}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(url, json=payload)
            r.raise_for_status()
            return r.json()
    except Exception as e:
        logger.warning("Telegram API error", method=method, error=str(e))
        return None


async def _send(chat_id: str, text_: str, parse_mode: str = "HTML") -> bool:
    result = await _tg_post("sendMessage", {
        "chat_id": chat_id,
        "text": text_,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    })
    return result is not None


# ──────────────────────────────────────────────
# Quiet hours
# ──────────────────────────────────────────────

def _is_quiet_hours() -> bool:
    hour = datetime.now(PARIS_TZ).hour
    if _QUIET_START > _QUIET_END:
        return hour >= _QUIET_START or hour < _QUIET_END
    return _QUIET_START <= hour < _QUIET_END


# ──────────────────────────────────────────────
# Formatage messages
# ──────────────────────────────────────────────

def _signal_emoji(signal_type: str, strength: str) -> str:
    if signal_type == "BUY":
        return "🟢🟢" if strength == "strong" else "🟢"
    if signal_type == "SELL":
        return "🔴🔴" if strength == "strong" else "🔴"
    return "⚪"


def _format_signal_alert(data: dict, reasoning: str) -> str:
    ticker = data["ticker"]
    signal_type = data["signal_type"]
    strength = data.get("strength", "weak")
    score = data["composite_score"]
    confidence = data.get("confidence_label", "medium")
    macro_regime = data.get("macro_regime", "neutral")
    emoji = _signal_emoji(signal_type, strength)

    dashboard_url = getattr(settings, "dashboard_url", "")
    link = f"{dashboard_url}/asset/{ticker}" if dashboard_url else ""

    lines = [
        f"{emoji} <b>{signal_type} — {ticker}</b>",
        f"Score: <b>{score/100:.2f}</b> | Confiance: <b>{confidence}</b>",
        f"Régime macro: {macro_regime}",
        "",
    ]
    if reasoning:
        lines.append(reasoning[:200])
        lines.append("")
    now_str = datetime.now(PARIS_TZ).strftime("%d/%m %H:%M")
    lines.append(f"<i>{now_str} CET</i>")
    if link:
        lines.append(f'<a href="{link}">Voir le dashboard →</a>')
    return "\n".join(lines)


def _format_watchlist_summary(rows: list[dict]) -> str:
    if not rows:
        return "Watchlist vide."
    lines = ["<b>Watchlist</b>", ""]
    for r in rows:
        emoji = _signal_emoji(r["signal_type"], r.get("strength", "weak"))
        score_str = f"{r['composite_score']/100:.2f}"
        conf = r.get("confidence_label", "—")
        lines.append(f"{emoji} <b>{r['ticker']}</b> — {r['signal_type']} {score_str} ({conf})")
    lines.append(f"\n<i>Mise à jour: {datetime.now(PARIS_TZ).strftime('%H:%M')} CET</i>")
    return "\n".join(lines)


def _format_status(rows: list[dict], macro: dict) -> str:
    now_str = datetime.now(PARIS_TZ).strftime("%d/%m/%Y %H:%M")
    regime = macro.get("regime", "N/A")
    macro_score = macro.get("score", 50)
    lines = [
        "<b>Statut du système</b>",
        f"<i>{now_str} CET</i>",
        "",
        f"Signaux actifs: {len(rows)}",
        f"Régime macro: {regime} ({macro_score:.0f}/100)",
    ]
    if rows:
        last = rows[0]
        lines.append(f"Dernier signal: {last['ticker']} {last['signal_type']} à {last['ts'].strftime('%H:%M') if last.get('ts') else '—'}")
    return "\n".join(lines)


def _format_digest(rows: list[dict], macro: dict) -> str:
    now_str = datetime.now(PARIS_TZ).strftime("%d/%m/%Y")
    regime = macro.get("regime", "neutral")
    macro_score = macro.get("score", 50)
    bias = macro.get("bias", "neutral")

    buy = [r for r in rows if r["signal_type"] == "BUY"]
    sell = [r for r in rows if r["signal_type"] == "SELL"]

    lines = [
        f"<b>Digest matinal — {now_str}</b>",
        "",
        f"<b>Macro :</b> {regime} | Score {macro_score:.0f}/100 | Biais {bias}",
        "",
    ]
    if buy:
        lines.append("<b>Signaux BUY :</b>")
        for r in buy[:5]:
            lines.append(f"  🟢 {r['ticker']} — {r['composite_score']/100:.2f} ({r.get('confidence_label','—')})")
    if sell:
        lines.append("<b>Signaux SELL :</b>")
        for r in sell[:5]:
            lines.append(f"  🔴 {r['ticker']} — {r['composite_score']/100:.2f} ({r.get('confidence_label','—')})")
    if not buy and not sell:
        lines.append("Aucun signal actif ce matin.")
    return "\n".join(lines)


# ──────────────────────────────────────────────
# DB helpers
# ──────────────────────────────────────────────

async def _fetch_active_signals() -> list[dict]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(text("""
            SELECT a.ticker, s.signal_type, s.strength, s.composite_score,
                   s.confidence, s.reasoning, s.timestamp,
                   CASE
                     WHEN s.confidence >= 0.70 THEN 'high'
                     WHEN s.confidence >= 0.45 THEN 'medium'
                     ELSE 'low'
                   END AS confidence_label
            FROM signals s
            JOIN assets a ON a.id = s.asset_id
            WHERE s.is_active = TRUE
            ORDER BY s.composite_score DESC
        """))
        rows = result.fetchall()
    return [
        {
            "ticker": r.ticker,
            "signal_type": r.signal_type,
            "strength": r.strength,
            "composite_score": r.composite_score,
            "confidence": r.confidence,
            "confidence_label": r.confidence_label,
            "reasoning": r.reasoning or "",
            "ts": r.timestamp,
        }
        for r in rows
    ]


async def _fetch_signal_for_ticker(ticker: str) -> dict | None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("""
                SELECT a.ticker, s.signal_type, s.strength, s.composite_score,
                       s.confidence, s.reasoning, s.timestamp,
                       CASE
                         WHEN s.confidence >= 0.70 THEN 'high'
                         WHEN s.confidence >= 0.45 THEN 'medium'
                         ELSE 'low'
                       END AS confidence_label
                FROM signals s
                JOIN assets a ON a.id = s.asset_id
                WHERE a.ticker = :ticker AND s.is_active = TRUE
                ORDER BY s.timestamp DESC
                LIMIT 1
            """),
            {"ticker": ticker.upper()},
        )
        r = result.fetchone()
    if not r:
        return None
    return {
        "ticker": r.ticker,
        "signal_type": r.signal_type,
        "strength": r.strength,
        "composite_score": r.composite_score,
        "confidence": r.confidence,
        "confidence_label": r.confidence_label,
        "reasoning": r.reasoning or "",
        "ts": r.timestamp,
    }


# ──────────────────────────────────────────────
# Logique d'alerte
# ──────────────────────────────────────────────

async def _should_alert(ticker: str, score: float, confidence_label: str) -> bool:
    from app.routers.settings import get_settings
    cfg = await get_settings()
    if cfg.get("panic_mode"):
        return False
    if not cfg.get("telegram_enabled", True):
        return False
    threshold = cfg.get("alert_threshold", 0.70)
    if score / 100.0 < threshold:
        return False
    if confidence_label not in ("medium", "high"):
        return False
    paused = await cache_get(f"{_PAUSE_PREFIX}{ticker.upper()}")
    if paused:
        return False
    cooldown = await cache_get(f"{_COOLDOWN_PREFIX}{ticker.upper()}")
    if cooldown:
        return False
    return True


async def _set_cooldown(ticker: str) -> None:
    await cache_set(
        f"{_COOLDOWN_PREFIX}{ticker.upper()}",
        {"at": datetime.now(timezone.utc).isoformat()},
        _COOLDOWN_TTL,
    )


async def _store_pending(ticker: str, data: dict, reasoning: str) -> None:
    """Stocke un signal en attente pendant les quiet hours."""
    await cache_set(
        f"{_PENDING_PREFIX}{ticker.upper()}",
        {"data": data, "reasoning": reasoning},
        ttl_seconds=12 * 3600,  # expire après 12h si jamais envoyé
    )


async def _flush_pending_signals() -> None:
    """Envoie les signaux mis en attente pendant les quiet hours."""
    chat_id = settings.telegram_chat_id
    if not chat_id:
        return
    try:
        redis = get_redis()
        keys = await redis.keys(f"{_PENDING_PREFIX}*")
        for key in keys:
            raw = await redis.get(key)
            if not raw:
                continue
            payload = json.loads(raw)
            data = payload["data"]
            reasoning = payload["reasoning"]
            ticker = data["ticker"]
            # Vérifie cooldown avant d'envoyer
            cooldown = await cache_get(f"{_COOLDOWN_PREFIX}{ticker.upper()}")
            if not cooldown:
                msg = _format_signal_alert(data, reasoning)
                ok = await _send(chat_id, msg)
                if ok:
                    await _set_cooldown(ticker)
                    await redis.delete(key)
                    logger.info("Pending signal sent", ticker=ticker)
    except Exception:
        logger.exception("Failed to flush pending signals")


# ──────────────────────────────────────────────
# Commandes bot
# ──────────────────────────────────────────────

async def _handle_command(text_: str, chat_id: str) -> None:
    text_ = text_.strip()
    cmd_parts = text_.split()
    cmd = cmd_parts[0].lower().split("@")[0]  # strip bot username

    if cmd == "/signal":
        ticker = cmd_parts[1].upper() if len(cmd_parts) > 1 else None
        if not ticker:
            await _send(chat_id, "Usage: /signal &lt;TICKER&gt;")
            return
        sig = await _fetch_signal_for_ticker(ticker)
        if not sig:
            await _send(chat_id, f"Aucun signal actif pour <b>{ticker}</b>.")
            return
        ts_str = sig["ts"].strftime("%d/%m %H:%M") if sig.get("ts") else "—"
        msg = (
            f"{_signal_emoji(sig['signal_type'], sig['strength'])} <b>{sig['signal_type']} — {ticker}</b>\n"
            f"Score: <b>{sig['composite_score']/100:.2f}</b> | Confiance: <b>{sig['confidence_label']}</b>\n"
            f"<i>{ts_str} CET</i>\n\n"
            f"{sig['reasoning'][:300] if sig['reasoning'] else '—'}"
        )
        await _send(chat_id, msg)

    elif cmd == "/watchlist":
        rows = await _fetch_active_signals()
        await _send(chat_id, _format_watchlist_summary(rows))

    elif cmd == "/status":
        rows = await _fetch_active_signals()
        from app.agents.macro import get_macro_context
        macro = await get_macro_context()
        await _send(chat_id, _format_status(rows, macro))

    elif cmd == "/pause":
        ticker = cmd_parts[1].upper() if len(cmd_parts) > 1 else None
        if not ticker:
            await _send(chat_id, "Usage: /pause &lt;TICKER&gt;")
            return
        await cache_set(f"{_PAUSE_PREFIX}{ticker}", {"at": datetime.now(timezone.utc).isoformat()}, 24 * 3600)
        await _send(chat_id, f"Alertes <b>{ticker}</b> suspendues pendant 24h.")

    elif cmd == "/resume":
        ticker = cmd_parts[1].upper() if len(cmd_parts) > 1 else None
        if not ticker:
            await _send(chat_id, "Usage: /resume &lt;TICKER&gt;")
            return
        redis = get_redis()
        await redis.delete(f"{_PAUSE_PREFIX}{ticker}")
        await _send(chat_id, f"Alertes <b>{ticker}</b> réactivées.")

    else:
        await _send(chat_id, "Commandes: /signal &lt;TICKER&gt; | /watchlist | /status | /pause &lt;TICKER&gt; | /resume &lt;TICKER&gt;")


# ──────────────────────────────────────────────
# Polling update loop
# ──────────────────────────────────────────────

_last_update_id: int = 0


async def _poll_commands() -> None:
    global _last_update_id
    if not settings.telegram_bot_token:
        return
    try:
        result = await _tg_post("getUpdates", {
            "offset": _last_update_id + 1,
            "timeout": 5,
            "allowed_updates": ["message"],
        })
        if not result or not result.get("ok"):
            return
        for update in result.get("result", []):
            _last_update_id = update["update_id"]
            msg = update.get("message", {})
            text_ = msg.get("text", "")
            chat_id = str(msg.get("chat", {}).get("id", ""))
            if text_ and text_.startswith("/") and chat_id:
                await _handle_command(text_, chat_id)
    except Exception:
        logger.exception("Telegram polling error")


# ──────────────────────────────────────────────
# Redis subscriber
# ──────────────────────────────────────────────

async def _signal_listener() -> None:
    """Écoute Redis pub/sub signal:updated:* et envoie les alertes Telegram."""
    chat_id = settings.telegram_chat_id
    if not chat_id or not settings.telegram_bot_token:
        logger.info("Telegram not configured — listener disabled")
        return

    redis = get_redis()
    pubsub = redis.pubsub()
    await pubsub.psubscribe("signal:updated:*")
    logger.info("Telegram signal listener started")

    async for raw_msg in pubsub.listen():
        if raw_msg["type"] not in ("pmessage", "message"):
            continue

        try:
            data = json.loads(raw_msg["data"])
            ticker = data.get("ticker", "")
            score = data.get("composite_score", 0.0)
            confidence_label = data.get("confidence_label", "low")
            signal_type = data.get("signal_type", "HOLD")

            # HOLD n'est jamais alerté
            if signal_type == "HOLD":
                continue

            if not await _should_alert(ticker, score, confidence_label):
                continue

            # Récupère le reasoning depuis la DB
            sig = await _fetch_signal_for_ticker(ticker)
            reasoning = sig["reasoning"] if sig else ""

            if _is_quiet_hours():
                await _store_pending(ticker, data, reasoning)
                logger.info("Signal stored (quiet hours)", ticker=ticker)
                continue

            msg = _format_signal_alert(data, reasoning)
            ok = await _send(chat_id, msg)
            if ok:
                await _set_cooldown(ticker)
                logger.info("Alert sent", ticker=ticker, signal=signal_type, score=score)

        except Exception:
            logger.exception("Error processing signal alert", raw=raw_msg)


# ──────────────────────────────────────────────
# Digest quotidien
# ──────────────────────────────────────────────

async def send_daily_digest() -> None:
    """Job scheduler 08h00 — résumé matinal."""
    chat_id = settings.telegram_chat_id
    if not chat_id or not settings.telegram_bot_token:
        return
    try:
        await _flush_pending_signals()
        rows = await _fetch_active_signals()
        from app.agents.macro import get_macro_context
        macro = await get_macro_context()
        msg = _format_digest(rows, macro)
        await _send(chat_id, msg)
        logger.info("Daily digest sent", signals=len(rows))
    except Exception:
        logger.exception("Daily digest failed")


# ──────────────────────────────────────────────
# Lifecycle
# ──────────────────────────────────────────────

async def _command_polling_loop() -> None:
    """Boucle indépendante — poll Telegram toutes les 3s pour les commandes."""
    while True:
        await _poll_commands()
        await asyncio.sleep(3)


async def start_telegram_bot() -> None:
    global _listener_task, _polling_task
    if not settings.telegram_bot_token:
        logger.info("Telegram token not set — bot disabled")
        return
    _listener_task = asyncio.create_task(_signal_listener())
    _polling_task = asyncio.create_task(_command_polling_loop())
    logger.info("Telegram bot started")


async def stop_telegram_bot() -> None:
    global _listener_task, _polling_task
    for task in [_listener_task, _polling_task]:
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
    logger.info("Telegram bot stopped")


# Backward-compat stub (appelé nulle part mais gardé au cas où)
async def send_signal_notification(*_, **__) -> bool:
    return False


async def send_status_message(message: str) -> bool:
    chat_id = settings.telegram_chat_id
    if not chat_id:
        return False
    return bool(await _send(chat_id, message))
