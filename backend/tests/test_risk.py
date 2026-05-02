"""
Tests Risk & Confidence Agent — filtres et calcul de confiance.
Pas d'accès DB ni Redis (mocks).
"""
import pytest
from unittest.mock import AsyncMock, patch

from app.agents.risk import (
    _volume_filter,
    _volatility_filter,
    _score_filter,
    _trend_filter,
    compute_confidence,
    RiskAssessment,
    assess_risk,
)


# ──────────────────────────────────────────────
# Tests filtres individuels
# ──────────────────────────────────────────────

class TestVolumeFilter:
    def test_ok_above_threshold(self):
        ind = {"volume": 1_500_000.0, "volume_ma20": 1_000_000.0}
        ok, msg = _volume_filter(ind)
        assert ok is True
        assert "ok" in msg

    def test_fail_below_threshold(self):
        ind = {"volume": 200_000.0, "volume_ma20": 1_000_000.0}
        ok, msg = _volume_filter(ind)
        assert ok is False
        assert "faible" in msg

    def test_missing_data_passes(self):
        ok, _ = _volume_filter({})
        assert ok is True

    def test_zero_ma_passes(self):
        ok, _ = _volume_filter({"volume": 0, "volume_ma20": 0})
        assert ok is True


class TestVolatilityFilter:
    def test_ok_normal_atr(self):
        ind = {"atr": 2.0, "close": 100.0}   # 2%
        ok, msg = _volatility_filter(ind)
        assert ok is True

    def test_fail_high_atr(self):
        ind = {"atr": 10.0, "close": 100.0}  # 10% > seuil 8%
        ok, msg = _volatility_filter(ind)
        assert ok is False
        assert "excessive" in msg

    def test_missing_data_passes(self):
        ok, _ = _volatility_filter({})
        assert ok is True


class TestScoreFilter:
    def test_strong_buy_passes(self):
        ok, _ = _score_filter(75.0)
        assert ok is True

    def test_strong_sell_passes(self):
        ok, _ = _score_filter(20.0)
        assert ok is True

    def test_neutral_fails(self):
        ok, msg = _score_filter(50.0)
        assert ok is False
        assert "neutre" in msg

    def test_borderline_just_above_passes(self):
        ok, _ = _score_filter(61.0)
        assert ok is True

    def test_borderline_just_below_fails(self):
        ok, _ = _score_filter(59.0)
        assert ok is False


class TestTrendFilter:
    def test_buy_with_bullish_trend_passes(self):
        ind = {"ema20": 105.0, "ema50": 100.0, "close": 108.0}
        ok, msg = _trend_filter(ind, "BUY")
        assert ok is True

    def test_buy_against_bearish_trend_fails(self):
        ind = {"ema20": 95.0, "ema50": 100.0, "close": 90.0}
        ok, msg = _trend_filter(ind, "BUY")
        assert ok is False
        assert "contre_trend" in msg

    def test_sell_with_bearish_trend_passes(self):
        ind = {"ema20": 95.0, "ema50": 100.0, "close": 92.0}
        ok, msg = _trend_filter(ind, "SELL")
        assert ok is True

    def test_sell_against_bullish_trend_fails(self):
        ind = {"ema20": 105.0, "ema50": 100.0, "close": 108.0}
        ok, msg = _trend_filter(ind, "SELL")
        assert ok is False

    def test_missing_data_passes(self):
        ok, _ = _trend_filter({}, "BUY")
        assert ok is True


# ──────────────────────────────────────────────
# Tests compute_confidence
# ──────────────────────────────────────────────

class TestComputeConfidence:
    def test_convergent_signals_high_confidence(self):
        # tech, momentum, patterns tous haussiers
        conf = compute_confidence(
            technical_score=75.0,
            pattern_score=72.0,
            momentum_score=70.0,
            volume_ratio=1.6,
            patterns_count=3,
            atr_pct=0.025,
        )
        assert conf > 0.70, f"Convergence forte attendue > 0.70, obtenu {conf}"

    def test_divergent_signals_low_confidence(self):
        # tech haussier mais patterns baissiers
        conf = compute_confidence(
            technical_score=72.0,
            pattern_score=25.0,
            momentum_score=30.0,
            volume_ratio=0.4,
            patterns_count=1,
            atr_pct=0.07,
        )
        assert conf < 0.55, f"Divergence → confiance basse attendue < 0.55, obtenu {conf}"

    def test_confidence_bounds(self):
        for tech, pat, mom in [(0, 0, 0), (100, 100, 100), (50, 50, 50)]:
            conf = compute_confidence(tech, pat, mom, 1.0, 0, 0.02)
            assert 0.05 <= conf <= 0.95

    def test_high_volume_boosts_confidence(self):
        base = compute_confidence(75, 70, 70, 1.0, 2, 0.025)
        high = compute_confidence(75, 70, 70, 2.0, 2, 0.025)
        assert high > base


# ──────────────────────────────────────────────
# Tests assess_risk (intégration, mock Redis)
# ──────────────────────────────────────────────

@pytest.mark.asyncio
class TestAssessRisk:
    @pytest.fixture
    def good_indicators(self):
        return {
            "rsi": 35.0,
            "macd_histogram": 0.5,
            "prev_macd_histogram": -0.2,
            "ema20": 100.0, "ema50": 95.0, "ema200": 90.0,
            "close": 102.0,
            "bb_upper": 110.0, "bb_lower": 90.0, "bb_middle": 100.0,
            "volume": 1_500_000.0, "volume_ma20": 1_000_000.0,
            "stoch_k": 25.0, "stoch_d": 28.0, "prev_stoch_k": 22.0,
            "atr": 2.0, "williams_r": -75.0,
        }

    @pytest.fixture
    def good_patterns(self):
        return [
            {"pattern_name": "Hammer", "direction": "bullish", "strength": 0.7},
            {"pattern_name": "Double Bottom", "direction": "bullish", "strength": 0.8},
        ]

    async def test_strong_buy_passes_all_filters(self, good_indicators, good_patterns):
        with patch("app.agents.risk.cache_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None  # pas de cooldown
            result = await assess_risk(
                ticker="MC.PA",
                indicators=good_indicators,
                composite_score=72.0,
                technical_score=70.0,
                pattern_score=68.0,
                momentum_score=65.0,
                patterns=good_patterns,
            )

        assert result.passed is True
        assert "volume" in result.filters_passed
        assert "cooldown" in result.filters_passed
        assert "score" in result.filters_passed
        assert result.confidence > 0.5

    async def test_cooldown_blocks_signal(self, good_indicators, good_patterns):
        with patch("app.agents.risk.cache_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {"at": "2026-05-02T10:00:00Z"}  # cooldown actif
            result = await assess_risk(
                ticker="MC.PA",
                indicators=good_indicators,
                composite_score=75.0,
                technical_score=72.0,
                pattern_score=70.0,
                momentum_score=68.0,
                patterns=good_patterns,
            )

        assert result.passed is False
        assert "cooldown" in result.filters_failed

    async def test_low_volume_blocks_signal(self, good_patterns):
        low_vol_ind = {
            "volume": 100_000.0,
            "volume_ma20": 1_000_000.0,
            "close": 100.0, "atr": 1.5,
            "ema20": 102.0, "ema50": 98.0,
        }
        with patch("app.agents.risk.cache_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None
            result = await assess_risk(
                ticker="TEST",
                indicators=low_vol_ind,
                composite_score=70.0,
                technical_score=65.0,
                pattern_score=60.0,
                momentum_score=60.0,
                patterns=good_patterns,
            )

        assert result.passed is False
        assert "volume" in result.filters_failed

    async def test_neutral_score_blocked(self, good_indicators, good_patterns):
        with patch("app.agents.risk.cache_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None
            result = await assess_risk(
                ticker="TEST",
                indicators=good_indicators,
                composite_score=50.0,   # neutre
                technical_score=50.0,
                pattern_score=50.0,
                momentum_score=50.0,
                patterns=[],
            )

        assert result.passed is False
        assert "score" in result.filters_failed
