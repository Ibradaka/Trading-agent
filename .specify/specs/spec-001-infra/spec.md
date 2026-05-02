# Spec 001 — Infrastructure & Setup

## Objectif
Mettre en place l'intégralité de l'infrastructure avant d'écrire le moindre agent.
Un environnement opérationnel de bout en bout : base de données, cache, API skeleton, frontend skeleton, CI/CD.

## User stories

**En tant qu'utilisateur**, je veux pouvoir lancer `docker compose up` et avoir un système fonctionnel avec :
- API FastAPI répondant sur le port 8899
- Frontend Next.js répondant sur le port 5899
- PostgreSQL + TimescaleDB opérationnel avec le schéma initialisé
- Redis opérationnel
- Healthcheck endpoint `/health` retournant `{"status": "ok"}`

**En tant que développeur**, je veux que chaque push sur `main` déclenche automatiquement un déploiement sur le VPS.

## Critères d'acceptation

- [ ] `docker compose up -d` démarre tous les services sans erreur
- [ ] `GET /health` retourne 200 avec `{"status": "ok", "version": "1.0.0-beta"}`
- [ ] `GET /api/watchlists` retourne 200 (liste vide)
- [ ] Migrations Alembic s'exécutent sans erreur (`alembic upgrade head`)
- [ ] TimescaleDB hypertable créée sur `ohlc_data`
- [ ] Frontend charge sans erreur console
- [ ] GitHub Actions déploie automatiquement sur le VPS à chaque push sur `main`
- [ ] `.env` non commité dans git
- [ ] Nginx reverse proxy fonctionnel en prod (HTTP redirect → HTTPS)

## Périmètre

### Inclus
- Docker Compose dev + prod
- PostgreSQL 16 + TimescaleDB
- Redis 7
- FastAPI avec CORS, lifespan, structlog
- Alembic setup + migration initiale (toutes les tables)
- Next.js 14 avec Tailwind + shadcn/ui installés
- GitHub Actions workflow deploy
- Nginx configuration prod
- `.env.example` complet
- `.gitignore` complet

### Exclus
- Logique métier des agents (spec-002)
- Scoring (spec-003)
- Dashboard complet (spec-004)
- Telegram (spec-005)
