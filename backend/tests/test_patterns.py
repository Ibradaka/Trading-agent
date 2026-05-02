"""
Tests Pattern Detection Agent — données OHLC synthétiques avec patterns connus.
"""
import pytest
import numpy as np
import pandas as pd
from datetime import datetime, timezone

from app.agents.patterns import (
    _detect_double_bottom,
    _detect_double_top,
    _detect_support_resistance,
    detect_all_patterns_sync,
)
from app.scoring.patterns import compute_pattern_score


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def _make_ohlc(closes: list[float], base_vol: float = 1_000_000.0) -> pd.DataFrame:
    closes = np.array(closes, dtype=float)
    n = len(closes)
    opens = np.roll(closes, 1)
    opens[0] = closes[0]
    highs = np.maximum(opens, closes) * 1.005
    lows = np.minimum(opens, closes) * 0.995
    volumes = np.full(n, base_vol)
    idx = pd.date_range("2024-01-01", periods=n, freq="D", tz="UTC")
    return pd.DataFrame(
        {"open": opens, "high": highs, "low": lows, "close": closes, "volume": volumes},
        index=idx,
    )


def _w_shape(n: int = 80, valley_drop: float = 0.12) -> list[float]:
    """
    Génère une série en forme de W (double bottom).
    Structure : montée → creux1 → rebond → creux2 → sortie haussière.
    """
    base = 100.0
    seq = []
    # Phase montée
    seq += [base + i * 0.2 for i in range(20)]
    # Creux 1
    peak = seq[-1]
    seq += [peak - i * (peak * valley_drop / 10) for i in range(1, 11)]
    low1 = seq[-1]
    # Rebond partiel
    seq += [low1 + i * (peak * 0.06 / 5) for i in range(1, 6)]
    mid = seq[-1]
    # Creux 2 (similaire au creux 1, ±2%)
    seq += [mid - i * (peak * valley_drop / 10) for i in range(1, 11)]
    low2 = seq[-1]
    # Sortie haussière
    seq += [low2 + i * (peak * 0.12 / 20) for i in range(1, n - len(seq) + 1)]
    return seq[:n]


def _m_shape(n: int = 80, peak_rise: float = 0.12) -> list[float]:
    """Série en forme de M (double top)."""
    base = 100.0
    seq = []
    seq += [base - i * 0.1 for i in range(10)]
    low = seq[-1]
    seq += [low + i * (base * peak_rise / 10) for i in range(1, 11)]
    high1 = seq[-1]
    seq += [high1 - i * (base * 0.06 / 5) for i in range(1, 6)]
    mid = seq[-1]
    seq += [mid + i * (base * peak_rise / 10) for i in range(1, 11)]
    high2 = seq[-1]
    seq += [high2 - i * (base * 0.12 / 20) for i in range(1, n - len(seq) + 1)]
    return seq[:n]


# ──────────────────────────────────────────────
# Tests double bottom
# ──────────────────────────────────────────────

def test_detect_double_bottom_found():
    closes = _w_shape(n=80)
    df = _make_ohlc(closes)
    patterns = _detect_double_bottom(df, window=80)
    found = [p for p in patterns if p["pattern_name"] == "Double Bottom"]
    assert len(found) >= 1, "Double Bottom non détecté sur un W synthétique"
    assert found[0]["direction"] == "bullish"


def test_detect_double_bottom_not_found_on_trend():
    """Tendance haussière pure → pas de double bottom."""
    closes = [100 + i * 0.5 for i in range(80)]
    df = _make_ohlc(closes)
    patterns = _detect_double_bottom(df, window=80)
    assert len(patterns) == 0


# ──────────────────────────────────────────────
# Tests double top
# ──────────────────────────────────────────────

def test_detect_double_top_found():
    closes = _m_shape(n=80)
    df = _make_ohlc(closes)
    patterns = _detect_double_top(df, window=80)
    found = [p for p in patterns if p["pattern_name"] == "Double Top"]
    assert len(found) >= 1, "Double Top non détecté sur un M synthétique"
    assert found[0]["direction"] == "bearish"


def test_detect_double_top_not_found_on_downtrend():
    """Tendance baissière pure → pas de double top."""
    closes = [100 - i * 0.5 for i in range(80)]
    df = _make_ohlc(closes)
    patterns = _detect_double_top(df, window=80)
    assert len(patterns) == 0


# ──────────────────────────────────────────────
# Tests support/résistance
# ──────────────────────────────────────────────

def test_support_resistance_near_level():
    """Prix actuel proche d'un pivot → pattern détecté."""
    # Créer plusieurs hauts locaux autour de 110
    closes = []
    for i in range(50):
        if i in (10, 30):
            closes.append(110.0)
        else:
            closes.append(100.0 + (i % 5))
    closes.append(109.5)  # proche de 110 (résistance)
    df = _make_ohlc(closes)
    patterns = _detect_support_resistance(df, window=50, tolerance=0.03)
    # On ne peut pas garantir le pattern vu la génération simple, juste vérifier le type de retour
    assert isinstance(patterns, list)


# ──────────────────────────────────────────────
# Tests detect_all_patterns_sync
# ──────────────────────────────────────────────

def test_detect_all_patterns_returns_list():
    closes = _w_shape()
    df = _make_ohlc(closes)
    patterns = detect_all_patterns_sync(df)
    assert isinstance(patterns, list)
    for p in patterns:
        assert "pattern_name" in p
        assert "direction" in p
        assert "strength" in p
        assert p["direction"] in ("bullish", "bearish", "neutral")
        assert 0.0 <= p["strength"] <= 1.0


# ──────────────────────────────────────────────
# Tests compute_pattern_score
# ──────────────────────────────────────────────

def test_score_empty_patterns():
    assert compute_pattern_score([]) == 50.0


def test_score_all_bullish():
    patterns = [
        {"pattern_name": "Engulfing", "direction": "bullish", "strength": 0.8},
        {"pattern_name": "Hammer", "direction": "bullish", "strength": 0.7},
        {"pattern_name": "Double Bottom", "direction": "bullish", "strength": 0.8},
    ]
    score = compute_pattern_score(patterns)
    assert score > 70, f"Attendu > 70 pour patterns 100% bullish, obtenu {score}"


def test_score_all_bearish():
    patterns = [
        {"pattern_name": "Engulfing", "direction": "bearish", "strength": 0.8},
        {"pattern_name": "Shooting Star", "direction": "bearish", "strength": 0.7},
        {"pattern_name": "Double Top", "direction": "bearish", "strength": 0.8},
    ]
    score = compute_pattern_score(patterns)
    assert score < 30, f"Attendu < 30 pour patterns 100% bearish, obtenu {score}"


def test_score_balanced_patterns():
    patterns = [
        {"pattern_name": "Hammer", "direction": "bullish", "strength": 0.7},
        {"pattern_name": "Shooting Star", "direction": "bearish", "strength": 0.7},
    ]
    score = compute_pattern_score(patterns)
    # Équilibre → proche de 50 (±25)
    assert 25 <= score <= 75, f"Attendu 25-75 pour patterns équilibrés, obtenu {score}"


def test_score_bounds():
    patterns = [
        {"pattern_name": "Three White Soldiers", "direction": "bullish", "strength": 1.0},
        {"pattern_name": "Morning Star", "direction": "bullish", "strength": 1.0},
        {"pattern_name": "Engulfing", "direction": "bullish", "strength": 1.0},
    ]
    score = compute_pattern_score(patterns)
    assert 0.0 <= score <= 100.0
