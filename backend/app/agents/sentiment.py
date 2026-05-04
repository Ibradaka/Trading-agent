"""
Sentiment Agent — RSS feeds → keyword scoring + GPT-4o-mini → sentiment 0-100 → Redis 15min.
Sources: Yahoo Finance RSS, Google News RSS.
"""
import asyncio
import json
import re
import structlog
from datetime import datetime, timezone, timedelta
from time import mktime

import feedparser
from sqlalchemy import text

from app.database import AsyncSessionLocal
from app.services.redis_client import cache_get, cache_set
from app.services.llm import score_sentiment_batch
from app.agents.watchlist_manager import get_active_tickers

logger = structlog.get_logger()

_SENTIMENT_TTL = 15 * 60  # 15 min

# Mots-clés macro qui justifient un appel LLM pour scoring précis
_MACRO_TRIGGER_KEYWORDS = frozenset([
    "fed", "fomc", "federal", "reserve", "rate", "hike", "cut", "pivot",
    "cpi", "inflation", "deflation", "recession", "gdp", "stagflation",
    "sanctions", "opec", "oil", "crisis", "default", "collapse", "bubble",
    "quantitative", "taper", "powell", "lagarde", "ecb", "bce",
    "unemployment", "payrolls", "yields", "treasury", "spread",
])

_POSITIVE_WORDS = frozenset([
    "upgrade", "buy", "outperform", "beat", "beats", "growth", "surge", "rally",
    "strong", "bullish", "positive", "raised", "exceeded", "record", "gain",
    "profit", "revenue", "top pick", "overweight", "accumulate",
    "hausse", "croissance", "bénéfice", "rebond", "progression", "achat",
])
_NEGATIVE_WORDS = frozenset([
    "downgrade", "sell", "underperform", "miss", "misses", "cut", "cuts",
    "decline", "drop", "weak", "bearish", "negative", "concern", "warning",
    "below", "loss", "deficit", "lawsuit", "fraud", "recall", "lowered",
    "underweight", "reduce", "baisse", "chute", "perte", "avertissement",
    "dégradation", "risque", "vente",
])


def _rss_urls(ticker: str) -> list[str]:
    return [
        f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}&region=US&lang=en-US",
        f"https://news.google.com/rss/search?q={ticker}+stock&hl=en-US&gl=US&ceid=US:en",
    ]


def _parse_rss(url: str) -> list[dict]:
    """Synchronous RSS parsing — called via asyncio.to_thread."""
    try:
        feed = feedparser.parse(url)
        items = []
        cutoff = datetime.now(timezone.utc) - timedelta(hours=48)
        for entry in feed.entries[:10]:
            title = entry.get("title", "").strip()
            if not title:
                continue
            pub = entry.get("published_parsed")
            if pub:
                pub_dt = datetime.fromtimestamp(mktime(pub), tz=timezone.utc)
                if pub_dt < cutoff:
                    continue
            items.append({
                "title": title,
                "url": entry.get("link", ""),
                "source": feed.feed.get("title", ""),
            })
        return items
    except Exception:
        return []


def _keyword_score(title: str) -> float:
    """Quick keyword-based score: -1 (negative) to +1 (positive)."""
    words = set(re.findall(r"\w+", title.lower()))
    pos = len(words & _POSITIVE_WORDS)
    neg = len(words & _NEGATIVE_WORDS)
    if pos == 0 and neg == 0:
        return 0.0
    return (pos - neg) / (pos + neg)


def _should_use_llm(titles: list[str]) -> bool:
    """Retourne True si les titres contiennent un événement macro important."""
    all_words = set(re.findall(r"\b\w+\b", " ".join(titles).lower()))
    return bool(all_words & _MACRO_TRIGGER_KEYWORDS)


async def get_sentiment_score(ticker: str) -> tuple[float, str, list[str]]:
    """
    Returns (score 0-100, narrative, themes) from Redis cache.
    50 = neutral, >50 = positive, <50 = negative.
    Falls back to (50, '', []) if no cached data available.
    """
    cached = await cache_get(f"sentiment:{ticker.upper()}")
    if cached:
        return float(cached["score"]), cached.get("narrative", ""), cached.get("themes", [])
    return 50.0, "", []


async def _compute_and_cache(ticker: str, asset_id: str) -> None:
    """Fetch RSS, score with keywords + LLM, store in Redis and DB."""
    articles: list[dict] = []
    for url in _rss_urls(ticker):
        batch = await asyncio.to_thread(_parse_rss, url)
        articles.extend(batch)
        if len(articles) >= 6:
            break

    if not articles:
        logger.debug("No articles found for sentiment", ticker=ticker)
        return

    titles = [a["title"] for a in articles[:8]]
    keyword_scores = [_keyword_score(t) for t in titles]

    # Appel LLM uniquement si événement macro détecté — réduit les coûts API
    use_llm = _should_use_llm(titles)
    if use_llm:
        llm_scores = await score_sentiment_batch(ticker, titles)
        final_scores = [
            0.4 * kw + 0.6 * (llm_scores[i] if i < len(llm_scores) else kw)
            for i, kw in enumerate(keyword_scores)
        ]
        logger.debug("Sentiment LLM triggered", ticker=ticker, reason="macro keywords detected")
    else:
        final_scores = keyword_scores

    avg = sum(final_scores) / len(final_scores)
    score = max(10.0, min(90.0, round(50.0 + avg * 30.0, 1)))

    # Key themes: titles with highest absolute sentiment
    scored_titles = sorted(zip([abs(s) for s in final_scores], titles), key=lambda x: x[0], reverse=True)
    themes = [t for _, t in scored_titles[:3]]

    direction = "positif" if avg > 0.1 else ("négatif" if avg < -0.1 else "neutre")
    narrative = f"Sentiment {ticker}: {len(articles)} articles ({direction}), score {score:.0f}/100"
    sources = list({a["source"] for a in articles if a["source"]})[:3]

    payload = {"score": score, "narrative": narrative, "themes": themes}
    await cache_set(f"sentiment:{ticker.upper()}", payload, _SENTIMENT_TTL)

    # Persist to DB
    now = datetime.now(timezone.utc)
    expires = now + timedelta(minutes=15)
    themes_json = json.dumps(themes)
    sources_json = json.dumps(sources)

    async with AsyncSessionLocal() as session:
        try:
            await session.execute(
                text("""
                    INSERT INTO sentiment_cache (asset_id, timestamp, sentiment_score, key_themes, sources, expires_at)
                    VALUES (:asset_id, :ts, :score, cast(:themes as jsonb), cast(:sources as jsonb), :expires)
                    ON CONFLICT (asset_id, timestamp) DO NOTHING
                """),
                {
                    "asset_id": asset_id,
                    "ts": now,
                    "score": score,
                    "themes": themes_json,
                    "sources": sources_json,
                    "expires": expires,
                },
            )
            await session.commit()
        except Exception:
            logger.exception("Failed to persist sentiment cache", ticker=ticker)

    logger.info("Sentiment updated", ticker=ticker, score=score, articles=len(articles))


async def update_all_sentiments() -> None:
    """Scheduler job — update sentiment for all active watchlist tickers."""
    async with AsyncSessionLocal() as session:
        tickers = await get_active_tickers(session)

    if not tickers:
        return

    logger.info("Updating sentiment scores", count=len(tickers))

    # Process in batches of 5 to respect API rate limits
    for i in range(0, len(tickers), 5):
        batch = [_compute_and_cache(t, aid) for t, aid in tickers[i : i + 5]]
        await asyncio.gather(*batch, return_exceptions=True)

    logger.info("Sentiment update complete", count=len(tickers))
    from app.services.redis_client import agent_heartbeat
    await agent_heartbeat("sentiment", f"{len(tickers)} actifs")
