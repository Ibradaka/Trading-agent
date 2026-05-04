from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
import asyncio
import uuid

from app.database import get_session
from app.models.db import Asset
from app.services.yfinance_session import yf_chart, yf_chart_full, yf_intraday, yf_quote_summary, yf_news, get_yf_session
from app.services.redis_client import cache_get, cache_set
from app.services.llm import translate_titles_to_french

router = APIRouter()

PEA_ELIGIBLE_EXCHANGES = {
    "ENX", "PAR", "EPA",
    "AMS", "EAM",
    "BRU", "EBR",
    "LIS", "ELI",
    "XETRA", "GER", "EWE", "ETR",
    "MIL", "BIT",
    "MAD", "MCE",
    "STO", "HEL", "CPH", "OSL",
}

PEA_ELIGIBLE_SUFFIXES = {".PA", ".AS", ".BR", ".LS", ".DE", ".MI", ".MC", ".AM"}


def _detect_asset_type(ticker: str) -> str:
    if ticker.endswith("=F"):
        return "commodity"
    if ticker.startswith("^"):
        return "index"
    if ticker.endswith("-USD") or ticker.endswith("-EUR") or ticker.endswith("-USDT"):
        return "crypto"
    if ticker.endswith("=X"):
        return "forex"
    return "equity"


def _check_pea_eligibility(ticker: str, exchange: str) -> bool:
    if _detect_asset_type(ticker) != "equity":
        return False
    for suffix in PEA_ELIGIBLE_SUFFIXES:
        if ticker.endswith(suffix):
            return True
    return (exchange or "").upper() in PEA_ELIGIBLE_EXCHANGES


def _fetch_ticker_info(ticker: str) -> dict:
    """Synchrone — appelé via asyncio.to_thread."""
    meta = yf_chart(ticker)
    summary = yf_quote_summary(ticker)
    price_data = summary.get("price", {})
    profile = summary.get("summaryProfile", {}) or summary.get("assetProfile", {})
    return {
        "regularMarketPrice": (price_data.get("regularMarketPrice") or {}).get("raw") or meta.get("regularMarketPrice"),
        "currency": price_data.get("currency") or meta.get("currency"),
        "exchange": price_data.get("exchange") or meta.get("exchangeName"),
        "shortName": price_data.get("shortName") or meta.get("symbol"),
        "longName": price_data.get("longName"),
        "quoteType": price_data.get("quoteType"),
        "sector": profile.get("sector"),
        "country": profile.get("country"),
        "marketCap": (price_data.get("marketCap") or {}).get("raw"),
        "longBusinessSummary": profile.get("longBusinessSummary", ""),
    }


class TickerValidation(BaseModel):
    valid: bool
    ticker: Optional[str] = None
    name: Optional[str] = None
    asset_type: Optional[str] = None
    exchange: Optional[str] = None
    currency: Optional[str] = None
    sector: Optional[str] = None
    country: Optional[str] = None
    is_pea_eligible: Optional[bool] = None
    current_price: Optional[float] = None
    error: Optional[str] = None


@router.get("/validate")
async def validate_ticker(ticker: str = Query(min_length=1, max_length=20)) -> TickerValidation:
    ticker_upper = ticker.upper().strip()
    try:
        info = await asyncio.to_thread(_fetch_ticker_info, ticker_upper)
        price = info.get("regularMarketPrice")
        if not price:
            return TickerValidation(valid=False, ticker=ticker_upper, error="Ticker not found or no market data")

        exchange = info.get("exchange", "")
        return TickerValidation(
            valid=True,
            ticker=ticker_upper,
            name=info.get("longName") or info.get("shortName") or ticker_upper,
            asset_type=_detect_asset_type(ticker_upper),
            exchange=exchange,
            currency=info.get("currency"),
            sector=info.get("sector"),
            country=info.get("country"),
            is_pea_eligible=_check_pea_eligibility(ticker_upper, exchange),
            current_price=price,
        )
    except Exception as e:
        return TickerValidation(valid=False, ticker=ticker_upper, error=str(e))


@router.post("/validate/add")
async def validate_and_add_asset(
    ticker: str = Query(min_length=1, max_length=20),
    db: AsyncSession = Depends(get_session),
):
    ticker_upper = ticker.upper().strip()

    existing = await db.execute(select(Asset).where(Asset.ticker == ticker_upper))
    if existing.scalar_one_or_none():
        return {"ticker": ticker_upper, "created": False, "message": "Already exists"}

    validation = await validate_ticker(ticker_upper)
    if not validation.valid:
        return {"ticker": ticker_upper, "created": False, "error": validation.error}

    info = await asyncio.to_thread(_fetch_ticker_info, ticker_upper)
    asset = Asset(
        id=uuid.uuid4(),
        ticker=ticker_upper,
        name=validation.name,
        asset_type=validation.asset_type,
        exchange=validation.exchange,
        currency=validation.currency,
        sector=validation.sector,
        country=validation.country,
        is_pea_eligible=validation.is_pea_eligible,
        metadata_={
            "longBusinessSummary": (info.get("longBusinessSummary") or "")[:500],
            "marketCap": info.get("marketCap"),
        },
    )
    db.add(asset)
    await db.flush()
    return {"ticker": ticker_upper, "created": True, "asset_id": str(asset.id)}


def _fetch_quote(ticker: str) -> dict:
    """Synchrone — appelé via asyncio.to_thread.
    Retourne prix courant + OHLC du jour + 52S range + historique 1mo + variations multi-timeframe.
    Utilise l'intraday 1m/1d comme source principale pour l'OHLC du jour en cours."""

    # Appels parallèles : chart 1d/1mo pour historique + intraday 1m/1d pour OHLC live
    daily = yf_chart_full(ticker)
    intra = yf_intraday(ticker)
    summary = yf_quote_summary(ticker)

    # Meta : priorité intraday (plus frais), fallback daily
    meta = intra.get("meta") or daily.get("meta", {})
    price_data = summary.get("price", {})

    # Historique mensuel (bougies journalières pour sparkline + variations)
    timestamps = daily.get("timestamp") or []
    quotes_raw = (daily.get("indicators", {}).get("quote") or [{}])[0]
    closes = quotes_raw.get("close") or []
    opens_arr = quotes_raw.get("open") or []
    highs_arr = quotes_raw.get("high") or []
    lows_arr = quotes_raw.get("low") or []
    volumes_arr = quotes_raw.get("volume") or []

    history = []
    for i, ts in enumerate(timestamps):
        c = closes[i] if i < len(closes) else None
        if c is None:
            continue
        history.append({
            "date": ts,
            "open": opens_arr[i] if i < len(opens_arr) else None,
            "high": highs_arr[i] if i < len(highs_arr) else None,
            "low": lows_arr[i] if i < len(lows_arr) else None,
            "close": c,
            "volume": volumes_arr[i] if i < len(volumes_arr) else None,
        })

    # OHLC du jour depuis intraday : agrège toutes les bougies 1min
    intra_q = (intra.get("indicators", {}).get("quote") or [{}])[0]
    intra_opens = [v for v in (intra_q.get("open") or []) if v is not None]
    intra_highs = [v for v in (intra_q.get("high") or []) if v is not None]
    intra_lows = [v for v in (intra_q.get("low") or []) if v is not None]
    intra_closes = [v for v in (intra_q.get("close") or []) if v is not None]
    intra_volumes = [v for v in (intra_q.get("volume") or []) if v is not None]

    intra_open = intra_opens[0] if intra_opens else None
    intra_high = max(intra_highs) if intra_highs else None
    intra_low = min(intra_lows) if intra_lows else None
    intra_close = intra_closes[-1] if intra_closes else None
    intra_volume = int(sum(intra_volumes)) if intra_volumes else None

    current_price = intra_close or meta.get("regularMarketPrice")
    previous_close = meta.get("previousClose") or meta.get("chartPreviousClose")

    change_pct = None
    if current_price and previous_close:
        change_pct = round((current_price - previous_close) / previous_close * 100, 2)

    week_change_pct = None
    month_change_pct = None
    if history and current_price:
        if len(history) >= 5 and history[-5]["close"]:
            week_change_pct = round((current_price - history[-5]["close"]) / history[-5]["close"] * 100, 2)
        if history[0]["close"]:
            month_change_pct = round((current_price - history[0]["close"]) / history[0]["close"] * 100, 2)

    def _raw(field: str) -> float | None:
        val = price_data.get(field)
        if isinstance(val, dict):
            return val.get("raw")
        return val

    last_bar = history[-1] if history else {}

    return {
        "ticker": ticker,
        "current_price": current_price,
        "previous_close": previous_close,
        "change_pct": change_pct,
        "week_change_pct": week_change_pct,
        "month_change_pct": month_change_pct,
        "currency": meta.get("currency"),
        "exchange": meta.get("exchangeName"),
        "market_state": meta.get("marketState"),
        "open": intra_open or _raw("regularMarketOpen") or last_bar.get("open"),
        "day_high": intra_high or _raw("regularMarketDayHigh") or last_bar.get("high"),
        "day_low": intra_low or _raw("regularMarketDayLow") or last_bar.get("low"),
        "volume": intra_volume or _raw("regularMarketVolume") or last_bar.get("volume"),
        "week52_high": _raw("fiftyTwoWeekHigh"),
        "week52_low": _raw("fiftyTwoWeekLow"),
        "history": history,
    }


@router.get("/{ticker}/quote")
async def get_asset_quote(ticker: str):
    ticker_upper = ticker.upper().strip()
    try:
        data = await asyncio.to_thread(_fetch_quote, ticker_upper)
        if not data.get("current_price"):
            return {"error": "No data", "ticker": ticker_upper}
        return data
    except Exception as e:
        return {"error": str(e), "ticker": ticker_upper}


@router.get("/{ticker}/news")
async def get_asset_news(ticker: str):
    ticker_upper = ticker.upper().strip()
    cache_key = f"news:{ticker_upper}"

    cached = await cache_get(cache_key)
    if cached is not None:
        return cached

    raw_news = await asyncio.to_thread(yf_news, ticker_upper)
    if not raw_news:
        return []

    titles = [item.get("title", "") for item in raw_news]
    translated = await translate_titles_to_french(titles)

    result = [
        {
            "title": translated[i] if i < len(translated) else titles[i],
            "title_original": titles[i],
            "link": item.get("link", ""),
            "publisher": item.get("publisher", ""),
            "published_at": item.get("providerPublishTime"),
        }
        for i, item in enumerate(raw_news)
    ]

    await cache_set(cache_key, result, 1800)
    return result


_CHART_RANGES = {
    "5d":  ("15m", "5d"),
    "1mo": ("1d",  "1mo"),
    "3mo": ("1d",  "3mo"),
    "6mo": ("1d",  "6mo"),
    "1y":  ("1d",  "1y"),
}

def _fetch_chart_ohlc(ticker: str, interval: str, range_: str) -> list[dict]:
    """Fetch OHLC via curl_cffi — contourne le blocage datacenter."""
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
        f"?interval={interval}&range={range_}"
    )
    r = get_yf_session().get(url, timeout=20)
    result = (r.json().get("chart", {}).get("result") or [None])[0]
    if not result:
        return []
    timestamps = result.get("timestamp") or []
    q = (result.get("indicators", {}).get("quote") or [{}])[0]
    adj = (result.get("indicators", {}).get("adjclose") or [{}])[0].get("adjclose") or []
    out = []
    for i, ts in enumerate(timestamps):
        c = adj[i] if adj and i < len(adj) else (q.get("close") or [None])[i] if i < len(q.get("close") or []) else None
        o = (q.get("open") or [None])[i] if i < len(q.get("open") or []) else None
        h = (q.get("high") or [None])[i] if i < len(q.get("high") or []) else None
        l = (q.get("low") or [None])[i] if i < len(q.get("low") or []) else None
        if c is None:
            continue
        out.append({"time": ts, "open": o, "high": h, "low": l, "close": c})
    return out


@router.get("/{ticker}/chart")
async def get_asset_chart(ticker: str, range: str = Query(default="1mo")):
    ticker_upper = ticker.upper().strip()
    interval, range_ = _CHART_RANGES.get(range, ("1d", "1mo"))
    cache_key = f"chart:{ticker_upper}:{range}"
    ttl = 300 if range == "5d" else 1800

    cached = await cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        data = await asyncio.to_thread(_fetch_chart_ohlc, ticker_upper, interval, range_)
        if data:
            await cache_set(cache_key, data, ttl)
        return data
    except Exception as e:
        return []


@router.get("/search")
async def search_assets(
    q: str = Query(min_length=1, max_length=50),
    db: AsyncSession = Depends(get_session),
):
    result = await db.execute(
        select(Asset)
        .where(Asset.ticker.ilike(f"%{q}%") | Asset.name.ilike(f"%{q}%"))
        .limit(10)
    )
    assets = result.scalars().all()
    return [
        {
            "ticker": a.ticker,
            "name": a.name,
            "asset_type": a.asset_type,
            "is_pea_eligible": a.is_pea_eligible,
            "exchange": a.exchange,
            "currency": a.currency,
        }
        for a in assets
    ]
