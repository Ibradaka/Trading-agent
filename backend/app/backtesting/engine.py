"""
Backtesting walk-forward — rejoue le scoring engine sur historique yfinance.
Aucune logique parallèle : réutilise les fonctions de scoring existantes.
Aucune fuite de données futures : fenêtre glissante strictement passée.
"""
import asyncio
import structlog
import numpy as np
import pandas as pd
from collections import defaultdict

from app.services.yfinance_session import get_yf_session
from app.scoring.technical import compute_technical_score, compute_momentum_score
from app.scoring.composite import compute_composite_score, compute_fusion_score
from app.agents.confidence import compute_confidence
from app.agents.technical import compute_indicators
from app.agents.patterns import detect_all_patterns_sync

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

        # Patterns actifs sur la fenêtre courante
        try:
            active_patterns = detect_all_patterns_sync(window)
        except Exception:
            active_patterns = []

        signals.append({
            "date": df.index[i],
            "signal_type": fusion["signal_type"],
            "score": round(fusion["score"], 1),
            "tech_score": round(tech_score, 1),
            "mom_score": round(mom_score, 1),
            "confidence": round(conf["score"] / 100.0, 2),
            "confidence_label": conf["label"],
            "price": round(float(df.iloc[i]["close"]), 2),
            "idx": i,
            "patterns": [
                {"name": p["pattern_name"], "direction": p["direction"], "strength": p["strength"]}
                for p in active_patterns
            ],
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


def _winrate_for(sigs: list[dict], horizon: int) -> float | None:
    c = [s[f"correct_{horizon}d"] for s in sigs if s.get(f"correct_{horizon}d") is not None]
    return round(sum(c) / len(c) * 100, 1) if c else None


def _avg_return(sigs: list[dict], horizon: int) -> float | None:
    r = [s[f"return_{horizon}d"] for s in sigs if s.get(f"return_{horizon}d") is not None]
    return round(float(np.mean(r)), 2) if r else None


def _sharpe(sigs: list[dict], horizon: int) -> float | None:
    r = [s[f"return_{horizon}d"] for s in sigs if s.get(f"return_{horizon}d") is not None]
    if len(r) < 3:
        return None
    std = float(np.std(r))
    if std == 0:
        return None
    return round((float(np.mean(r)) / std) * (252 / horizon) ** 0.5, 2)


def _compute_diagnostics(signals: list[dict], df: pd.DataFrame, horizon: int = 20) -> dict:
    """
    Analyse de robustesse complète depuis les signaux backtestés.
    Couvre 5.5.2 (qualité), 5.5.3 (score/confiance), 5.5.4 (type signal),
    5.5.5 (patterns), 5.5.6 (sur-trading), 5.5.7 (label), 5.5.8 (recommandation).
    """
    valid = [s for s in signals if s.get(f"return_{horizon}d") is not None]
    n = len(valid)
    if n == 0:
        return {"error": "Pas de signaux valides pour le diagnostic"}

    total_days = len(df)

    # ── 5.5.2 Qualité des signaux ───────────────────────────────────────────
    buy_sigs  = [s for s in valid if s["signal_type"] == "BUY"]
    sell_sigs = [s for s in valid if s["signal_type"] == "SELL"]

    returns_all = [s[f"return_{horizon}d"] for s in valid]
    signal_frequency = round(n / total_days * 252, 1)  # signaux / an annualisé

    correct_all = [s[f"correct_{horizon}d"] for s in valid if s.get(f"correct_{horizon}d") is not None]
    false_signal_rate = round((1 - sum(correct_all) / len(correct_all)) * 100, 1) if correct_all else None

    # Stabilité temporelle : win rate sur première vs deuxième moitié
    mid = n // 2
    first_half  = valid[:mid]
    second_half = valid[mid:]
    wr_first  = _winrate_for(first_half, horizon)
    wr_second = _winrate_for(second_half, horizon)
    stability_delta = round(abs((wr_second or 0) - (wr_first or 0)), 1)

    signal_quality = {
        "total_signals": n,
        "buy_count": len(buy_sigs),
        "sell_count": len(sell_sigs),
        "signal_frequency_per_year": signal_frequency,
        "false_signal_rate_pct": false_signal_rate,
        "return_std_pct": round(float(np.std(returns_all)), 2),
        "return_dispersion_p25": round(float(np.percentile(returns_all, 25)), 2),
        "return_dispersion_p75": round(float(np.percentile(returns_all, 75)), 2),
        "stability_first_half_wr": wr_first,
        "stability_second_half_wr": wr_second,
        "stability_delta_pct": stability_delta,
    }

    # ── 5.5.3 Calibration par score et confiance ──────────────────────────
    score_buckets = {
        "50-60": [s for s in valid if 50 <= s["score"] < 60],
        "60-70": [s for s in valid if 60 <= s["score"] < 70],
        "70-80": [s for s in valid if 70 <= s["score"] < 80],
        "80+":   [s for s in valid if s["score"] >= 80],
    }
    score_calibration = {
        bucket: {
            "n": len(sigs),
            "win_rate_pct": _winrate_for(sigs, horizon),
            "avg_return_pct": _avg_return(sigs, horizon),
        }
        for bucket, sigs in score_buckets.items()
        if sigs
    }

    conf_buckets = {
        "high":   [s for s in valid if s.get("confidence_label") == "high"],
        "medium": [s for s in valid if s.get("confidence_label") == "medium"],
        "low":    [s for s in valid if s.get("confidence_label") == "low"],
    }
    confidence_calibration = {
        label: {
            "n": len(sigs),
            "win_rate_pct": _winrate_for(sigs, horizon),
            "avg_return_pct": _avg_return(sigs, horizon),
        }
        for label, sigs in conf_buckets.items()
        if sigs
    }

    # ── 5.5.4 Performance par type de signal ──────────────────────────────
    by_signal_type = {}
    for sig_type, sigs in [("BUY", buy_sigs), ("SELL", sell_sigs)]:
        if not sigs:
            continue
        by_signal_type[sig_type] = {
            "n": len(sigs),
            "win_rate_pct": _winrate_for(sigs, horizon),
            "avg_return_pct": _avg_return(sigs, horizon),
            "sharpe": _sharpe(sigs, horizon),
        }
        rets = [s[f"return_{horizon}d"] for s in sigs if s.get(f"return_{horizon}d") is not None]
        if len(rets) > 1:
            cum = np.cumprod([1 + r / 100 for r in rets])
            peak = np.maximum.accumulate(cum)
            by_signal_type[sig_type]["max_drawdown_pct"] = round(float(np.min((cum - peak) / peak)) * 100, 2)

    # ── 5.5.5 Performance par pattern de chandelier ───────────────────────
    pattern_stats: dict[str, dict] = defaultdict(lambda: {"outcomes": [], "directions": []})
    for s in valid:
        for p in s.get("patterns", []):
            key = p["name"]
            ret = s.get(f"return_{horizon}d")
            correct = s.get(f"correct_{horizon}d")
            if ret is not None:
                pattern_stats[key]["outcomes"].append({
                    "return": ret,
                    "correct": correct,
                    "signal_type": s["signal_type"],
                    "return_5d": s.get("return_5d"),
                    "return_10d": s.get("return_10d"),
                })
                pattern_stats[key]["directions"].append(p["direction"])

    patterns_analysis = {}
    for name, data in pattern_stats.items():
        outs = data["outcomes"]
        if len(outs) < 2:
            continue
        rets = [o["return"] for o in outs]
        corrects = [o["correct"] for o in outs if o["correct"] is not None]
        r5  = [o["return_5d"]  for o in outs if o.get("return_5d")  is not None]
        r10 = [o["return_10d"] for o in outs if o.get("return_10d") is not None]
        patterns_analysis[name] = {
            "occurrences": len(outs),
            "win_rate_pct": round(sum(corrects) / len(corrects) * 100, 1) if corrects else None,
            "avg_return_pct": round(float(np.mean(rets)), 2),
            "avg_return_5d": round(float(np.mean(r5)), 2) if r5 else None,
            "avg_return_10d": round(float(np.mean(r10)), 2) if r10 else None,
        }
    # Tri par occurrences décroissantes
    patterns_analysis = dict(
        sorted(patterns_analysis.items(), key=lambda x: x[1]["occurrences"], reverse=True)
    )

    # ── 5.5.6 Détection de sur-trading ────────────────────────────────────
    OVERTRADING_FREQ_THRESHOLD = 30   # > 30 signaux/an = suspect
    OVERTRADING_FREQ_EXTREME   = 60   # > 60 signaux/an = sur-trading sévère
    over_traded = signal_frequency > OVERTRADING_FREQ_THRESHOLD

    overtrading_diagnosis = {
        "is_over_traded": over_traded,
        "signal_frequency_per_year": signal_frequency,
        "threshold": OVERTRADING_FREQ_THRESHOLD,
        "severity": (
            "severe" if signal_frequency > OVERTRADING_FREQ_EXTREME
            else "moderate" if over_traded
            else "none"
        ),
    }

    # ── 5.5.7 Label automatique ───────────────────────────────────────────
    win_rate_all = _winrate_for(valid, horizon) or 0.0
    sharpe_all   = _sharpe(valid, horizon) or 0.0
    cum_rets     = [s[f"return_{horizon}d"] for s in valid if s.get(f"return_{horizon}d") is not None]
    cum_final    = float(np.prod([1 + r / 100 for r in cum_rets]) - 1) * 100 if cum_rets else 0.0

    label: str
    label_reason: str

    if over_traded and win_rate_all < 55:
        label = "over_traded"
        label_reason = f"Trop de signaux ({signal_frequency:.0f}/an) avec win rate faible ({win_rate_all:.1f}%)"
    elif stability_delta > 20:
        label = "unstable"
        label_reason = f"Win rate instable : {wr_first}% → {wr_second}% (écart {stability_delta}pts)"
    elif sharpe_all >= 1.2 and win_rate_all >= 60:
        label = "robust"
        label_reason = f"Sharpe {sharpe_all:.2f} + win rate {win_rate_all:.1f}% — moteur bien calibré"
    elif win_rate_all >= 55 and not over_traded:
        label = "noisy"
        label_reason = f"Win rate correct ({win_rate_all:.1f}%) mais Sharpe faible ({sharpe_all:.2f})"
    elif cum_final < -20:
        label = "bearish_asset"
        label_reason = f"Retour cumulé négatif ({cum_final:.1f}%) — actif en tendance baissière sur la période"
    else:
        label = "mixed"
        label_reason = f"Résultats mixtes — win rate {win_rate_all:.1f}%, Sharpe {sharpe_all:.2f}"

    # ── 5.5.8 Recommandation ──────────────────────────────────────────────
    if label == "robust":
        recommendation = "keep"
        recommendation_reason = "Actif fiable — conserver dans la watchlist active"
    elif label in ("over_traded", "unstable"):
        recommendation = "monitor"
        recommendation_reason = "Performances dégradées — surveiller avant d'agir sur les signaux"
    elif label == "bearish_asset":
        recommendation = "exclude"
        recommendation_reason = "Tendance structurellement baissière — exclure ou filtrer SELL uniquement"
    elif label == "noisy":
        recommendation = "monitor"
        recommendation_reason = "Signal utile mais dispersé — augmenter le seuil de confiance minimum"
    else:
        recommendation = "monitor"
        recommendation_reason = "Résultats insuffisants pour conclusion — continuer l'observation"

    return {
        "signal_quality": signal_quality,
        "score_calibration": score_calibration,
        "confidence_calibration": confidence_calibration,
        "by_signal_type": by_signal_type,
        "patterns_analysis": patterns_analysis,
        "overtrading": overtrading_diagnosis,
        "label": label,
        "label_reason": label_reason,
        "recommendation": recommendation,
        "recommendation_reason": recommendation_reason,
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

    buy_sigs  = [s for s in signals if s["signal_type"] == "BUY"]
    sell_sigs = [s for s in signals if s["signal_type"] == "SELL"]
    diagnostics = _compute_diagnostics(signals, df, horizon=horizon_days)

    return {
        "ticker": ticker.upper(),
        "period": period,
        "total_signals": len(signals),
        "buy_signals": len(buy_sigs),
        "sell_signals": len(sell_sigs),
        "metrics": metrics,
        "benchmarks": benchmarks,
        "diagnostics": diagnostics,
        "signals": [
            {
                "date": s["date"].isoformat(),
                "signal_type": s["signal_type"],
                "score": s["score"],
                "tech_score": s.get("tech_score"),
                "mom_score": s.get("mom_score"),
                "confidence": s["confidence"],
                "confidence_label": s["confidence_label"],
                "price": s["price"],
                "return_5d": s.get("return_5d"),
                "return_10d": s.get("return_10d"),
                "return_20d": s.get("return_20d"),
                "correct_20d": s.get("correct_20d"),
                "patterns": s.get("patterns", []),
            }
            for s in signals
        ],
    }
