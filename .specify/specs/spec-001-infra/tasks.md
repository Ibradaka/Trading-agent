# Tasks 001 — Infrastructure & Setup

## État : EN COURS

---

### Groupe A — Fichiers racine

- [x] `CLAUDE.md` mis à jour (périmètre beta)
- [x] `.specify/memory/constitution.md` créé
- [x] `.env.example` créé
- [x] `.gitignore` créé
- [x] `docker-compose.yml` créé (dev)
- [x] `docker-compose.prod.yml` créé (prod)
- [x] `nginx/nginx.conf` créé

### Groupe B — CI/CD

- [x] `.github/workflows/deploy.yml` créé (GitHub Actions → VPS SSH)

### Groupe C — Backend skeleton

- [x] `backend/requirements.txt` complet
- [x] `backend/Dockerfile` multi-stage (dev + prod)
- [x] `backend/app/__init__.py`
- [x] `backend/app/main.py` (FastAPI + lifespan + CORS + routers)
- [x] `backend/app/config.py` (Settings Pydantic)
- [x] `backend/app/database.py` (SQLAlchemy async engine + session)

### Groupe D — Modèles de données

- [x] `backend/app/models/db.py` (toutes les tables SQLAlchemy)

### Groupe E — Stubs agents / routers / services

- [x] `backend/app/agents/` (fichiers vides avec structure)
- [x] `backend/app/routers/watchlist.py` (CRUD complet)
- [x] `backend/app/routers/signals.py` (read-only)
- [x] `backend/app/routers/assets.py` (search + validate)
- [x] `backend/app/routers/sse.py` (SSE stream)
- [x] `backend/app/services/scheduler.py` (APScheduler setup)
- [x] `backend/app/services/redis_client.py` (client Redis)
- [x] `backend/app/services/telegram.py` (stub)
- [x] `backend/app/scoring/composite.py` (stub)

### Groupe F — Alembic

- [x] `backend/alembic.ini`
- [x] `backend/migrations/env.py` (async)
- [x] `backend/migrations/script.py.mako`
- [ ] Migration initiale générée et appliquée sur VPS

### Groupe G — Tests

- [x] `backend/tests/__init__.py`
- [x] `backend/tests/test_health.py`
- [x] `backend/tests/test_scoring.py` (structure)

### Groupe H — Frontend skeleton

- [x] `frontend/package.json`
- [x] `frontend/tsconfig.json`
- [x] `frontend/next.config.ts`
- [x] `frontend/tailwind.config.ts`
- [x] `frontend/postcss.config.mjs`
- [x] `frontend/Dockerfile`
- [x] `frontend/src/app/globals.css`
- [x] `frontend/src/app/layout.tsx`
- [x] `frontend/src/app/page.tsx` (stub watchlist)
- [x] `frontend/src/app/asset/[ticker]/page.tsx` (stub)
- [x] `frontend/src/app/history/page.tsx` (stub)
- [x] `frontend/src/app/settings/page.tsx` (stub)
- [x] `frontend/src/lib/api.ts`
- [x] `frontend/src/lib/sse.ts`

### Groupe I — Composants frontend

- [x] `frontend/src/components/layout/sidebar.tsx`
- [x] `frontend/src/components/layout/header.tsx`
- [x] `frontend/src/components/watchlist/watchlist-panel.tsx`
- [x] `frontend/src/components/signals/signal-card.tsx`
- [x] `frontend/src/components/charts/trading-view-chart.tsx`

### Déploiement VPS (à faire manuellement)

- [ ] SSH au VPS, clone du repo
- [ ] Copier `.env` sur le VPS
- [ ] `docker compose -f docker-compose.prod.yml up -d --build`
- [ ] `docker compose exec backend alembic upgrade head`
- [ ] Vérifier `GET /health` sur le domaine
