"""
Watchlist Manager Agent — validation tickers yfinance, éligibilité PEA, CRUD watchlist.
"""
import asyncio
import structlog
from uuid import UUID
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
import yfinance as yf

from app.models.db import Asset, Watchlist, WatchlistAsset
from app.services.yfinance_session import get_yf_session

logger = structlog.get_logger()

PEA_ELIGIBLE_EXCHANGES = {
    "ENX", "PAR", "EPA", "AMS", "EAM", "BRU", "EBR",
    "LIS", "ELI", "XETRA", "GER", "ETR", "MIL", "BIT",
    "MAD", "MCE", "STO", "HEL", "CPH", "OSL",
    "EURONEXT", "XPAR", "XAMS", "XBRU", "XLIS", "XMIL", "XMAD",
}

PEA_ELIGIBLE_SUFFIXES = {".PA", ".AS", ".BR", ".LS", ".DE", ".MI", ".MC", ".AM"}


def detect_asset_type(ticker: str, info: dict) -> str:
    t = ticker.upper()
    if t.endswith("=F"):
        return "commodity"
    if t.startswith("^"):
        return "index"
    if "-USD" in t or "-EUR" in t or "-BTC" in t or "-USDT" in t:
        return "crypto"
    if t.endswith("=X"):
        return "forex"
    return "equity"


def check_pea_eligibility(ticker: str, info: dict) -> bool:
    """
    PEA éligible si :
    1. Equity sur exchange européen (suffix ou code exchange)
    2. ETF UCITS domicilié en Europe
    """
    if detect_asset_type(ticker, info) != "equity":
        return False

    for suffix in PEA_ELIGIBLE_SUFFIXES:
        if ticker.endswith(suffix):
            return True

    exchange = (info.get("exchange") or "").upper()
    if exchange in PEA_ELIGIBLE_EXCHANGES:
        return True

    # ETF UCITS
    quote_type = (info.get("quoteType") or "").upper()
    if quote_type == "ETF":
        legal_type = (info.get("legalType") or "").lower()
        fund_family = (info.get("fundFamily") or "").lower()
        if "ucits" in legal_type or "ucits" in fund_family:
            return True

    return False


def _parse_yf_info(ticker: str, info: dict) -> dict:
    suffix = ("." + ticker.split(".", 1)[1]) if "." in ticker else None
    return {
        "valid": True,
        "ticker": ticker,
        "name": info.get("shortName") or info.get("longName") or ticker,
        "asset_type": detect_asset_type(ticker, info),
        "exchange": info.get("exchange"),
        "exchange_suffix": suffix,
        "currency": info.get("currency"),
        "sector": info.get("sector"),
        "country": info.get("country"),
        "isin": info.get("isin"),
        "is_pea_eligible": check_pea_eligibility(ticker, info),
        "current_price": info.get("regularMarketPrice") or info.get("currentPrice"),
        "market_cap": info.get("marketCap"),
    }


def _yf_fetch(ticker: str) -> dict:
    """Synchrone — appelé via asyncio.to_thread."""
    yfobj = yf.Ticker(ticker, session=get_yf_session())
    info = yfobj.info or {}
    if not info.get("regularMarketPrice") and not info.get("currentPrice"):
        try:
            price = yfobj.fast_info["lastPrice"]
            if price:
                info["regularMarketPrice"] = price
        except Exception:
            pass
    return info


async def validate_ticker(ticker: str) -> dict:
    """Valide un ticker et retourne ses métadonnées. Pas d'écriture en DB."""
    ticker = ticker.strip().upper()
    try:
        info = await asyncio.to_thread(_yf_fetch, ticker)
        if not info.get("regularMarketPrice") and not info.get("currentPrice"):
            return {"valid": False, "ticker": ticker, "error": "Ticker non trouvé ou prix indisponible"}
        return _parse_yf_info(ticker, info)
    except Exception as e:
        logger.warning("validate_ticker failed", ticker=ticker, error=str(e))
        return {"valid": False, "ticker": ticker, "error": str(e)}


async def get_or_create_asset(session: AsyncSession, ticker_data: dict) -> Asset:
    """Retourne l'asset existant ou le crée en DB à partir de la validation."""
    result = await session.execute(
        select(Asset).where(Asset.ticker == ticker_data["ticker"])
    )
    asset = result.scalar_one_or_none()

    if asset is None:
        asset = Asset(
            ticker=ticker_data["ticker"],
            name=ticker_data["name"],
            asset_type=ticker_data["asset_type"],
            exchange=ticker_data["exchange"],
            exchange_suffix=ticker_data.get("exchange_suffix"),
            currency=ticker_data["currency"],
            sector=ticker_data.get("sector"),
            country=ticker_data.get("country"),
            isin=ticker_data.get("isin"),
            is_pea_eligible=ticker_data["is_pea_eligible"],
            metadata_={
                "market_cap": ticker_data.get("market_cap"),
                "current_price": ticker_data.get("current_price"),
            },
        )
        session.add(asset)
        await session.flush()
        logger.info("Asset créé", ticker=ticker_data["ticker"])

    return asset


async def get_active_tickers(session: AsyncSession) -> list[tuple[str, str]]:
    """Retourne [(ticker, asset_id)] pour tous les assets dans une watchlist active."""
    result = await session.execute(
        select(Asset.ticker, Asset.id)
        .join(WatchlistAsset, WatchlistAsset.asset_id == Asset.id)
        .join(Watchlist, Watchlist.id == WatchlistAsset.watchlist_id)
        .where(Watchlist.is_active.is_(True))
        .where(WatchlistAsset.is_active.is_(True))
        .distinct()
    )
    return [(row.ticker, str(row.id)) for row in result.all()]


async def add_to_watchlist(
    session: AsyncSession,
    watchlist_id: str,
    asset_id: str,
    notes: str | None = None,
    target_buy: float | None = None,
    target_sell: float | None = None,
) -> WatchlistAsset:
    entry = WatchlistAsset(
        watchlist_id=UUID(watchlist_id),
        asset_id=UUID(asset_id),
        notes=notes,
        target_buy_price=target_buy,
        target_sell_price=target_sell,
    )
    session.add(entry)
    await session.flush()
    return entry


async def remove_from_watchlist(session: AsyncSession, watchlist_id: str, asset_id: str) -> None:
    await session.execute(
        delete(WatchlistAsset).where(
            WatchlistAsset.watchlist_id == UUID(watchlist_id),
            WatchlistAsset.asset_id == UUID(asset_id),
        )
    )
