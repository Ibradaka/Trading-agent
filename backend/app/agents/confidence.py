"""
Confidence Engine — mesure la qualité d'un signal par convergence des agents.

Inputs : scores 0-100 des 3 agents (technical_composite, sentiment, macro).
Output : {"score": float, "label": str, "reasons": list[str]}
"""
import statistics


def compute_confidence(
    tech_composite: float,
    sentiment_score: float,
    macro_score: float,
    has_fresh_sentiment: bool = False,
    has_fresh_macro: bool = False,
) -> dict:
    """
    Retourne {"score": float 0-100, "label": "high"|"medium"|"low", "reasons": list[str]}.

    Critères évalués :
    1. Convergence directionnelle des 3 agents
    2. Dispersion (écart-type entre les scores)
    3. Fraîcheur des données (sentiment + macro)
    """
    score = 60.0
    reasons: list[str] = []

    def _direction(s: float) -> int:
        return 1 if s > 55 else (-1 if s < 45 else 0)

    dirs = [_direction(tech_composite), _direction(sentiment_score), _direction(macro_score)]
    non_neutral = [d for d in dirs if d != 0]

    if not non_neutral:
        score -= 10
        reasons.append("tous les agents neutres")
    else:
        agreement = abs(sum(non_neutral) / len(non_neutral))
        if agreement == 1.0:
            score += 20
            reasons.append("convergence parfaite des 3 agents")
        elif agreement >= 0.66:
            score += 10
            reasons.append("2 agents convergents")
        else:
            score -= 15
            reasons.append("divergence entre agents")

    # Pénalité de dispersion
    try:
        std = statistics.stdev([tech_composite, sentiment_score, macro_score])
        if std > 25:
            score -= 15
            reasons.append(f"forte dispersion entre agents (σ={std:.0f})")
        elif std > 15:
            score -= 7
            reasons.append(f"dispersion modérée (σ={std:.0f})")
    except statistics.StatisticsError:
        pass

    # Pénalité données manquantes / par défaut
    if not has_fresh_sentiment:
        score -= 8
        reasons.append("sentiment : données non fraîches (défaut 50)")
    if not has_fresh_macro:
        score -= 8
        reasons.append("macro : données FRED indisponibles (défaut 50)")

    score = max(10.0, min(95.0, round(score, 1)))
    label = "high" if score >= 70 else ("medium" if score >= 45 else "low")

    return {"score": score, "label": label, "reasons": reasons}


# Ordre hiérarchique des niveaux de confiance
_CONFIDENCE_RANK = {"low": 0, "medium": 1, "high": 2}
_CONFIDENCE_SCORE_CAP = {"low": 44.9, "medium": 69.9, "high": 95.0}


def apply_confidence_cap(confidence: dict, max_label: str) -> dict:
    """
    Plafonne le niveau de confiance selon le profil de l'actif.
    Si le label calculé dépasse max_label, on ramène label ET score au cap.
    """
    if _CONFIDENCE_RANK.get(confidence["label"], 0) <= _CONFIDENCE_RANK.get(max_label, 2):
        return confidence  # déjà sous le cap, rien à faire

    capped_score = min(confidence["score"], _CONFIDENCE_SCORE_CAP[max_label])
    return {
        "score": capped_score,
        "label": max_label,
        "reasons": confidence["reasons"] + [f"confiance plafonnée à '{max_label}' (profil actif)"],
    }
