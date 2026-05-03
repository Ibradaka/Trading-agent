"""
Backtesting walk-forward — rejoue le scoring engine sur historique yfinance.
Aucune logique parallèle : réutilise les fonctions de scoring existantes.
Aucune fuite de données futures : fenêtre glissante strictement passée.
"""
import asyncio
import structlog
import numpy as np
import pandas as pd

from app.services.yfinance_session import get_yf_session
from app.scoring.technical import compute_technical_score, compute_momentum_score
from app.scoring.composite import compute_composite_score, compute_fusion_score
from app.agents.confidence import compute_confidence
from app.agents.technical import compute_indicators

logger = structlog.get_logger()

_MIN_HISTORY = 52   # bougies minimum avant de générer un signal
_COOLDOWN_DAYS = 4  # jours minimum entre deux signaux (cohérent avec risk.py)


_YF_CHART_URL = (
    "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
    "?interval=1d&range={period}"
)


def _fetch_history(ticker: str, period: str = "5y") -> pd.DataFrame:
    """Fetch historique OHLC via curl_cffi (contourne le blocage datacenter)."""
    try:
        session = get_yf_session()
        r = session.get(_YF_CHART_URL.format(ticker=ticker, period=period), timeout=30)
        data = r.json()
        result = (data.get("chart", {}).get("result") or [None])[0]
        if not result:
            return pd.DataFrame()

        timestamps = result.get("timestamp", [])
        ohlcv = result.get("indicators", {}).get("quote", [{}])[0]
        adjclose = result.get("indicators", {}).get("adjclose", [{}])[0].get("adjclose", [])

        if not timestamps:
            return pd.DataFrame()

        closes = adjclose if adjclose else ohlcv.get("close", [])
        df = pd.DataFrame({
            "open": ohlcv.get("open", []),
            "high": ohlcv.get("high", []),
            "low": ohlcv.get("low", []),
            "close": closes,
            "volume": ohlcv.get("volume", []),
        }, index=pd.to_datetime(timestamps, unit="s", utc=True))

        df = df.dropna(subset=["close"])
        return df
    except Exception as e:
        logger.warning("yfinance curl fetch failed", ticker=ticker, error=str(e))
        return pd.DataFrame()


def _simulate_signals(
    df: pd.DataFrame,
    min_fusion_score: float = 65.0,
    min_confidence: float = 0.40,
    cooldown_days: int = _COOLDOWN_DAYS,
) -> list[dict]:
    """
    Walk-forward : pour chaque bougie i, calcule les indicateurs sur df[:i+1]
    (données strictement passées) et génère un signal si les seuils sont atteints.
    """
    signals = []
    last_signal_idx = -cooldown_days - 1

    for i in range(_MIN_HISTORY, len(df)):
        if i - last_signal_idx <= cooldown_days:
            continue

        window = df.iloc[: i + 1].copy()
        try:
            indicators = compute_indicators(window)
        except Exception:
            continue

        if indicators is None:
            continue

        tech_score = compute_technical_score(indicators)
        mom_score = compute_momentum_score(indicators)

        # Mode backtest : pas de replay sentiment/macro → score technique seul
        # tech_composite = (0.35*tech + 0.20*patterns + 0.20*momentum) / 0.75
        tech_composite = round(
            (0.35 * tech_score + 0.20 * 50.0 + 0.20 * mom_score) / 0.75, 1
        )
        if tech_composite > 65:
            signal_type = "BUY"
        elif tech_composite < 45:
            signal_type = "SELL"
        else:
            continue

        if tech_composite < min_fusion_score:
            continue

        breakdown = compute_composite_score(
            technical=tech_score,
            patterns=50.0,
            momentum=mom_score,
            macro=50.0,
            sentiment=50.0,
        )
        fusion = compute_fusion_score(breakdown)
        fusion["signal_type"] = signal_type
        fusion["score"] = tech_composite

        conf = compute_confidence(
            tech_composite=fusion["technical_composite"],
            sentiment_score=50.0,
            macro_score=50.0,
            has_fresh_sentiment=False,
            has_fresh_macro=False,
        )

        if conf["score"] / 100.0 < min_confidence:
            continue

        signals.append({
            "date": df.index[i],
            "signal_type": fusion["signal_type"],
            "score": round(fusion["score"], 1),
            "confidence": round(conf["score"] / 100.0, 2),
            "confidence_label": conf["label"],
            "price": round(float(df.iloc[i]["close"]), 2),
            "idx": i,
        })
        last_signal_idx = i

    return signals


def _attach_outcomes(
    df: pd.DataFrame, signals: list[dict], horizons: list[int] = [5, 10, 20]
) -> list[dict]:
    """Attache les retours à J+N à chaque signal simulé."""
    for sig in signals:
        i = sig["idx"]
        for h in horizons:
            fi = i + h
            if fi >= len(df):
                sig[f"return_{h}d"] = None
                sig[f"correct_{h}d"] = None
            else:
                future_price = float(df.iloc[fi]["close"])
                ret = round((future_price - sig["price"]) / sig["price"] * 100, 2)
                sig[f"return_{h}d"] = ret
                sig[f"correct_{h}d"] = (
                    ret > 0 if sig["signal_type"] == "BUY" else ret < 0
                )
    return signals


def _compute_metrics(signals: list[dict], horizon: int = 20) -> dict:
    """Métriques de performance agrégées."""
    valid = [s for s in signals if s.get(f"return_{horizon}d") is not None]
    if not valid:
        return {"n_trades": 0, "horizon_days": horizon}

    returns = [s[f"return_{horizon}d"] for s in valid]
    correct = [s[f"correct_{horizon}d"] for s in valid if s.get(f"correct_{horizon}d") is not None]

    win_rate = sum(correct) / len(correct) if correct else 0.0
    avg_return = float(np.mean(returns))
    std_return = float(np.std(returns))

    # Sharpe annualisé
    sharpe = (avg_return / std_return) * (252 / horizon) ** 0.5 if std_return > 0 else 0.0

    # Retour cumulé et drawdown max
    cum = np.cumprod([1 + r / 100 for r in returns])
    cumulative_return = round((float(cum[-1]) - 1) * 100, 2)
    peak = np.maximum.accumulate(cum)
    max_drawdown = round(float(np.min((cum - peak) / peak)) * 100, 2)

    # Calibration par niveau de confiance
    def _winrate(sigs_subset):
        c = [s[f"correct_{horizon}d"] for s in sigs_subset if s.get(f"correct_{horizon}d") is not None]
        return round(sum(c) / len(c) * 100, 1) if c else None

    high = [s for s in valid if s.get("confidence_label") == "high"]
    med = [s for s in valid if s.get("confidence_label") == "medium"]

    return {
        "n_trades": len(valid),
        "win_rate_pct": round(win_rate * 100, 1),
        "avg_return_pct": round(avg_return, 2),
        "sharpe_ratio": round(sharpe, 2),
        "max_drawdown_pct": max_drawdown,
        "cumulative_return_pct": cumulative_return,
        "horizon_days": horizon,
        "calibration": {
            "high_confidence_win_rate_pct": _winrate(high),
            "medium_confidence_win_rate_pct": _winrate(med),
            "n_high": len(high),
            "n_medium": len(med),
        },
    }


def _compute_benchmarks(df: pd.DataFrame, start_idx: int, horizon: int = 20) -> dict:
    """Retours des 3 benchmarks sur la même période."""
    subset = df.iloc[start_idx:]
    if len(subset) < horizon + 50:
        return {}

    closes = subset["close"].values
    first, last = float(closes[0]), float(closes[-1])
    buy_hold = round((last - first) / first * 100, 2)

    # Momentum simple : BUY quand close > SMA20
    sma20 = pd.Series(closes).rolling(20).mean().values
    mom_returns = [
        (closes[i + horizon] - closes[i]) / closes[i] * 100
        for i in range(20, len(closes) - horizon)
        if sma20[i] and closes[i] > sma20[i]
    ]
    momentum_avg = round(float(np.mean(mom_returns)), 2) if mom_returns else 0.0

    # Croisement MA20/MA50
    sma50 = pd.Series(closes).rolling(50).mean().values
    ma_returns = [
        (closes[i + horizon] - closes[i]) / closes[i] * 100
        for i in range(50, len(closes) - horizon)
        if sma20[i] and sma50[i] and sma20[i] > sma50[i]
    ]
    ma_avg = round(float(np.mean(ma_returns)), 2) if ma_returns else 0.0

    return {
        "buy_and_hold_pct": buy_hold,
        "momentum_avg_return_pct": momentum_avg,
        "ma_crossover_avg_return_pct": ma_avg,
    }


async def run_backtest(
    ticker: str,
    period: str = "5y",
    min_fusion_score: float = 65.0,
    horizon_days: int = 20,
) -> dict:
    """
    Lance un backtest walk-forward sur `period` d'historique.
    Retourne métriques, benchmarks et liste des signaux simulés.
    """
    df = await asyncio.to_thread(_fetch_history, ticker, period)
    if df.empty or len(df) < _MIN_HISTORY + horizon_days:
        return {"error": f"Données insuffisantes pour {ticker} (période: {period})"}

    signals = _simulate_signals(df, min_fusion_score=min_fusion_score)
    signals = _attach_outcomes(df, signals, horizons=[5, 10, 20])
    metrics = _compute_metrics(signals, horizon=horizon_days)
    benchmarks = _compute_benchmarks(df, start_idx=_MIN_HISTORY, horizon=horizon_days)

    buy_sigs = [s for s in signals if s["signal_type"] == "BUY"]
    sell_sigs = [s for s in signals if s["signal_type"] == "SELL"]

    return {
        "ticker": ticker.upper(),
        "period": period,
        "total_signals": len(signals),
        "buy_signals": len(buy_sigs),
        "sell_signals": len(sell_sigs),
        "metrics": metrics,
        "benchmarks": benchmarks,
        "signals": [
            {
                "date": s["date"].isoformat(),
                "signal_type": s["signal_type"],
                "score": s["score"],
                "confidence": s["confidence"],
                "confidence_label": s["confidence_label"],
                "price": s["price"],
                "return_5d": s.get("return_5d"),
                "return_10d": s.get("return_10d"),
                "return_20d": s.get("return_20d"),
                "correct_20d": s.get("correct_20d"),
            }
            for s in signals
        ],
    }
