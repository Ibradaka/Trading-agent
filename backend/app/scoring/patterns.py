"""
Scoring patterns (0-100).

50 = neutre (aucun pattern ou signaux équilibrés)
>70 = patterns haussiers dominants
<30 = patterns baissiers dominants
"""
from typing import TypedDict


class PatternData(TypedDict):
    pattern_name: str
    direction: str    # bullish | bearish | neutral
    strength: float   # 0.0 – 1.0


PATTERN_WEIGHTS: dict[str, float] = {
    "Three White Soldiers": 1.0,
    "Morning Star": 1.0,
    "Three Black Crows": 1.0,
    "Evening Star": 1.0,
    "Engulfing": 0.9,
    "Double Bottom": 0.85,
    "Double Top": 0.85,
    "Hammer": 0.75,
    "Shooting Star": 0.75,
    "Inverted Hammer": 0.65,
    "Harami": 0.6,
    "Support": 0.6,
    "Resistance": 0.6,
    "Marubozu": 0.55,
    "Doji": 0.3,
}


def compute_pattern_score(patterns: list[PatternData]) -> float:
    """
    Agrège les patterns détectés en un score unique 0-100.
    Chaque pattern contribue proportionnellement à sa force et son poids.
    """
    if not patterns:
        return 50.0

    bullish = 0.0
    bearish = 0.0

    for p in patterns:
        name = p.get("pattern_name", "")
        direction = p.get("direction", "neutral")
        strength = float(p.get("strength", 0.5))
        weight = PATTERN_WEIGHTS.get(name, 0.5)
        contribution = strength * weight * 100.0

        if direction == "bullish":
            bullish += contribution
        elif direction == "bearish":
            bearish += contribution

    total = bullish + bearish
    if total == 0:
        return 50.0

    bullish_ratio = bullish / total   # [0, 1]
    raw_score = bullish_ratio * 100.0

    # Amplifier l'écart à 50 selon l'intensité globale
    intensity = min(total / 200.0, 1.0)
    centered = raw_score - 50.0
    amplified = centered * (0.5 + 0.5 * intensity)

    return max(0.0, min(100.0, 50.0 + amplified))
