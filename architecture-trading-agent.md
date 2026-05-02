# Architecture — Système d'aide à la décision Swing Trading

> **Insight directeur :** sur les 7 agents que tu listes, seuls 3 ont besoin d'un LLM. Les 4 autres sont du code Python pur — plus rapide, gratuit, déterministe. Ce découpage divise le coût par 10 et rend le système 5x plus stable.

---

## 1. Vue d'ensemble

**Pipeline :** Collecte → Calcul déterministe → Enrichissement IA → Scoring → Dashboard

**Cadences de refresh** (clé pour la perf VPS) :
- **1 min** : prix temps réel + indicateurs courts
- **5-15 min** : news, sentiment
- **1-6h** : macro
- **Quotidien** : recalibration scores, rapport synthèse

---

## 2. Architecture logique

```
┌─────────────────────────────────────────────────────────────────┐
│                        ORCHESTRATEUR                             │
│              (n8n existant + APScheduler Python)                 │
└──────────────┬───────────────────────────┬──────────────────────┘
               │                           │
   ┌───────────▼──────────┐    ┌───────────▼──────────────┐
   │  AGENTS DÉTERMINISTES│    │   AGENTS IA (LLM)        │
   │  (pur Python)        │    │   (GPT-4o-mini)          │
   ├──────────────────────┤    ├──────────────────────────┤
   │ • Market Data        │    │ • Sentiment Analyzer     │
   │ • Technical Analysis │    │ • Macro Contextualizer   │
   │ • Pattern Detection  │    │ • Signal Synthesizer     │
   │ • Risk/Confidence    │    │   (raisonnement final)   │
   └──────────┬───────────┘    └──────────┬───────────────┘
              │                           │
              └───────────┬───────────────┘
                          │
              ┌───────────▼────────────┐
              │   STORAGE LAYER        │
              │ • PostgreSQL+TimescaleDB│
              │ • Redis (cache + pub/sub)│
              └───────────┬────────────┘
                          │
              ┌───────────▼────────────┐
              │      API FastAPI       │
              │   (REST + SSE stream)  │
              └───────────┬────────────┘
                          │
              ┌───────────▼────────────┐
              │   Dashboard Next.js    │
              │ (Tailwind+shadcn+TV)   │
              └────────────────────────┘
```

---

## 3. Découpage détaillé des agents

### 🔧 Agents déterministes (pur code, sans LLM)

#### **Agent Market Data**
- **Rôle :** collecte prix OHLC + données volume
- **Input :** liste actifs surveillés, intervalle (1m/5m/1h/1d)
- **Output :** DataFrame normalisé → écrit dans TimescaleDB
- **Tech :** `yfinance` (gratuit, illimité), `ccxt` pour crypto, fallback Alpha Vantage
- **Fréquence :** 1 min sur watchlist active

#### **Agent Technical Analysis**
- **Rôle :** calcul de tous les indicateurs
- **Input :** OHLC depuis TimescaleDB
- **Output :** dict d'indicateurs + signaux atomiques (`{rsi: 28, rsi_signal: "oversold"}`)
- **Tech :** `pandas-ta` (gratuit, 130+ indicateurs), `TA-Lib` si besoin de perf
- **Indicateurs :** MACD, RSI, SMA(20/50/200), EMA(9/21), Bollinger (20,2), ATR, OBV

#### **Agent Pattern Detection**
- **Rôle :** détection patterns chandeliers + figures chartistes
- **Input :** OHLC dernière fenêtre
- **Output :** patterns détectés avec score de force (`{pattern: "engulfing_bullish", strength: 0.82}`)
- **Tech :** `pandas-ta` (60+ patterns candlesticks intégrés) + custom pour figures (double-top, H&S)

#### **Agent Risk/Confidence**
- **Rôle :** filtre les signaux selon volatilité, liquidité, contexte
- **Input :** signal brut + ATR + volume + contexte macro
- **Output :** signal pondéré + niveau de confiance (0-1)
- **Logique :** règles déterministes (ex: pas de BUY si VIX > 30 ET signal < 0.7)

#### **Agent Watchlist Manager**
- **Rôle :** gère le CRUD des actifs surveillés + valide les ajouts
- **Input :** requête utilisateur (ajout/suppression/toggle) avec symbole
- **Output :** actif validé + enrichi (nom, asset_class, source de données)
- **Logique :**
  1. Validation symbole (test fetch yfinance/ccxt)
  2. Auto-détection de la classe d'actif (equity/commodity/crypto/index/forex)
  3. Récupération du nom complet via metadata API
  4. Persistance dans table `watchlist` PostgreSQL
  5. Notification au scheduler pour intégration immédiate

### 🤖 Agents IA (LLM, GPT-4o-mini)

#### **Agent Sentiment Analyzer**
- **Rôle :** analyse news + Google Trends + reddit (si possible)
- **Input :** flux RSS + queries pytrends + headlines actif
- **Output :** `{sentiment: -0.6, key_themes: [...], catalysts: [...]}`
- **Tech :** `feedparser` (RSS Reuters, FT, Investing.com, ZeroHedge), `pytrends`, LLM résume + score
- **Optimisation coût :** cache 15min sur même actif, batch les analyses

#### **Agent Macro Contextualizer**
- **Rôle :** synthèse environnement macro pour un actif
- **Input :** données FRED (taux Fed, CPI, NFP), calendrier éco
- **Output :** narrative macro + bias directionnel (`{macro_bias: "bearish_risk_assets", strength: 0.7}`)
- **Tech :** `fredapi` + RSS TradingEconomics + LLM
- **Fréquence :** 6h ou sur événement macro majeur

#### **Agent Signal Synthesizer** ⭐
- **Rôle :** **le cerveau** — agrège tous les signaux et produit la décision finale
- **Input :** outputs de tous les autres agents
- **Output :** 
  ```json
  {
    "asset": "GC=F",
    "signal": "BUY",
    "score": 78,
    "confidence": 0.82,
    "horizon": "5-10 jours",
    "reasoning": "Convergence : RSI sortant de survente + MACD croisement haussier + sentiment neutre→positif + macro favorable (USD faiblissant)",
    "risks": ["Résistance à 2050", "Décision Fed mercredi"],
    "invalidation": "Cloture sous 1980"
  }
  ```
- **Tech :** GPT-4o-mini avec prompt structuré + outputs JSON forcés
- **Fréquence :** uniquement si agrégat de signaux change significativement (économie de tokens)

---

## 4. Stack technique

| Couche | Choix | Raison |
|--------|-------|--------|
| **Backend** | Python 3.11 + FastAPI | Async natif, écosystème data |
| **Calcul** | pandas, numpy, pandas-ta | Standards industriels gratuits |
| **DB time-series** | PostgreSQL 16 + TimescaleDB | Gratuit, optimisé OHLC, requêtes ultra-rapides |
| **Cache + bus** | Redis | Pub/Sub entre agents + cache LLM |
| **Orchestration** | n8n (déjà installé) + APScheduler | n8n pour workflows visuels, APScheduler pour jobs Python lourds |
| **LLM** | OpenAI GPT-4o-mini via API | Excellent rapport prix/qualité, ton crédit suffit |
| **Frontend** | Next.js 14 + Tailwind + shadcn/ui | Tu maîtrises déjà |
| **Charts** | TradingView Lightweight Charts | Gratuit, ultra performant, look pro |
| **Push temps réel** | Server-Sent Events (SSE) | Plus simple que WebSocket, suffisant pour 1 utilisateur |
| **Déploiement** | Docker Compose sur Hostinger VPS | Tu connais déjà |
| **Notifs** | Telegram Bot | Gratuit, fiable, mobile |

---

## 5. Sources de données gratuites

| Type | Source | Lib Python | Limite |
|------|--------|-----------|--------|
| Prix OHLC actions/indices | Yahoo Finance | `yfinance` | Pas de limite officielle |
| Crypto | Binance public | `ccxt` | Limites IP raisonnables |
| Backup prix | Alpha Vantage | `alpha_vantage` | 25 calls/jour gratuit |
| Macro US | FRED | `fredapi` | Illimité avec clé gratuite |
| Macro Europe | ECB SDW, Eurostat | `requests` | Gratuit |
| News financières | RSS Reuters, FT, Investing | `feedparser` | Gratuit |
| Calendrier éco | TradingEconomics RSS | `feedparser` | Gratuit |
| Google Trends | Google | `pytrends` | Limites IP, à throttler |
| Volatilité (VIX) | Yahoo via ^VIX | `yfinance` | Inclus |

**À éviter** (pièges classiques) :
- Twitter/X scraping → bloqué, payant maintenant
- Reddit API → quotas serrés depuis 2023, peu rentable
- Stocktwits → API limitée

---

## 6. Workflow temps réel

### Boucle minute (la plus critique)
```
T+0s    : APScheduler trigger
T+0-2s  : Agent Market Data fetch yfinance (parallèle sur watchlist)
T+2-3s  : Agent Technical Analysis recalcule indicateurs
T+3-4s  : Agent Pattern Detection scan patterns
T+4-5s  : Agent Risk/Confidence pondère
T+5s    : Publie sur Redis pub/sub
T+5s    : Si changement signal majeur → trigger Signal Synthesizer (LLM)
T+5-10s : Push SSE vers dashboard + notif Telegram si signal fort
```

### Boucle 15 minutes
- Refresh news (RSS multi-sources)
- Agent Sentiment Analyzer LLM-based
- Update score sentiment dans Redis

### Boucle 6 heures
- Refresh macro FRED
- Agent Macro Contextualizer LLM-based
- Update bias macro

### Astuces perf VPS
- **Cache LLM agressif** : key = hash(input), TTL = 15min sur sentiment, 6h sur macro
- **Batch processing** : grouper plusieurs actifs dans un même prompt LLM
- **Async everywhere** : FastAPI async, aiohttp pour les fetchs
- **TimescaleDB compression** : compresse automatiquement les données > 7j

---

## 7. Logique de scoring

### Score composite (0-100)

```python
score = (
    technical_score * 0.40 +      # convergence indicateurs
    pattern_score * 0.20 +        # force patterns détectés
    sentiment_score * 0.15 +      # news + Google Trends
    macro_score * 0.15 +          # alignement macro
    momentum_score * 0.10         # tendance multi-timeframe
)
```

### Scoring technique (exemple détaillé)
```python
def compute_technical_score(indicators):
    points = 0
    
    # MACD
    if indicators['macd_cross_up']: points += 20
    elif indicators['macd_cross_down']: points -= 20
    
    # RSI zones
    if 30 < indicators['rsi'] < 50 and indicators['rsi_rising']: points += 15
    elif indicators['rsi'] < 30: points += 25  # survente
    elif indicators['rsi'] > 70: points -= 25  # surachat
    
    # EMA alignment
    if indicators['ema9'] > indicators['ema21'] > indicators['sma50']:
        points += 20  # tendance haussière propre
    
    # Bollinger
    if indicators['close'] < indicators['bb_lower']: points += 15
    elif indicators['close'] > indicators['bb_upper']: points -= 15
    
    return max(0, min(100, points + 50))  # normalise [0, 100]
```

### Seuils de décision
- **Score > 75 + confidence > 0.7** → BUY/SELL fort (notif Telegram)
- **Score 60-75** → BUY/SELL faible (dashboard uniquement)
- **Score 40-60** → HOLD
- **Score < 40** → contre-signal

---

## 8. Gestion du portefeuille de suivi (Watchlist Manager)

### Concept : multi-watchlists

Plutôt qu'une seule liste plate, organiser en **watchlists thématiques** alignées sur tes vehicles fiscaux :

| Watchlist | Type d'actifs | Vehicle |
|-----------|---------------|---------|
| `pea-actions` | Actions européennes éligibles PEA | PEA |
| `ct-international` | Actions US, ETF non-éligibles | Compte-titres |
| `commodities` | Or, pétrole, cuivre | Compte-titres |
| `indices` | S&P500, CAC40, Nasdaq | Suivi macro |
| `crypto` | BTC, ETH | Hors fiscal |
| `pee-watch` | Fonds disponibles PEE | PEEE (info only) |

**Avantage :** chaque watchlist peut avoir ses propres seuils de signal, sa cadence de refresh, ses sources de données privilégiées.

### Modèle de données

```sql
-- Table watchlists
CREATE TABLE watchlists (
    id UUID PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    refresh_interval INT DEFAULT 60,  -- secondes
    signal_threshold INT DEFAULT 70,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Table assets (ticker + métadonnées)
CREATE TABLE assets (
    id UUID PRIMARY KEY,
    ticker VARCHAR(20) UNIQUE NOT NULL,  -- ex: "AAPL", "GC=F", "BTC-USD"
    name VARCHAR(200),                    -- "Apple Inc."
    asset_type VARCHAR(50),               -- "equity", "commodity", "index", "crypto", "forex"
    exchange VARCHAR(50),                 -- "NASDAQ", "EURONEXT_PARIS"
    currency VARCHAR(10),                 -- "USD", "EUR"
    sector VARCHAR(100),                  -- "Technology" (pour actions)
    is_pea_eligible BOOLEAN DEFAULT FALSE,
    metadata JSONB,                       -- infos enrichies
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Table de jointure
CREATE TABLE watchlist_assets (
    watchlist_id UUID REFERENCES watchlists(id) ON DELETE CASCADE,
    asset_id UUID REFERENCES assets(id) ON DELETE CASCADE,
    added_at TIMESTAMPTZ DEFAULT NOW(),
    notes TEXT,                           -- annotations perso ("acheté à 150€")
    target_buy_price DECIMAL,             -- objectif d'achat
    target_sell_price DECIMAL,            -- objectif de vente
    PRIMARY KEY (watchlist_id, asset_id)
);
```

### API REST (FastAPI)

```
GET    /watchlists                          # liste toutes les watchlists
POST   /watchlists                          # crée une watchlist
GET    /watchlists/{id}                     # détail watchlist + ses actifs
PATCH  /watchlists/{id}                     # modifie nom/seuils
DELETE /watchlists/{id}                     # supprime watchlist

GET    /watchlists/{id}/assets              # actifs de la watchlist + signaux courants
POST   /watchlists/{id}/assets              # ajoute un actif (ticker)
DELETE /watchlists/{id}/assets/{ticker}     # retire un actif
PATCH  /watchlists/{id}/assets/{ticker}     # update notes/cibles

GET    /assets/search?q=apple               # autocomplete recherche
GET    /assets/validate?ticker=AAPL         # valide qu'un ticker existe sur yfinance
```

### Validation à l'ajout (UX critique)

Quand l'utilisateur tape un ticker, le backend valide en temps réel :

```python
async def validate_ticker(ticker: str) -> dict:
    """Valide ticker via yfinance + enrichit avec métadonnées."""
    try:
        info = yf.Ticker(ticker).info
        if not info.get('regularMarketPrice'):
            return {"valid": False, "error": "Ticker introuvable ou inactif"}
        
        return {
            "valid": True,
            "ticker": ticker,
            "name": info.get('longName', ticker),
            "asset_type": _detect_type(info),  # equity/commodity/etc
            "exchange": info.get('exchange'),
            "currency": info.get('currency'),
            "sector": info.get('sector'),
            "is_pea_eligible": _check_pea_eligibility(info),
            "current_price": info.get('regularMarketPrice')
        }
    except Exception as e:
        return {"valid": False, "error": str(e)}
```

**Détection automatique du type d'actif** :
- Suffixe `=F` → commodity (futures)
- Suffixe `^` → indice
- Suffixe `-USD` ou `-EUR` → crypto
- `EURUSD=X` → forex
- Sinon → equity

**Éligibilité PEA** : règle automatique basée sur l'exchange (Euronext Paris/Amsterdam/Bruxelles/Lisbonne, Xetra, etc.) + checklist actifs blacklisted.

### UI — Watchlist Manager

```
┌──────────────────────────────────────────────────────────┐
│  📁 Mes watchlists                          [+ Nouvelle] │
├──────────────────────────────────────────────────────────┤
│  ▶ pea-actions          (12 actifs) • 3 signaux actifs  │
│  ▼ commodities          (5 actifs)  • 1 signal actif    │
│      ┌────────────────────────────────────────────────┐ │
│      │ + Ajouter actif: [_____________] 🔍            │ │
│      ├────────────────────────────────────────────────┤ │
│      │ GC=F   Or              📈 BUY  78  $2,045  [×]│ │
│      │ CL=F   Pétrole WTI     ⏸ HOLD  52  $78.20 [×] │ │
│      │ HG=F   Cuivre          ⏸ HOLD  48  $4.12  [×] │ │
│      │ SI=F   Argent          📉 SELL 32  $24.50 [×] │ │
│      │ NG=F   Gaz Naturel     📈 BUY  71  $2.85  [×] │ │
│      └────────────────────────────────────────────────┘ │
│  ▶ indices              (4 actifs)                      │
│  ▶ crypto               (3 actifs)                      │
└──────────────────────────────────────────────────────────┘
```

**Interactions clés :**
- Drag & drop pour réorganiser actifs entre watchlists
- Clic-droit sur actif → menu contextuel (toggle pause, voir détails, supprimer)
- Bouton "+" en haut → modal d'ajout avec auto-complete
- Toggle pour "pauser" un actif sans le supprimer (utile pendant earnings)

### Cas particuliers gérés

| Cas | Comportement |
|-----|-------------|
| Symbole invalide | Erreur claire à l'utilisateur, pas d'ajout silencieux |
| Symbole délisté ou inactif | Warning : "Pas de données depuis 30j — confirmer ?" |
| Trop d'actifs | Soft cap à **30 actifs actifs** (perf VPS), warning au-delà |
| Doublon dans même watchlist | Toast : "AAPL est déjà dans cette watchlist" |
| Ticker renommé (FB → META) | Endpoint dédié `/assets/{id}/migrate` |
| Asset class inconnue | Fallback `'other'` + demande à l'user |

### Cohérence avec l'orchestrateur

```python
# Le scheduler lit la watchlist depuis la DB (plus de hardcoded)
async def get_active_assets() -> list[dict]:
    return await db.fetch_all("""
        SELECT DISTINCT a.ticker, a.asset_type, a.exchange,
               MIN(w.refresh_interval) as refresh_interval
        FROM assets a
        JOIN watchlist_assets wa ON wa.asset_id = a.id
        JOIN watchlists w ON w.id = wa.watchlist_id
        WHERE wa.enabled = TRUE
        GROUP BY a.ticker, a.asset_type, a.exchange
    """)

# Notification Redis quand la watchlist change
async def on_watchlist_changed(action: str, ticker: str):
    await redis.publish('watchlist:changed', json.dumps({
        'action': action,  # 'added' | 'removed' | 'paused' | 'resumed'
        'ticker': ticker
    }))
    # Le scheduler invalide son cache au cycle suivant
```

**Important :** les données OHLC historiques restent en TimescaleDB même si l'actif est retiré d'une watchlist (utile pour réajout futur ou analyse comparée).

---

## 9. Dashboard — features et UX
```
┌──────────────────────────────────────────────────────┐
│ Header: Watchlist • Status agents • Dernière maj    │
├──────────────────────────────────────────────────────┤
│                                          ┌─────────┐ │
│                                          │ SIGNAL  │ │
│         Chart TradingView                │  BUY    │ │
│         (candles + EMA + Bollinger)      │  78/100 │ │
│                                          ├─────────┤ │
│                                          │ Détails │ │
│                                          │ • Tech: │ │
│                                          │   34/40 │ │
│                                          │ • News: │ │
│                                          │   12/15 │ │
│                                          │ • Macro:│ │
│                                          │   11/15 │ │
│                                          └─────────┘ │
├──────────────────────────────────────────────────────┤
│ Reasoning IA: "Convergence haussière sur 4H..."     │
│ Risks: • Résistance 2050  • Fed mercredi            │
│ Invalidation: cloture sous 1980                     │
├──────────────────────────────────────────────────────┤
│ News Feed (live)  │  Historique signaux  │  Perf    │
└──────────────────────────────────────────────────────┘
```

### Features clés
- **Transparence du scoring** : voir exactement d'où viennent les points (anti-boîte noire)
- **Timeline signaux** : historique chronologique avec outcome (combien de % de raison)
- **Alertes configurables** : seuils par actif, canaux (Telegram/email)
- **Mode "panic"** : kill-switch global qui désactive tous les signaux (utile en backtest live)
- **Dark mode par défaut** (regards prolongés sur écrans)

### Stack frontend
- Next.js 14 App Router (familier)
- shadcn/ui (composants prêts)
- TradingView Lightweight Charts (charts)
- Recharts (mini graphs scoring)
- TanStack Query (state serveur)
- SSE pour live updates

---

## 10. Roadmap MVP → V3

### 🟢 MVP (2-3 semaines) — "ça marche"
- 5 actifs : Or (GC=F), Pétrole (CL=F), S&P500 (^GSPC), CAC40 (^FCHI), Bitcoin (BTC-USD)
- Agents Market Data + Technical Analysis + Pattern Detection (tous déterministes)
- Scoring sans LLM (règles uniquement)
- Dashboard read-only avec chart + signal courant
- Notifs Telegram basiques
- **Objectif :** valider la pipeline end-to-end

### 🟡 V2 (4-6 semaines) — "c'est intelligent"
- Ajout Agent Sentiment Analyzer (LLM)
- Ajout Agent Signal Synthesizer (LLM) avec reasoning
- News feed live dans dashboard
- Historique signaux + tracking outcome
- Backtesting basique (vectorbt)
- **Objectif :** valider la qualité des signaux

### 🔴 V3 (2-3 mois) — "ça apprend"
- Agent Macro Contextualizer
- Multi-timeframe analysis (1H + 4H + 1D)
- Module backtest avancé (walk-forward)
- Auto-learning : régression logistique sur historique signaux vs réalité → ajuste pondérations
- Mode comparatif : "qu'aurait fait l'agent Buffett vs Graham" (style FinceptTerminal)
- **Objectif :** convergence vers la fiabilité

---

## 11. Estimation des coûts

| Poste | Coût mensuel |
|-------|-------------|
| VPS Hostinger | déjà payé (0€ marginal) |
| PostgreSQL + Redis self-hosted | 0€ |
| APIs données (toutes gratuites) | 0€ |
| GPT-4o-mini (~50-100 calls/j optimisé) | **3-8€/mois** |
| Domaine + SSL | déjà payé |
| **Total marginal** | **~5€/mois** |

**Volumétrie LLM estimée** :
- Sentiment : 4 calls/heure × 24h × 30j = 2880 calls/mois (cachés 15min)
- Signal Synthesizer : ~20 calls/jour (uniquement sur changements significatifs)
- Macro : 4 calls/jour
- **Total : ~3500 calls/mois × ~0.0015€ = ~5€**

Ton crédit OpenAI couvre largement.

---

## 12. Anti-biais et faux signaux

### Pièges techniques
- **Multicolinéarité indicateurs** : RSI + Stochastique = redondant. Choisir UN indicateur par catégorie (momentum, tendance, volatilité, volume)
- **Overfitting backtest** : ne JAMAIS optimiser les paramètres sur les mêmes données que le test final → walk-forward obligatoire
- **Survivorship bias** : tester sur 2008, 2020, 2022 (périodes de crash) sinon résultats biaisés
- **Look-ahead bias** : attention au timestamping — un indicateur calculé en fin de bougie n'est dispo qu'à la suivante

### Garde-fous opérationnels
- **Cooldown 48h** : pas de signal opposé < 48h après le précédent
- **Filtre liquidité** : pas de signal si volume < moyenne 20 jours / 2
- **Filtre volatilité** : pas de signal si ATR explose (régime instable)
- **Multi-timeframe confirmation** : signal D doit être cohérent avec signal 4H
- **Macro override** : si récession confirmée → biais SELL sur risk assets, peu importe la tech

### Anti-LLM-hallucination
- **JSON mode strict** sur OpenAI (response_format)
- **Validation Pydantic** sur tous les outputs LLM
- **Fallback déterministe** : si LLM down ou JSON invalide → utiliser le score technique pur
- **Logging exhaustif** : chaque output LLM stocké pour audit

---

## 13. Bonus

### A. Communication multi-agents (pattern Pub/Sub)

```python
# Pattern simple via Redis
redis_client.publish('signals.technical.GC=F', json.dumps({
    'agent': 'technical_analysis',
    'asset': 'GC=F',
    'timestamp': now,
    'signals': {...}
}))

# Signal Synthesizer écoute tous les channels
pubsub.subscribe('signals.*')
for message in pubsub.listen():
    aggregate(message)
    if should_synthesize():
        call_llm()
```

**Avantages** : découplage total, scalable, auditable (tout logged dans PostgreSQL).

### B. Auto-learning futur (V3+)

Ne pas partir sur du deep learning. Approche pragmatique :

1. **Stocker chaque signal généré** + features qui l'ont produit
2. **Mesurer outcome** après N jours (5, 10, 20)
3. **Régression logistique** : `P(signal_correct) = f(feature_1, feature_2, ...)`
4. **Ajuster pondérations** du scoring composite selon coefficients trouvés
5. **Détecter les indicateurs morts** : si la corrélation baisse, le marché a changé de régime

Outils : `scikit-learn` (gratuit, suffit largement). Pas besoin de PyTorch.

### C. Backtesting simple

**MVP backtest avec `vectorbt`** :
```python
import vectorbt as vbt

# Charger 5 ans d'OHLC
prices = vbt.YFData.download('GC=F', start='2020-01-01').get('Close')

# Générer signaux avec ta logique
entries = (rsi < 30) & (macd_cross_up)
exits = (rsi > 70) | (macd_cross_down)

# Backtest
pf = vbt.Portfolio.from_signals(prices, entries, exits, init_cash=10000)
print(pf.stats())  # Sharpe, drawdown, win rate, etc.
```

**Walk-forward** : `backtrader` est plus complet pour ça, mais plus complexe à prendre en main. Commencer par vectorbt.

---

## 14. Ordre d'implémentation pratique

Pour ton kick-off (10-12 jours à 10h/semaine) :

1. **J1** : VPS prep — Docker Compose avec PostgreSQL + TimescaleDB + Redis + n8n + FastAPI vide. Migrations DB initiales (tables `watchlists`, `assets`, `watchlist_assets`, `signals`).
2. **J2** : Agent Watchlist Manager — endpoints CRUD + validation yfinance + seed initial avec 5 actifs (or, pétrole, S&P500, CAC40, BTC).
3. **J3** : Agent Market Data — fetch yfinance basé sur la watchlist DB + écriture TimescaleDB.
4. **J4** : Agent Technical Analysis — pandas-ta + outputs sur Redis.
5. **J5** : Endpoint FastAPI `/signals/{ticker}` + `/watchlists/{id}/assets` qui retourne dernier état.
6. **J6** : Frontend Next.js — page watchlists (CRUD UI) + page détail actif (chart TradingView + signal).
7. **J7** : Pattern Detection + scoring déterministe.
8. **J8** : Notif Telegram + finitions UX.

À ce stade, **le MVP est utilisable et utile**. La watchlist est dynamique dès le départ (J2) parce que coder sans elle = devoir tout refactorer après. Le LLM vient en V2 quand la pipeline est solide.

---

## 15. Pièges à éviter (vu sur des projets similaires)

1. **Vouloir trop d'actifs au début** → 5 max au MVP, sinon tu ne sais plus rien debugger
2. **Mettre du LLM partout** → coût explose et latence aussi
3. **Sur-orchestrer avec n8n** → utiliser n8n pour les workflows métiers (notifs, hooks externes), pas pour les calculs intensifs (Python pur)
4. **Négliger le logging** → impossible de débugger un signal douteux 3 jours après
5. **Croire ses backtests** → résultats backtest > 50% Sharpe = probablement biaisé
6. **Oublier les frais & slippage dans les backtests** → vectorbt et backtrader gèrent ça
7. **Coder sans tests sur la logique scoring** → un bug ici = signaux faux pendant des semaines

---

## Synthèse exécutive

| Question | Réponse |
|----------|---------|
| **Faisable sur ton VPS ?** | Oui, largement — 5 actifs + 1m refresh = charge minime |
| **Coût mensuel ?** | ~5€ avec ton crédit OpenAI existant |
| **Temps MVP ?** | 2-3 semaines à 10h/semaine |
| **Risque principal ?** | Faux signaux par over-fitting → walk-forward obligatoire |
| **Quick win ?** | MVP sans LLM en 1 semaine, LLM en V2 |
| **Erreur fatale à éviter ?** | Ajouter du LLM partout dès le départ |
