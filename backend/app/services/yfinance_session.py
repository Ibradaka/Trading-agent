"""
Session yfinance avec impersonation Chrome via curl_cffi.
Contourne le blocage IP datacenter de Yahoo Finance.
"""
from curl_cffi.requests import Session

_session: Session | None = None


def get_yf_session() -> Session:
    global _session
    if _session is None:
        _session = Session(impersonate="chrome110")
    return _session
