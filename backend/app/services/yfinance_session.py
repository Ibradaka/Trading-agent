"""
Session curl_cffi + helpers Yahoo Finance directs.
Contourne le blocage IP datacenter (TLS fingerprinting).
"""
from curl_cffi.requests import Session

_session: Session | None = None

_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=1mo"
_SUMMARY_URL = (
    "https://query2.finance.yahoo.com/v11/finance/quoteSummary/{ticker}"
    "?modules=price,summaryProfile,assetProfile"
)
_NEWS_URL = (
    "https://query1.finance.yahoo.com/v1/finance/search"
    "?q={ticker}&newsCount=5&enableFuzzyQuery=false&enableEnhancedTrivialQuery=true"
)


def get_yf_session() -> Session:
    global _session
    if _session is None:
        _session = Session(impersonate="chrome110")
    return _session


def yf_chart(ticker: str) -> dict:
    """Retourne le dict meta du chart Yahoo Finance (price, currency, exchange…)."""
    try:
        r = get_yf_session().get(_CHART_URL.format(ticker=ticker), timeout=15)
        results = r.json().get("chart", {}).get("result") or []
        return results[0].get("meta", {}) if results else {}
    except Exception:
        return {}


def yf_chart_full(ticker: str) -> dict:
    """Retourne le résultat complet du chart Yahoo Finance (meta + timestamps + OHLCV)."""
    try:
        r = get_yf_session().get(_CHART_URL.format(ticker=ticker), timeout=15)
        results = r.json().get("chart", {}).get("result") or []
        return results[0] if results else {}
    except Exception:
        return {}


def yf_quote_summary(ticker: str) -> dict:
    """Retourne {price: {…}, summaryProfile: {…}} depuis quoteSummary."""
    try:
        r = get_yf_session().get(_SUMMARY_URL.format(ticker=ticker), timeout=15)
        results = r.json().get("quoteSummary", {}).get("result") or []
        return results[0] if results else {}
    except Exception:
        return {}


def yf_news(ticker: str) -> list[dict]:
    """Retourne les 5 dernières news Yahoo Finance pour un ticker."""
    try:
        r = get_yf_session().get(_NEWS_URL.format(ticker=ticker), timeout=15)
        return r.json().get("news", [])[:5]
    except Exception:
        return []
