# Spec 003 — Scoring, LLM & Backtesting

## Objectif
Implémenter le scoring composite, les agents IA (Sentiment, Macro, Signal Synthesizer)
et le moteur de backtesting walk-forward pour valider les pondérations du scoring.

## Agents LLM

### Sentiment Agent (RSS-based, sans LLM)
Analyse les flux RSS de sources financières pour scorer le sentiment sur un actif.
Sources : Reuters, Google Finance RSS, Investing.com RSS, Les Echos.

### Macro Contextualizer (FRED + GPT-4o-mini)
Synthétise l'environnement macro pour contextualiser les signaux.
Données FRED : taux Fed, CPI, NFP, courbe des taux 2Y/10Y, DXY.

### Signal Synthesizer (GPT-4o-mini — le cerveau)
Agrège TOUS les scores et produit la décision finale avec raisonnement explicite.
Output JSON strict, validé par Pydantic.
Fallback : si LLM indisponible → score technique pur.

## Score composite

```
composite_score = (
    technical_score  * 0.35 +
    pattern_score    * 0.20 +
    momentum_score   * 0.20 +
    macro_score      * 0.15 +
    sentiment_score  * 0.10
)
```

## Critères d'acceptation

- [ ] Signal Synthesizer retourne JSON valide (validé Pydantic) pour 5 actifs tests
- [ ] Fallback déterministe activé si openai.APIError → signal calculé sans LLM
- [ ] Cache Redis TTL 15min sur sentiment, 6h sur macro
- [ ] Backtesting sur 5 ans OHLC (yfinance) sans look-ahead bias
- [ ] Walk-forward : fenêtre d'entraînement 12 mois, fenêtre de test 3 mois
- [ ] Résultats backtesting stockés en DB et affichables sur le dashboard
- [ ] Coût LLM estimé < 10€/mois avec batch + cache

## Output Signal Synthesizer

```json
{
  "asset": "MC.PA",
  "signal": "BUY",
  "strength": "strong",
  "composite_score": 78,
  "confidence": 0.82,
  "horizon": "5-10 jours",
  "reasoning": "Convergence haussière : RSI sortant de survente (28→35), MACD croisement signal haussier, EMA20 > EMA50, sentiment RSS positif sur luxury sector, macro BCE accommodante.",
  "risks": ["Résistance à 720€", "Publication résultats Q4 vendredi"],
  "invalidation_conditions": "Clôture sous 695€",
  "scores_breakdown": {
    "technical": 72,
    "patterns": 65,
    "momentum": 80,
    "macro": 70,
    "sentiment": 60
  }
}
```
