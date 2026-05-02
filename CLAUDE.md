# Trading Agent — Système d'aide à la décision Swing Trading (BETA)

## Spec de référence
La spec complète est dans `architecture-trading-agent.md`.
La structure spec-kit est dans `.specify/` — chaque feature a son propre `spec.md`, `plan.md`, `tasks.md`.
**Toujours** s'y référer avant d'implémenter quoi que ce soit.

## Ce que ce projet fait
Outil personnel d'aide à la décision pour swing trading (actions PEA, compte-titres, indices).
Signaux BUY/SELL/HOLD avec score de probabilité, raisonnement IA, dashboard temps réel.
**Pas d'exécution automatique de trades. Jamais.**

## Périmètre BETA (pas un MVP — ne pas économiser)
- ✅ Tous les agents déterministes (Market Data, Technical, Patterns, Risk, Watchlist)
- ✅ Agents IA inclus dès la beta (Sentiment RSS, Macro FRED, Signal Synthesizer GPT-4o-mini)
- ✅ Dashboard complet avec TradingView charts
- ✅ Historique signaux + accuracy tracking
- ✅ Backtesting walk-forward sur historique yfinance
- ✅ Telegram bot avec formatting riche
- ✅ Multi-watchlist (PEA + CTO + Indices)
- ✅ PEA eligibility detection automatique
- ✅ Marché européen (Euronext Paris/Amsterdam/Bruxelles, Xetra) en priorité

## Stack technique
- **Backend** : Python 3.11+ / FastAPI / async partout
- **DB** : PostgreSQL 16 + TimescaleDB (time series) + Redis (cache + pub/sub)
- **Frontend** : Next.js 14 App Router / TypeScript / Tailwind CSS / shadcn/ui
- **Charts** : TradingView Lightweight Charts (gratuit)
- **LLM** : OpenAI GPT-4o-mini (Signal Synthesizer + Macro)
- **Orchestration** : APScheduler (jobs Python intégrés)
- **Déploiement** : Docker Compose sur VPS Hostinger (Ubuntu 24.04)
- **Notifs** : Telegram Bot

## Ports
- Backend : **8899**
- Frontend : **5899** (dev) / **3000** (container)

## Règles de développement

### Architecture agents
- **Agents déterministes** = pur Python, PAS de LLM (Market Data, Technical, Patterns, Risk, Watchlist)
- **Agents IA** = GPT-4o-mini avec JSON mode strict, validation Pydantic sur TOUS les outputs
- Fallback déterministe obligatoire si LLM down ou JSON invalide
- Cache Redis agressif sur les outputs LLM (TTL : 15min sentiment, 6h macro)
- Ne JAMAIS utiliser un LLM pour un calcul déterministe (RSI, MACD, etc.)

### Conventions code Python
- Type hints partout
- Pydantic v2 pour les modèles de données et validation
- async/await pour tout I/O (DB, API, Redis)
- Logging structuré avec structlog (jamais de print)
- Tests pytest obligatoires pour la logique de scoring
- Docstrings sur chaque fonction publique
- Fichier `.env` pour toutes les config (jamais hardcodé)

### Conventions frontend
- Composants fonctionnels React uniquement
- shadcn/ui pour les composants UI (pas Material UI, pas Ant Design)
- TanStack Query pour le state serveur
- SSE (Server-Sent Events) pour le temps réel, pas de WebSocket
- Dark mode par défaut
- Pas de `any` TypeScript — types stricts partout

### Cadences de refresh (APScheduler)
- **15 min** : Market Data + Technical + Patterns + Risk (pendant heures marché : 09h00-17h30 CET)
- **15 min** : Sentiment RSS
- **6h** : Macro FRED
- **Journalier** : Backtesting + rapport synthèse
- Heures marché : `exchange_calendars` (Euronext/Xetra), pas de refresh hors heures

### Anti-biais obligatoires
- Walk-forward testing (jamais d'optimisation sur les données de test)
- Cooldown 48h entre signaux opposés sur le même actif
- Filtre liquidité : pas de signal si volume < moyenne 20j / 2
- Multi-timeframe confirmation : signal daily cohérent avec 4H
- Fallback déterministe si LLM invalide

### Sécurité
- Jamais de clé API dans le code ou les commits
- `.env` dans `.gitignore`
- Validation Pydantic sur tous les inputs API
- Pas de données sensibles dans les logs

## Structure du projet
```
Trading agent/
├── .specify/                        # spec-kit — source de vérité
│   ├── memory/constitution.md
│   └── specs/spec-00X-*/           # spec.md + plan.md + tasks.md
├── CLAUDE.md                        # ce fichier
├── architecture-trading-agent.md    # spec technique complète
├── docker-compose.yml               # dev
├── docker-compose.prod.yml          # prod
├── nginx/nginx.conf
├── .github/workflows/deploy.yml     # CI/CD → VPS
├── .env.example
├── .gitignore
├── backend/
│   ├── app/
│   │   ├── main.py                  # FastAPI app + lifespan
│   │   ├── config.py                # Settings Pydantic
│   │   ├── database.py              # SQLAlchemy async engine
│   │   ├── agents/                  # Un fichier par agent
│   │   │   ├── market_data.py
│   │   │   ├── technical.py
│   │   │   ├── patterns.py
│   │   │   ├── risk.py
│   │   │   ├── watchlist_manager.py
│   │   │   ├── sentiment.py         # RSS-based
│   │   │   ├── macro.py             # FRED + LLM
│   │   │   └── signal_synthesizer.py # GPT-4o-mini
│   │   ├── routers/
│   │   │   ├── watchlist.py
│   │   │   ├── signals.py
│   │   │   ├── assets.py
│   │   │   └── sse.py               # Server-Sent Events
│   │   ├── services/
│   │   │   ├── scheduler.py         # APScheduler
│   │   │   ├── redis_client.py      # Cache + Pub/Sub
│   │   │   └── telegram.py          # Notifs
│   │   ├── models/
│   │   │   └── db.py                # SQLAlchemy models
│   │   ├── scoring/
│   │   │   ├── composite.py         # Score composite
│   │   │   ├── technical.py         # Score technique
│   │   │   └── patterns.py          # Score patterns
│   │   └── backtesting/
│   │       └── engine.py            # Walk-forward backtesting
│   ├── migrations/                  # Alembic
│   │   ├── env.py
│   │   └── versions/
│   ├── tests/
│   ├── requirements.txt
│   ├── alembic.ini
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── app/                     # Next.js App Router
│   │   │   ├── layout.tsx
│   │   │   ├── page.tsx             # Watchlist overview
│   │   │   ├── asset/[ticker]/page.tsx
│   │   │   ├── history/page.tsx
│   │   │   └── settings/page.tsx
│   │   ├── components/
│   │   │   ├── layout/              # Sidebar, Header
│   │   │   ├── watchlist/           # Watchlist panel, asset row
│   │   │   ├── signals/             # Signal card, score radar
│   │   │   └── charts/              # TradingView wrapper
│   │   ├── hooks/                   # Custom React hooks
│   │   └── lib/
│   │       ├── api.ts               # API client
│   │       └── sse.ts               # SSE hook
│   ├── package.json
│   ├── tsconfig.json
│   ├── tailwind.config.ts
│   └── Dockerfile
```

## Base de données
- SQLAlchemy 2.0 (async) + Alembic pour les migrations
- TimescaleDB hypertable sur la table `ohlc_data` (partitionnement par temps)
- Jamais de DELETE physique sur les données OHLC historiques
- UUID pour les clés primaires des tables métier

## Variables d'environnement (.env)
```
# Base de données
DATABASE_URL=postgresql+asyncpg://trading:password@postgres:5432/trading_agent
REDIS_URL=redis://redis:6379/0

# Sources de données
FRED_API_KEY=
ALPHA_VANTAGE_KEY=

# LLM
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini

# Notifications
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

# App
APP_ENV=development
LOG_LEVEL=INFO
DEFAULT_REFRESH_MINUTES=15
MARKET_OPEN_CET=09:00
MARKET_CLOSE_CET=17:30
MAX_ACTIVE_ASSETS=30

# Postgres
POSTGRES_PASSWORD=
REDIS_PASSWORD=
```

## Comment lancer le projet
```bash
# Dev (DB seulement en Docker, services en local)
docker compose up -d postgres redis
cd backend && uvicorn app.main:app --reload --port 8899
cd frontend && npm run dev -- -p 5899

# Tout en Docker (dev)
docker compose up -d

# Prod
docker compose -f docker-compose.prod.yml up -d --build
```

## Comment tester
```bash
cd backend
pytest tests/ -v
pytest tests/ -v -k "scoring"   # tests scoring uniquement
pytest tests/ -v -k "agents"    # tests agents uniquement
```

## Migrations Alembic
```bash
cd backend
alembic revision --autogenerate -m "description"
alembic upgrade head
```

## Approche d'implémentation
1. Toujours confirmer ce qui va être fait AVANT de coder
2. Implémenter une spec à la fois (voir .specify/specs/)
3. Créer les tests en même temps que le code
4. Ne pas passer à la spec suivante sans validation explicite
5. Si un choix technique diverge de la spec, le signaler et demander
6. Marquer les tasks comme completed dans tasks.md au fil de l'avancement
