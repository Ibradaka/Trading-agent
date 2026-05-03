# Trading Agent — Système d'aide à la décision swing trading

> Plateforme d'analyse financière multi-agents pour le swing trading PEA/CTO.
> Génère des signaux BUY/SELL déterministes, les explique en français, les valide historiquement et les pousse en temps réel sur Telegram.

---

## Pourquoi ce projet ?

Le swing trading manuel demande de surveiller en permanence des dizaines d'indicateurs techniques, de croiser avec le contexte macro et le sentiment de marché, puis de prendre une décision en quelques minutes. En pratique, c'est soit chronophage, soit émotionnel — rarement les deux à la fois de façon rigoureuse.

Ce projet automatise la **couche d'analyse** (pas l'exécution) :

- Les agents calculent en continu, 24h/24
- Le trader reçoit une alerte structurée avec raisonnement et niveau de confiance
- Il décide seul d'agir ou non

**Ce que le système fait :**
- Surveille une liste d'actifs (actions, ETF, indices, crypto, matières premières)
- Calcule des indicateurs techniques et détecte des patterns chartistes
- Agrège le sentiment de marché (RSS/actualités) et le contexte macro (FRED)
- Fusionne tout en un score composite 0–100 avec décision BUY/SELL/HOLD
- Explique la décision en français via LLM
- Alerte sur Telegram avec cooldown et heures silencieuses
- Mesure sa propre performance via backtesting walk-forward et outcome tracking réel

**Ce que le système ne fait PAS :**
- Passer des ordres automatiquement
- Gérer le portefeuille ou le sizing des positions
- Remplacer le jugement du trader

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    PIPELINE DE DONNÉES                        │
│  yfinance → OHLC DB → Indicateurs → Patterns → Score → Signal│
└──────────────────────────┬───────────────────────────────────┘
                           │ Redis pub/sub
          ┌────────────────┼────────────────┐
          ▼                ▼                ▼
   ┌─────────────┐  ┌──────────────┐  ┌──────────────┐
   │  Dashboard  │  │   Telegram   │  │   Outcome    │
   │  Next.js    │  │     Bot      │  │   Tracker    │
   └─────────────┘  └──────────────┘  └──────────────┘
```

### Stack technique

| Couche | Technologie |
|---|---|
| Backend API | FastAPI (Python 3.12) |
| Base de données | PostgreSQL 16 + TimescaleDB (séries temporelles) |
| Cache / Pub-Sub | Redis 7 |
| Scheduler | APScheduler (AsyncIO) |
| Données marché | yfinance + Yahoo Finance API (curl_cffi) |
| Données macro | FRED API (Federal Reserve Economic Data) |
| LLM | OpenAI GPT-4o-mini |
| Frontend | Next.js 14 + React + TypeScript |
| Style | Tailwind CSS |
| Charts | Lightweight Charts (TradingView) |
| Alertes | Telegram Bot API |
| Déploiement | Docker Compose (VPS Ubuntu 24.04) |
| Reverse proxy | Nginx + Let's Encrypt (HTTPS) |

---

## Les agents

### 1. Agent Market Data (`agents/market_data.py`)
Récupère les données OHLC (Open/High/Low/Close/Volume) depuis Yahoo Finance via session curl_cffi (contourne le blocage des IPs datacenter par fingerprinting TLS). Stocke en base PostgreSQL/TimescaleDB. Déclenché toutes les 15 minutes pendant les heures de marché.

### 2. Agent Technical (`agents/technical.py`)
Calcule les indicateurs techniques sur chaque actif :
- **Tendance** : EMA 20/50/200, SMA 20/50
- **Momentum** : RSI 14, MACD (12/26/9), Stochastique (14/3)
- **Volatilité** : Bandes de Bollinger (20/2), ATR 14
- **Volume** : OBV (On-Balance Volume)
- **Force** : ADX 14

### 3. Agent Patterns (`agents/patterns.py`)
Détecte les patterns chartistes sur les bougies japonaises et les figures chartistes :
- **Bougies** : Engulfing haussier/baissier, Hammer, Shooting Star, Doji, Morning Star, Evening Star, Three White Soldiers, Three Black Crows
- **Figures** : Double Top/Bottom, supports et résistances dynamiques

### 4. Agent Sentiment (`agents/sentiment.py`)
Analyse le sentiment de marché via flux RSS d'actualités financières. Utilise GPT-4o-mini pour scorer le sentiment (0–100) et extraire les thèmes clés. Cache Redis 15 minutes.

### 5. Agent Macro (`agents/macro.py`)
Interroge l'API FRED (Federal Reserve) pour le contexte macroéconomique :
- `FEDFUNDS` — Taux directeur Fed
- `T10Y2Y` — Spread 10 ans / 2 ans (indicateur de récession)
- `T10YIE` — Inflation anticipée 10 ans

Détermine un régime macro (bullish/bearish/neutral) qui pondère le score final. Cache 6 heures.

### 6. Agent Risk/Score (`agents/risk.py`)
Cœur du système — applique le **Signal Fusion Engine** :

```
Score composite = 0.35×technique + 0.20×patterns + 0.20×momentum + 0.15×macro + 0.10×sentiment

Score fusion = 0.50×tech_composite + 0.25×sentiment + 0.25×macro

BUY  si score > 65
SELL si score < 45
HOLD sinon
```

Applique ensuite un **Confidence Engine** :
- `high` (≥ 70%) : signal technique fort + sentiment frais + macro favorable
- `medium` (45–69%) : signal correct mais conditions partiellement remplies
- `low` (< 45%) : signal faible, non transmis à Telegram

Vérifie le cooldown (4 jours entre signaux sur le même actif) avant de persister en base et publier sur Redis.

### 7. Agent LLM (`services/llm.py`)
Génère en français le raisonnement du signal, les risques associés, les conditions d'invalidation et l'horizon temporel recommandé. Utilise GPT-4o-mini avec un prompt structuré incluant les indicateurs, le contexte macro et le sentiment.

---

## Signal Fusion Engine

Le scoring est **entièrement déterministe et backtestable**. Aucune logique parallèle entre le scoring live et le backtesting — les mêmes fonctions sont réutilisées.

### Score technique (0–100)
Agrège RSI, MACD, position par rapport aux EMA, Bollinger, ADX et Stochastique. Chaque indicateur vote +/- selon des seuils calibrés (ex: RSI < 30 → vote haussier fort, RSI > 70 → vote baissier fort).

### Score momentum (0–100)
Combine la pente des EMA, la position close/EMA20, le momentum à 5/10/20 jours et la tendance de volume.

### Score patterns (0–100)
Pondère les patterns détectés selon leur force (0–1) et leur direction (haussier/baissier).

### Score macro (0–100)
Traduit le régime FRED en score : taux en baisse + courbe normalisée + inflation maîtrisée → bullish.

### Score sentiment (0–100)
Score RSS normalisé sur les dernières actualités de l'actif.

---

## Backtesting walk-forward

Le backtesting rejoue le scoring engine sur 5 ans d'historique yfinance **sans fuite de données futures** :

- Fenêtre glissante stricte : pour chaque bougie `i`, seules les données `[0..i]` sont visibles
- Cooldown de 4 jours entre signaux simulés (cohérent avec le live)
- Minimum 52 bougies d'historique avant le premier signal
- Sentiment et macro neutralisés à 50 (pas de replay historique possible)
- Résultat à J+5, J+10, J+20

**Métriques calculées :**
- Win rate
- Retour moyen à J+N
- Sharpe ratio annualisé
- Max drawdown
- Retour cumulé
- Calibration par niveau de confiance (high vs medium)

**Benchmarks comparés :**
- Buy & Hold total sur la période
- Momentum simple (close > SMA20)
- Croisement MA20/MA50

---

## Outcome Tracker

Mesure la performance **réelle** des signaux générés en live :
- Enregistre le prix à la date du signal
- Vérifie à J+5, J+10 et J+20 le prix de clôture
- Calcule le retour réalisé et si le signal était correct
- Alimente la page Historique du dashboard

---

## Telegram Bot

Commandes disponibles :
- `/signal TICKER` — Dernier signal pour un actif
- `/watchlist` — Tous les signaux actifs
- `/status` — État du système (uptime, macro, nb signaux)
- `/pause TICKER` — Suspend les alertes pour cet actif (24h)
- `/resume TICKER` — Réactive les alertes

**Règles d'envoi :**
- Seuil minimum configurable (défaut : score ≥ 70%)
- Confiance minimum : medium ou high
- Cooldown 2h par actif (Redis TTL)
- Heures silencieuses 22h–07h CET (signaux mis en file, envoyés à 07h)
- Digest quotidien à 08h00 CET
- Mode panique global : coupe toutes les alertes sans arrêter le système

---

## Dashboard

Application web Next.js accessible sur HTTPS.

### Pages

| Page | Description |
|---|---|
| **Watchlists** | Vue principale — actifs surveillés avec prix live, sparklines, P&L position, signal actif |
| **Portefeuille** | Positions ouvertes (PEA/CTO/PEE/AUTRE), P&L en temps réel |
| **Historique** | Signaux générés avec leurs outcomes réels à J+5/J+10/J+20 |
| **Backtesting** | Simulation walk-forward sur 1–5 ans avec métriques et benchmarks |
| **Configuration** | Paramètres opérationnels : seuils, alertes, heures silencieuses, panic mode |

### Fonctionnalités

- **Graphiques interactifs** : Bougies japonaises via Lightweight Charts, timeframes 5J/1M/3M/6M/1A
- **Radar de score** : Visualisation des 5 composantes du signal
- **Flux temps réel** : Server-Sent Events (SSE) pour les mises à jour de signaux
- **Bannière système** : Indicateurs d'état opérationnel (marché ouvert, sentiment disponible, macro à jour, panic mode)
- **Ajout d'actifs** : Modal de recherche avec validation live du ticker Yahoo Finance

---

## Configuration et déploiement

### Prérequis
- Docker & Docker Compose
- VPS Linux (Ubuntu 24.04 recommandé)
- Clés API : OpenAI, FRED, Telegram Bot Token

### Variables d'environnement (`.env`)

```env
# Base de données
DATABASE_URL=postgresql+asyncpg://user:password@postgres:5432/trading
POSTGRES_PASSWORD=your_password

# Redis
REDIS_URL=redis://redis:6379/0

# LLM
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini

# Données macro
FRED_API_KEY=your_fred_key

# Telegram
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
DASHBOARD_URL=https://your-domain.com

# App
APP_ENV=production
SIGNAL_ALERT_THRESHOLD=0.70
```

### Démarrage

```bash
git clone https://github.com/Ibradaka/Trading-agent.git
cd Trading-agent
cp .env.example .env
# Remplir les variables dans .env
docker compose up -d
```

### Scheduler (jobs automatiques)

| Job | Fréquence | Condition |
|---|---|---|
| Pipeline marché (fetch + indicateurs + patterns + score) | Toutes les 15 min | Marché ouvert (9h–17h30 CET, lun–ven) |
| Mise à jour sentiment | Toutes les 15 min | Marché ouvert |
| Mise à jour macro FRED | Toutes les 6h | Toujours |
| Outcome tracking | Quotidien 20h00 CET | Toujours |
| Digest Telegram | Quotidien 08h00 CET | Si Telegram configuré |
| Flush signaux en attente | Quotidien 07h00 CET | Si signaux en file |

---

## Structure du projet

```
Trading-agent/
├── backend/
│   └── app/
│       ├── agents/          # Pipeline de traitement des données
│       │   ├── market_data.py
│       │   ├── technical.py
│       │   ├── patterns.py
│       │   ├── sentiment.py
│       │   ├── macro.py
│       │   ├── risk.py
│       │   └── confidence.py
│       ├── backtesting/
│       │   └── engine.py    # Backtesting walk-forward
│       ├── models/
│       │   └── db.py        # Modèles SQLAlchemy (TimescaleDB)
│       ├── routers/         # Endpoints FastAPI
│       │   ├── assets.py
│       │   ├── signals.py
│       │   ├── watchlist.py
│       │   ├── portfolio.py
│       │   ├── backtest.py
│       │   ├── system.py
│       │   └── sse.py
│       ├── scoring/
│       │   ├── technical.py
│       │   ├── patterns.py
│       │   └── composite.py
│       └── services/
│           ├── telegram.py
│           ├── scheduler.py
│           ├── outcome_tracker.py
│           ├── redis_client.py
│           ├── llm.py
│           └── yfinance_session.py
└── frontend/
    └── src/
        ├── app/             # Pages Next.js (App Router)
        │   ├── page.tsx
        │   ├── portfolio/
        │   ├── history/
        │   ├── backtest/
        │   └── settings/
        └── components/
            ├── charts/
            ├── layout/
            ├── portfolio/
            ├── signals/
            └── watchlist/
```

---

## Actifs supportés

Tous les actifs disponibles sur Yahoo Finance :
- **Actions françaises** : suffixe `.PA` (ex: `MC.PA`, `TTE.PA`, `AI.PA`)
- **Actions américaines** : ticker direct (ex: `NVDA`, `AAPL`, `MSFT`)
- **ETF européens** : suffixe `.L` Londres, `.DE` Xetra, `.MI` Milan
- **Éligibilité PEA** : détectée automatiquement selon l'exchange

---

## Performance observée (backtesting NVDA 5 ans)

| Métrique | Valeur |
|---|---|
| Signaux générés | 58 |
| Win rate | 73.7% |
| Retour moyen à J+20 | +5.8% |
| Sharpe ratio | 1.51 |
| Retour cumulé système | +1 464% |
| Buy & Hold sur période | +995% |

*Note : résultats historiques, non garantis pour le futur. Le backtesting ne modélise pas les frais de transaction ni la gestion de position.*

---

## Licence

Projet privé — tous droits réservés.
