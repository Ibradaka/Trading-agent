# Tasks 003 — Scoring, LLM & Backtesting

## État : EN ATTENTE (après spec-002)

### Scoring composite
- [ ] `backend/app/scoring/composite.py` — compute_composite_score avec pondérations
- [ ] `backend/app/scoring/momentum.py` — score momentum (ROC, OBV trend, Stoch)
- [ ] Tests : calcul score composite avec scores partiels connus

### Sentiment Agent (RSS)
- [ ] `backend/app/agents/sentiment.py` — fetch RSS feeds (feedparser)
- [ ] `backend/app/agents/sentiment.py` — scoring sentiment par actif (keyword matching)
- [ ] `backend/app/agents/sentiment.py` — cache Redis TTL 15min
- [ ] `backend/app/services/scheduler.py` — job sentiment 15min

### Macro Agent (FRED + LLM)
- [ ] `backend/app/agents/macro.py` — fetch FRED (taux, CPI, NFP, courbe taux)
- [ ] `backend/app/agents/macro.py` — calcul macro_score déterministe (sans LLM)
- [ ] `backend/app/agents/macro.py` — enrichissement LLM (narrative)
- [ ] `backend/app/agents/macro.py` — cache Redis TTL 6h
- [ ] `backend/app/services/scheduler.py` — job macro 6h

### Signal Synthesizer (LLM)
- [ ] `backend/app/agents/signal_synthesizer.py` — prompt engineering + JSON mode strict
- [ ] `backend/app/agents/signal_synthesizer.py` — validation Pydantic output
- [ ] `backend/app/agents/signal_synthesizer.py` — fallback déterministe si LLM down
- [ ] `backend/app/agents/signal_synthesizer.py` — sauvegarde signal en DB
- [ ] `backend/app/agents/signal_synthesizer.py` — publication Redis "signal:new:{ticker}"
- [ ] Tests : mock OpenAI → validation structure JSON output

### Backtesting
- [ ] `backend/app/backtesting/engine.py` — walk-forward backtesting sur yfinance historique
- [ ] `backend/app/backtesting/engine.py` — calcul métriques (Sharpe, max drawdown, win rate)
- [ ] `backend/app/backtesting/engine.py` — sauvegarde résultats en DB
- [ ] Endpoint `GET /api/backtest/{ticker}` — résultats backtesting
- [ ] Endpoint `POST /api/backtest/run` — lancer backtest à la demande
- [ ] Tests : backtest sur données synthétiques avec résultat connu

### Accuracy tracking
- [ ] `backend/app/services/outcome_tracker.py` — vérifie les signaux après N jours
- [ ] Job scheduler quotidien : vérifie les signaux de J-5, J-10, J-20
- [ ] Stockage résultats dans `signal_outcomes`
