# Spec 002 — Agents Core (Déterministes)

## Objectif
Implémenter les 5 agents déterministes qui forment le cœur du pipeline d'analyse.
Ces agents n'utilisent PAS de LLM — pur Python déterministe, testable, gratuit.

## Agents concernés

1. **Watchlist Manager** — CRUD actifs, validation tickers, éligibilité PEA
2. **Market Data Agent** — Collecte OHLC via yfinance
3. **Technical Analysis Agent** — Calcul de tous les indicateurs techniques
4. **Pattern Detection Agent** — Chandeliers japonais + figures chartistes
5. **Risk/Confidence Agent** — Filtres, pondération, niveau de confiance

## User stories

**En tant qu'utilisateur**, je peux :
- Ajouter un ticker à une watchlist → validation automatique + enrichissement métadonnées
- Voir instantanément si un actif est éligible PEA
- Lancer une analyse technique sur n'importe quel actif de ma watchlist
- Obtenir un score technique (0-100) avec le détail composante par composante

**En tant que système**, le scheduler doit :
- Fetcher les données OHLC toutes les 15 min (heures marché uniquement)
- Calculer les indicateurs après chaque fetch
- Détecter les patterns après chaque calcul
- Filtrer les signaux selon les règles de risque
- Publier les résultats sur Redis pour le Signal Synthesizer

## Critères d'acceptation

- [ ] `validate_ticker("MC.PA")` retourne `{valid: true, name: "LVMH", is_pea_eligible: true}`
- [ ] `validate_ticker("AAPL")` retourne `{valid: true, name: "Apple Inc.", is_pea_eligible: false}`
- [ ] `validate_ticker("INVALID")` retourne `{valid: false}`
- [ ] L'agent Market Data écrit en TimescaleDB sans erreur pour 10 tickers simultanés
- [ ] L'agent Technical Analysis calcule correctement RSI(14), MACD(12,26,9), EMA(20/50/200)
- [ ] Le score technique pour un RSI < 30 + MACD croisement haussier est > 65
- [ ] L'agent Pattern Detection détecte correctement un engulfing haussier sur données synthétiques
- [ ] Les tests pytest couvrent 100% de la logique de scoring
- [ ] Heures de marché respectées (pas de fetch le week-end ou hors 09h-17h30 CET)

## Scoring technique (détail)

```
Score technique (0-100) :
  MACD :         ±20 pts (croisement signal)
  RSI :          ±25 pts (zones survente/surachat/neutre)
  EMA alignment: +20 pts (ema9 > ema21 > sma50 = tendance propre)
  Bollinger :    ±15 pts (prix vs bandes)
  Volume :       +10 pts (confirmation par volume)
  Stochastique : ±10 pts
  Normalisation : max(0, min(100, points + 50))
```

## Règles éligibilité PEA
Éligibles : Euronext Paris (.PA), Amsterdam (.AS), Bruxelles (.BR), Lisbonne (.LS), Xetra (.DE), Milan (.MI), Madrid (.MC)
Non éligibles : NASDAQ, NYSE, crypto, commodities, indices, forex
Exception : ETFs UCITS domiciliés en Europe (à vérifier via metadata `fundFamily`)
