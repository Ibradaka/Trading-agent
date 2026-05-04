from dataclasses import dataclass


@dataclass
class ScoreBreakdown:
    technical: float   # 0-100
    patterns: float    # 0-100
    momentum: float    # 0-100
    macro: float       # 0-100
    sentiment: float   # 0-100

    @property
    def composite(self) -> float:
        """Score composite pondéré (0-100)."""
        return round(
            self.technical  * 0.35 +
            self.patterns   * 0.20 +
            self.momentum   * 0.20 +
            self.macro      * 0.15 +
            self.sentiment  * 0.10,
            1,
        )

    @property
    def signal_type(self) -> str:
        score = self.composite
        if score >= 75:
            return "BUY"
        elif score >= 60:
            return "BUY"
        elif score >= 40:
            return "HOLD"
        elif score >= 25:
            return "SELL"
        else:
            return "SELL"

    @property
    def signal_strength(self) -> str:
        score = self.composite
        if score >= 75 or score <= 25:
            return "strong"
        return "weak"

    def to_dict(self) -> dict:
        return {
            "composite": self.composite,
            "technical": self.technical,
            "patterns": self.patterns,
            "momentum": self.momentum,
            "macro": self.macro,
            "sentiment": self.sentiment,
            "signal_type": self.signal_type,
            "signal_strength": self.signal_strength,
        }


def compute_composite_score(
    technical: float,
    patterns: float,
    momentum: float,
    macro: float = 50.0,
    sentiment: float = 50.0,
) -> ScoreBreakdown:
    """Point d'entrée principal pour calculer le score composite."""
    return ScoreBreakdown(
        technical=max(0.0, min(100.0, technical)),
        patterns=max(0.0, min(100.0, patterns)),
        momentum=max(0.0, min(100.0, momentum)),
        macro=max(0.0, min(100.0, macro)),
        sentiment=max(0.0, min(100.0, sentiment)),
    )


def compute_fusion_score(breakdown: ScoreBreakdown) -> dict:
    """
    Signal Fusion Engine — décision déterministe et backtestable.

    Formule : 0.50 * technical_composite + 0.25 * sentiment + 0.25 * macro
    où technical_composite = agrégat normalisé de technical/patterns/momentum (75% du composite).

    Seuils : BUY > 65, SELL < 45, HOLD entre les deux.
    """
    # Normalise les 3 composantes techniques (35+20+20 = 75%) vers 0-100
    tech_composite = round(
        (0.35 * breakdown.technical + 0.20 * breakdown.patterns + 0.20 * breakdown.momentum)
        / 0.75,
        1,
    )

    score = round(
        0.50 * tech_composite
        + 0.25 * breakdown.sentiment
        + 0.25 * breakdown.macro,
        1,
    )
    score = max(0.0, min(100.0, score))

    if score > 60:
        signal_type = "BUY"
        signal_strength = "strong" if score > 72 else "weak"
    elif score < 42:
        signal_type = "SELL"
        signal_strength = "strong" if score < 28 else "weak"
    else:
        signal_type = "HOLD"
        signal_strength = "weak"

    return {
        "score": score,
        "signal_type": signal_type,
        "signal_strength": signal_strength,
        "technical_composite": tech_composite,
        "weights": {"technical": 0.50, "sentiment": 0.25, "macro": 0.25},
    }
