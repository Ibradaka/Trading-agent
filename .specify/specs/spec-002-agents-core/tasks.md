# Tasks 002 — Agents Core (Déterministes)

## État : TERMINÉ ✅

---

### Watchlist Manager
- [x] `backend/app/agents/watchlist_manager.py` — validate_ticker, detect_asset_type, check_pea_eligibility
- [x] `backend/app/agents/watchlist_manager.py` — CRUD logic (add/remove/pause/update)
- [x] `backend/app/routers/watchlist.py` — endpoints CRUD complets avec validation
- [x] `backend/app/routers/assets.py` — search autocomplete + validate endpoint
- [x] Tests : `tests/test_watchlist_manager.py` — validation tickers (PEA/non-PEA/invalid)

### Market Data Agent
- [x] `backend/app/agents/market_data.py` — fetch_ohlc avec asyncio.to_thread
- [x] `backend/app/agents/market_data.py` — écriture TimescaleDB (ON CONFLICT DO UPDATE)
- [x] `backend/app/agents/market_data.py` — gestion heures marché (exchange_calendars)
- [x] `backend/app/agents/market_data.py` — publication Redis "data:updated:{ticker}"
- [x] `backend/app/services/scheduler.py` — job fetch 15min configuré

### Technical Analysis Agent
- [x] `backend/app/agents/technical.py` — calcul tous indicateurs (pandas-ta)
- [x] `backend/app/agents/technical.py` — génération signaux atomiques
- [x] `backend/app/agents/technical.py` — écriture technical_indicators en DB
- [x] `backend/app/agents/technical.py` — publication Redis "indicators:updated:{ticker}"
- [x] `backend/app/scoring/technical.py` — compute_technical_score (0-100)
- [x] `backend/app/scoring/technical.py` — compute_momentum_score (0-100)
- [x] Tests : `tests/test_technical.py` — données synthétiques → score attendu
- [x] Tests : RSI<30+MACD cross = score > 65 ✓

### Pattern Detection Agent
- [x] `backend/app/agents/patterns.py` — chandeliers via pandas-ta CDL
- [x] `backend/app/agents/patterns.py` — double bottom/top custom
- [x] `backend/app/agents/patterns.py` — support/résistance dynamiques
- [x] `backend/app/scoring/patterns.py` — compute_pattern_score (0-100)
- [x] Tests : `tests/test_patterns.py` — données OHLC synthétiques avec patterns connus

### Risk/Confidence Agent
- [x] `backend/app/agents/risk.py` — implémentation 5 filtres (volume, volatilité, cooldown, score, trend)
- [x] `backend/app/agents/risk.py` — calcul confiance (0-1)
- [x] `backend/app/agents/risk.py` — cooldown tracking (Redis)
- [x] Tests : `tests/test_risk.py` — filtres (volume faible, cooldown, etc.)

### Intégration pipeline
- [x] `backend/app/services/scheduler.py` — pipeline complet : fetch → technical → patterns → risk → publish
- [x] Endpoint `GET /api/signals/{ticker}/latest` retourne signal complet
- [x] Endpoint `GET /api/watchlists/{id}/signals` retourne tous les signaux watchlist
- [x] `tests/pytest.ini` + `tests/conftest.py` — configuration pytest-asyncio
