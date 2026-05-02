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
