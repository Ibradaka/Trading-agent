import pytest
from app.scoring.composite import compute_composite_score, ScoreBreakdown


def test_composite_score_calculation():
    breakdown = compute_composite_score(
        technical=80, patterns=70, momentum=75, macro=60, sentiment=65
    )
    expected = 80*0.35 + 70*0.20 + 75*0.20 + 60*0.15 + 65*0.10
    assert abs(breakdown.composite - expected) < 0.1


def test_composite_score_clamping():
    breakdown = compute_composite_score(
        technical=110, patterns=-5, momentum=50, macro=50, sentiment=50
    )
    assert breakdown.technical == 100.0
    assert breakdown.patterns == 0.0


def test_signal_type_buy_strong():
    breakdown = ScoreBreakdown(technical=85, patterns=80, momentum=78, macro=70, sentiment=65)
    assert breakdown.signal_type == "BUY"
    assert breakdown.signal_strength == "strong"
    assert breakdown.composite > 75


def test_signal_type_hold():
    breakdown = ScoreBreakdown(technical=50, patterns=50, momentum=50, macro=50, sentiment=50)
    assert breakdown.signal_type == "HOLD"
    assert breakdown.signal_strength == "weak"


def test_signal_type_sell_strong():
    breakdown = ScoreBreakdown(technical=15, patterns=20, momentum=18, macro=30, sentiment=25)
    assert breakdown.signal_type == "SELL"
    assert breakdown.signal_strength == "strong"
    assert breakdown.composite < 25


def test_score_breakdown_dict():
    breakdown = compute_composite_score(technical=70, patterns=60, momentum=65, macro=55, sentiment=50)
    d = breakdown.to_dict()
    assert "composite" in d
    assert "signal_type" in d
    assert "signal_strength" in d
    assert d["technical"] == 70.0
