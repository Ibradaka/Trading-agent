"""
Tests Technical Analysis Agent — données OHLC synthétiques → indicateurs + scores.
Tous les calculs sont déterministes, pas d'appel réseau.
"""
import pytest
import numpy as np
import pandas as pd
from datetime import datetime, timezone

from app.agents.technical import compute_indicators
from app.scoring.technical import compute_technical_score, compute_momentum_score


# ──────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────

def _make_df(
    n: int = 250,
    start_price: float = 100.0,
    trend: float = 0.001,
    noise: float = 0.01,
    seed: int = 42,
) -> pd.DataFrame:
    """DataFrame OHLC synthétique avec tendance haussière légère."""
    rng = np.random.default_rng(seed)
    closes = [start_price]
    for _ in range(n - 1):
        closes.append(closes[-1] * (1 + trend + rng.normal(0, noise)))

    closes = np.array(closes)
    opens = closes * (1 + rng.normal(0, 0.002, n))
    highs = np.maximum(opens, closes) * (1 + rng.uniform(0.001, 0.015, n))
    lows = np.minimum(opens, closes) * (1 - rng.uniform(0.001, 0.015, n))
    volumes = rng.uniform(500_000, 2_000_000, n)

    idx = pd.date_range("2024-01-01", periods=n, freq="D", tz="UTC")
    return pd.DataFrame(
        {"open": opens, "high": highs, "low": lows, "close": closes, "volume": volumes},
        index=idx,
    )


def _make_oversold_df(n: int = 250) -> pd.DataFrame:
    """DataFrame avec forte baisse récente → RSI < 30."""
    df = _make_df(n, trend=-0.005, noise=0.005)
    # Crash final : -30% sur les 15 derniers jours
    for i in range(n - 15, n):
        df.iloc[i, df.columns.get_loc("close")] *= 0.98
    return df


def _make_overbought_df(n: int = 250) -> pd.DataFrame:
    """DataFrame avec forte hausse récente → RSI > 70."""
    df = _make_df(n, trend=0.012, noise=0.003)
    return df


# ──────────────────────────────────────────────
# Tests compute_indicators
# ──────────────────────────────────────────────

def test_compute_indicators_returns_expected_keys():
    df = _make_df()
    ind = compute_indicators(df)
    assert ind is not None

    required = [
        "ema20", "ema50", "ema200", "sma20", "sma50", "sma200",
        "rsi", "macd", "macd_signal", "macd_histogram",
        "stoch_k", "stoch_d", "williams_r",
        "bb_upper", "bb_middle", "bb_lower",
        "atr", "obv", "adx",
        "close", "volume", "volume_ma20",
    ]
    for key in required:
        assert key in ind, f"Clé manquante : {key}"


def test_compute_indicators_none_when_insufficient_data():
    df = _make_df(n=20)  # < 26 bougies
    assert compute_indicators(df) is None


def test_indicators_rsi_range():
    df = _make_df()
    ind = compute_indicators(df)
    assert ind is not None
    rsi = ind["rsi"]
    if rsi is not None:
        assert 0 <= rsi <= 100, f"RSI hors borne : {rsi}"


def test_indicators_bollinger_ordering():
    df = _make_df()
    ind = compute_indicators(df)
    assert ind is not None
    bb_l = ind["bb_lower"]
    bb_m = ind["bb_middle"]
    bb_u = ind["bb_upper"]
    if all(v is not None for v in [bb_l, bb_m, bb_u]):
        assert bb_l <= bb_m <= bb_u, "Bollinger bands mal ordonnées"


# ──────────────────────────────────────────────
# Tests compute_technical_score
# ──────────────────────────────────────────────

def test_technical_score_range():
    df = _make_df()
    ind = compute_indicators(df)
    assert ind is not None
    score = compute_technical_score(ind)
    assert 0.0 <= score <= 100.0


def test_technical_score_oversold_is_high():
    """RSI < 30 + tendance baissière → score élevé (survente = achat)."""
    df = _make_oversold_df()
    ind = compute_indicators(df)
    if ind is None:
        pytest.skip("Données insuffisantes")
    rsi = ind.get("rsi")
    if rsi is None or rsi >= 40:
        pytest.skip(f"RSI={rsi} — pas assez survendu pour ce test")
    score = compute_technical_score(ind)
    assert score > 55, f"Score attendu > 55 pour RSI={rsi:.1f}, obtenu {score:.1f}"


def test_technical_score_overbought_is_low():
    """RSI > 70 + tendance haussière forte → score bas (surachat = risque)."""
    df = _make_overbought_df()
    ind = compute_indicators(df)
    if ind is None:
        pytest.skip("Données insuffisantes")
    rsi = ind.get("rsi")
    if rsi is None or rsi <= 60:
        pytest.skip(f"RSI={rsi} — pas assez suracheté pour ce test")
    score = compute_technical_score(ind)
    assert score < 55, f"Score attendu < 55 pour RSI={rsi:.1f}, obtenu {score:.1f}"


def test_technical_score_rsi_below30_macd_bullish_above_65():
    """
    Critère spec-002 : RSI < 30 + croisement MACD haussier → score > 65.
    On injecte directement un indicateur synthétique.
    """
    ind = {
        "rsi": 28.0,
        "macd_histogram": 0.5,
        "prev_macd_histogram": -0.3,
        "ema20": 100.0, "ema50": 95.0, "ema200": 90.0,
        "close": 102.0,
        "bb_upper": 110.0, "bb_lower": 90.0, "bb_middle": 100.0,
        "volume": 1_500_000.0, "volume_ma20": 1_000_000.0,
        "stoch_k": 22.0, "stoch_d": 25.0, "prev_stoch_k": 20.0,
    }
    score = compute_technical_score(ind)
    assert score > 65, f"Attendu > 65, obtenu {score}"


def test_technical_score_neutral_around_50():
    """Indicateurs neutres → score ~50 (±15)."""
    ind = {
        "rsi": 50.0,
        "macd_histogram": 0.0,
        "prev_macd_histogram": 0.0,
        "ema20": 100.0, "ema50": 100.0, "ema200": 100.0,
        "close": 100.0,
        "bb_upper": 110.0, "bb_lower": 90.0, "bb_middle": 100.0,
        "volume": 1_000_000.0, "volume_ma20": 1_000_000.0,
        "stoch_k": 50.0, "stoch_d": 50.0, "prev_stoch_k": 49.0,
    }
    score = compute_technical_score(ind)
    assert 35.0 <= score <= 65.0, f"Score neutre attendu 35-65, obtenu {score}"


# ──────────────────────────────────────────────
# Tests compute_momentum_score
# ──────────────────────────────────────────────

def test_momentum_score_range():
    df = _make_df()
    ind = compute_indicators(df)
    assert ind is not None
    score = compute_momentum_score(ind)
    assert 0.0 <= score <= 100.0


def test_momentum_score_oversold_indicators():
    ind = {
        "rsi": 20.0,
        "macd_histogram": 0.5,
        "prev_macd_histogram": -0.1,
        "williams_r": -85.0,
        "stoch_k": 12.0,
    }
    score = compute_momentum_score(ind)
    assert score > 70, f"Momentum fort attendu > 70, obtenu {score}"


def test_momentum_score_overbought_indicators():
    ind = {
        "rsi": 80.0,
        "macd_histogram": -0.5,
        "prev_macd_histogram": 0.2,
        "williams_r": -10.0,
        "stoch_k": 90.0,
    }
    score = compute_momentum_score(ind)
    assert score < 30, f"Momentum baissier attendu < 30, obtenu {score}"
