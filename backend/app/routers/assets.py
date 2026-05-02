from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
import asyncio
import uuid

from app.database import get_session
from app.models.db import Asset
from app.services.yfinance_session import yf_chart, yf_chart_full, yf_quote_summary

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
    """Synchrone — appelé via asyncio.to_thread. Retourne prix courant + historique 5j."""
    full = yf_chart_full(ticker)
    meta = full.get("meta", {})
    timestamps = full.get("timestamp") or []
    quotes = (full.get("indicators", {}).get("quote") or [{}])[0]

    closes = quotes.get("close") or []
    opens = quotes.get("open") or []
    highs = quotes.get("high") or []
    lows = quotes.get("low") or []
    volumes = quotes.get("volume") or []

    history = []
    for i, ts in enumerate(timestamps):
        c = closes[i] if i < len(closes) else None
        if c is None:
            continue
        history.append({
            "date": ts,
            "open": opens[i] if i < len(opens) else None,
            "high": highs[i] if i < len(highs) else None,
            "low": lows[i] if i < len(lows) else None,
            "close": c,
            "volume": volumes[i] if i < len(volumes) else None,
        })

    current_price = meta.get("regularMarketPrice")
    previous_close = meta.get("previousClose") or meta.get("chartPreviousClose")
    change_pct = None
    if current_price and previous_close:
        change_pct = round((current_price - previous_close) / previous_close * 100, 2)

    return {
        "ticker": ticker,
        "current_price": current_price,
        "previous_close": previous_close,
        "change_pct": change_pct,
        "currency": meta.get("currency"),
        "exchange": meta.get("exchangeName"),
        "market_state": meta.get("marketState"),
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
