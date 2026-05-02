# Plan 001 — Infrastructure & Setup

## Architecture de déploiement

```
VPS Hostinger (Ubuntu 24.04)
└── Docker Compose
    ├── nginx          :80 :443  → reverse proxy
    ├── frontend       :3000     → Next.js
    ├── backend        :8899     → FastAPI
    ├── postgres       :5432     → PostgreSQL + TimescaleDB
    └── redis          :6379     → Redis

GitHub Actions
└── on push main → SSH VPS → docker compose pull && up -d --build
```

## Schéma de base de données (migration initiale)

### Tables principales
```sql
-- Watchlists (groupes d'actifs)
watchlists: id UUID, name, description, refresh_interval_minutes, signal_threshold, is_active, created_at

-- Actifs financiers
assets: id UUID, ticker, name, asset_type, exchange, currency, sector,
        is_pea_eligible, country, isin, metadata JSONB, created_at

-- Liaison many-to-many
watchlist_assets: watchlist_id, asset_id, is_active, notes,
                  target_buy_price, target_sell_price, added_at

-- Données OHLC (TimescaleDB hypertable)
ohlc_data: asset_id, timestamp, timeframe, open, high, low, close, volume, adj_close

-- Indicateurs techniques
technical_indicators: asset_id, timestamp, timeframe, rsi, macd, macd_signal,
                      macd_histogram, ema20, ema50, ema200, sma20, sma50, sma200,
                      bb_upper, bb_middle, bb_lower, atr, obv, stoch_k, stoch_d,
                      adx, williams_r

-- Patterns détectés
detected_patterns: asset_id, timestamp, pattern_name, direction, strength, description

-- Signaux générés
signals: id UUID, asset_id, timestamp, signal_type (BUY/SELL/HOLD),
         strength (strong/weak), composite_score, technical_score, pattern_score,
         sentiment_score, macro_score, momentum_score, confidence,
         reasoning TEXT, risks JSONB, invalidation_conditions TEXT,
         horizon TEXT, llm_raw_output JSONB, is_active, created_at

-- Cache sentiment
sentiment_cache: asset_id, timestamp, sentiment_score, key_themes JSONB,
                 sources JSONB, expires_at

-- Cache macro
macro_context: id UUID, timestamp, indicator_name, value, unit,
               description, source, expires_at

-- Historique performance signaux (pour accuracy tracking)
signal_outcomes: signal_id UUID, outcome_checked_at, price_at_signal,
                 price_at_check, actual_return_pct, was_correct,
                 days_elapsed, notes
```

## Choix techniques

### FastAPI lifespan
```python
@asynccontextmanager
async def lifespan(app):
    await init_db()          # pool SQLAlchemy
    await init_redis()       # connexion Redis
    start_scheduler()        # APScheduler
    yield
    stop_scheduler()
    await close_db()
```

### SQLAlchemy async
- Engine : `create_async_engine` avec pool_size=10
- Sessions : `async_sessionmaker` + dependency injection FastAPI
- Modèles : déclaratifs SQLAlchemy 2.0

### Alembic async
- env.py configuré pour async (run_async_migrations)
- autogenerate activé

### Next.js
- App Router (pas Pages Router)
- `next.config.ts` avec rewrites vers API backend
- Tailwind dark mode : `class` strategy
- shadcn/ui initialisé avec thème slate

## Décisions de déploiement

### CI/CD GitHub Actions
```yaml
trigger: push sur main
steps:
  1. SSH au VPS
  2. git pull origin main
  3. docker compose -f docker-compose.prod.yml pull
  4. docker compose -f docker-compose.prod.yml up -d --build
  5. docker compose exec backend alembic upgrade head
```

### Nginx
- HTTP → HTTPS redirect
- `/api/` → backend:8899
- `/` → frontend:3000
- gzip activé
- headers de sécurité
