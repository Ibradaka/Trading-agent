# Plan 003 — Scoring, LLM & Backtesting

## Architecture LLM

### Prompt Signal Synthesizer
```
System: Tu es un analyste swing trading expert. Tu analyses les données techniques,
les patterns chartistes, le sentiment et le contexte macro pour produire un signal
d'investissement structuré. Réponds UNIQUEMENT en JSON valide.

User: Actif: {ticker} ({name})
Prix actuel: {price}
Scores: technique={technical}, patterns={patterns}, momentum={momentum}, macro={macro}, sentiment={sentiment}
Indicateurs clés: RSI={rsi}, MACD={macd_cross}, EMA={ema_alignment}
Patterns: {detected_patterns}
Contexte macro: {macro_summary}
Sentiment RSS: {sentiment_summary}
Historique signaux: {last_signals}
```

### Optimisation coûts
- Batch : 1 appel LLM pour 3-5 actifs si même secteur
- Cache : ne re-synthétiser que si un score a changé > 5 points
- JSON mode : `response_format={"type": "json_object"}` → pas de parsing hasardeux

## Backtesting Walk-Forward

### Algorithme
```python
def walk_forward_backtest(ticker, total_years=5, train_months=12, test_months=3):
    windows = generate_windows(total_years, train_months, test_months)
    results = []
    for train_start, train_end, test_start, test_end in windows:
        # 1. Calculer indicateurs sur train (sans regard en avant)
        # 2. Générer signaux sur test avec paramètres du train
        # 3. Simuler positions (pas de levier, stop-loss 5%)
        # 4. Calculer métriques
        results.append(backtest_window(...))
    return aggregate_results(results)
```

### Métriques calculées
- Total return %
- Annualized Sharpe ratio
- Maximum drawdown %
- Win rate %
- Profit factor
- Number of trades
- Average holding period (jours)

## Sentiment RSS — Sources
```python
RSS_FEEDS = {
    "reuters_finance": "https://feeds.reuters.com/reuters/businessNews",
    "les_echos": "https://www.lesechos.fr/rss/rss_finance.xml",
    "investing_stocks": "https://www.investing.com/rss/news_25.rss",
    "boursorama": "https://www.boursorama.com/rss/actu-boursiere.xml",
}
```

### Scoring sentiment (sans LLM)
- Recherche du ticker + nom de la société dans les titres/descriptions
- Keywords positifs : "hausse", "croissance", "record", "surperformance", "acquisition"
- Keywords négatifs : "chute", "perte", "avertissement", "procès", "licenciement"
- Score = (positifs - négatifs) / total_articles × 100, normalisé [0-100]
