"""Tests Watchlist Manager — validation tickers et éligibilité PEA (sans appel réseau)."""
import pytest
from app.agents.watchlist_manager import (
    detect_asset_type,
    check_pea_eligibility,
    _parse_yf_info,
)


# ──────────────────────────────────────────────
# detect_asset_type
# ──────────────────────────────────────────────

def test_detect_equity():
    assert detect_asset_type("MC.PA", {}) == "equity"
    assert detect_asset_type("AAPL", {}) == "equity"


def test_detect_commodity():
    assert detect_asset_type("GC=F", {}) == "commodity"
    assert detect_asset_type("CL=F", {}) == "commodity"


def test_detect_index():
    assert detect_asset_type("^FCHI", {}) == "index"
    assert detect_asset_type("^GSPC", {}) == "index"


def test_detect_crypto():
    assert detect_asset_type("BTC-USD", {}) == "crypto"
    assert detect_asset_type("ETH-EUR", {}) == "crypto"


def test_detect_forex():
    assert detect_asset_type("EURUSD=X", {}) == "forex"


# ──────────────────────────────────────────────
# check_pea_eligibility
# ──────────────────────────────────────────────

@pytest.mark.parametrize("ticker,expected", [
    ("MC.PA",  True),   # Euronext Paris
    ("ASML.AS", True),  # Euronext Amsterdam
    ("SAP.DE",  True),  # Xetra
    ("ENI.MI",  True),  # Milan
    ("AAPL",   False),  # NASDAQ
    ("MSFT",   False),  # NASDAQ
    ("BTC-USD", False), # crypto
    ("^FCHI",   False), # index
    ("GC=F",    False), # commodity
])
def test_pea_eligibility_by_suffix(ticker, expected):
    info = {"exchange": "NASDAQ", "quoteType": "EQUITY"}
    assert check_pea_eligibility(ticker, info) is expected


def test_pea_eligible_by_exchange_code():
    info = {"exchange": "XPAR", "quoteType": "EQUITY"}
    assert check_pea_eligibility("SOMESTOCK", info) is True


def test_pea_not_eligible_commodity():
    info = {"exchange": "XPAR", "quoteType": "EQUITY"}
    assert check_pea_eligibility("GC=F", info) is False


def test_pea_etf_ucits():
    info = {
        "exchange": "XPAR",
        "quoteType": "ETF",
        "legalType": "UCITS ETF",
        "fundFamily": "Lyxor",
    }
    assert check_pea_eligibility("LYX.PA", info) is True


def test_pea_etf_non_ucits():
    info = {
        "exchange": "ARCX",
        "quoteType": "ETF",
        "legalType": "Open-Ended Fund",
        "fundFamily": "iShares",
    }
    assert check_pea_eligibility("SPY", info) is False


# ──────────────────────────────────────────────
# _parse_yf_info
# ──────────────────────────────────────────────

def test_parse_yf_info_complete():
    info = {
        "shortName": "LVMH Moët Hennessy",
        "exchange": "XPAR",
        "currency": "EUR",
        "sector": "Consumer Cyclical",
        "country": "France",
        "regularMarketPrice": 720.0,
        "marketCap": 350_000_000_000,
        "quoteType": "EQUITY",
    }
    result = _parse_yf_info("MC.PA", info)

    assert result["valid"] is True
    assert result["ticker"] == "MC.PA"
    assert result["name"] == "LVMH Moët Hennessy"
    assert result["is_pea_eligible"] is True
    assert result["asset_type"] == "equity"
    assert result["exchange_suffix"] == ".PA"
    assert result["currency"] == "EUR"


def test_parse_yf_info_aapl():
    info = {
        "shortName": "Apple Inc.",
        "exchange": "NASDAQ",
        "currency": "USD",
        "quoteType": "EQUITY",
        "regularMarketPrice": 180.0,
    }
    result = _parse_yf_info("AAPL", info)

    assert result["valid"] is True
    assert result["is_pea_eligible"] is False
    assert result["exchange_suffix"] is None
