from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
import asyncio
import yfinance as yf
import uuid

from app.database import get_session
from app.models.db import Asset

router = APIRouter()

PEA_ELIGIBLE_EXCHANGES = {
    "ENX", "PAR", "EPA",          # Euronext Paris
    "AMS", "EAM",                  # Amsterdam
    "BRU", "EBR",                  # Bruxelles
    "LIS", "ELI",                  # Lisbonne
    "XETRA", "GER", "EWE", "ETR", # Xetra (Allemagne)
    "MIL", "BIT",                  # Milan
    "MAD", "MCE",                  # Madrid
    "STO", "HEL", "CPH", "OSL",   # Nordiques
}


def _detect_asset_type(ticker: str, info: dict) -> str:
    if ticker.endswith("=F"):
        return "commodity"
    if ticker.startswith("^"):
        return "index"
    if ticker.endswith("-USD") or ticker.endswith("-EUR") or ticker.endswith("-USDT"):
        return "crypto"
    if ticker.endswith("=X"):
        return "forex"
    return "equity"


def _check_pea_eligibility(ticker: str, info: dict) -> bool:
    asset_type = _detect_asset_type(ticker, info)
    if asset_type != "equity":
        return False
    exchange = info.get("exchange", "").upper()
    return exchange in PEA_ELIGIBLE_EXCHANGES


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
    """Valide un ticker yfinance et retourne ses métadonnées."""
    ticker_upper = ticker.upper().strip()
    try:
        info = await asyncio.to_thread(lambda: yf.Ticker(ticker_upper).info)
        price = info.get("regularMarketPrice") or info.get("currentPrice")
        if not price:
            return TickerValidation(valid=False, error="Ticker not found or no market data")

        asset_type = _detect_asset_type(ticker_upper, info)
        return TickerValidation(
            valid=True,
            ticker=ticker_upper,
            name=info.get("longName") or info.get("shortName") or ticker_upper,
            asset_type=asset_type,
            exchange=info.get("exchange"),
            currency=info.get("currency"),
            sector=info.get("sector"),
            country=info.get("country"),
            is_pea_eligible=_check_pea_eligibility(ticker_upper, info),
            current_price=price,
        )
    except Exception as e:
        return TickerValidation(valid=False, error=str(e))


@router.post("/validate/add")
async def validate_and_add_asset(
    ticker: str = Query(min_length=1, max_length=20),
    db: AsyncSession = Depends(get_session),
):
    """Valide un ticker et l'ajoute à la table assets s'il n'existe pas."""
    ticker_upper = ticker.upper().strip()

    existing = await db.execute(select(Asset).where(Asset.ticker == ticker_upper))
    if existing.scalar_one_or_none():
        return {"ticker": ticker_upper, "created": False, "message": "Already exists"}

    validation = await validate_ticker(ticker_upper)
    if not validation.valid:
        return {"ticker": ticker_upper, "created": False, "error": validation.error}

    info = await asyncio.to_thread(lambda: yf.Ticker(ticker_upper).info)
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
            "longBusinessSummary": info.get("longBusinessSummary", "")[:500],
            "marketCap": info.get("marketCap"),
            "employees": info.get("fullTimeEmployees"),
        },
    )
    db.add(asset)
    await db.flush()
    return {"ticker": ticker_upper, "created": True, "asset_id": str(asset.id)}


@router.get("/search")
async def search_assets(
    q: str = Query(min_length=1, max_length=50),
    db: AsyncSession = Depends(get_session),
):
    """Recherche dans les actifs déjà en base."""
    result = await db.execute(
        select(Asset)
        .where(
            Asset.ticker.ilike(f"%{q}%") | Asset.name.ilike(f"%{q}%")
        )
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
