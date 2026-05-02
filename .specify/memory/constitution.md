# Constitution — Trading Agent Beta

## Identité et mission

Outil personnel d'aide à la décision pour swing trading sur actions (PEA + compte-titres) et indices.
Produit des signaux BUY/SELL/HOLD avec score de probabilité, raisonnement explicite et recommandations actionnables.

**Auteur** : Ibrahim Dahia — trader particulier, 18 ans d'expérience en digitalisation industrielle.
**Usage** : Personnel, mono-utilisateur, non commercial.
**Contrainte absolue** : Pas d'exécution automatique de trades. L'humain décide toujours.

---

## Principes immuables

### 1. Transparence totale
Chaque signal doit expliquer POURQUOI il a été généré. Pas de boîte noire.
L'utilisateur doit pouvoir auditer le score composante par composante.

### 2. Déterminisme avant LLM
Les calculs déterministes (RSI, MACD, patterns) ne doivent JAMAIS être délégués à un LLM.
Le LLM intervient uniquement pour la synthèse narrative et la contextualisation.

### 3. Anti-overfitting obligatoire
Walk-forward testing sur toute nouvelle logique de scoring.
Jamais d'optimisation de paramètres sur les données de test.
Tester sur 2008, 2020, 2022 (périodes de crise) avant de valider une stratégie.

### 4. Fallback déterministe
Si le LLM est indisponible ou retourne un JSON invalide, le système continue avec le score déterministe.
Aucun agent LLM ne peut bloquer le pipeline principal.

### 5. Coût maîtrisé
Budget LLM cible : < 10€/mois.
Cache Redis agressif : TTL 15min sur sentiment, TTL 6h sur macro.
Batch les appels LLM : plusieurs actifs dans un seul prompt quand possible.

### 6. Marchés européens en priorité
PEA = actions européennes éligibles (Euronext Paris/Amsterdam/Bruxelles, Xetra).
Compte-titres = international.
Heures de marché : 09h00–17h30 CET. Pas de refresh hors heures de cotation.

### 7. Garde-fous anti-biais
- Cooldown 48h entre signaux opposés sur le même actif
- Filtre liquidité : volume < moyenne 20j / 2 → pas de signal
- Multi-timeframe : signal daily doit être cohérent avec 4H
- Macro override : en récession confirmée → biais SELL sur risk assets

---

## Décisions techniques fondamentales

| Décision | Choix | Raison |
|---|---|---|
| Données marché | yfinance uniquement (free) | Suffisant pour swing trading daily |
| DB time-series | TimescaleDB sur PostgreSQL | Gratuit, optimisé OHLC |
| Cache | Redis | Pub/Sub entre agents + cache LLM |
| LLM | GPT-4o-mini uniquement | Meilleur rapport qualité/prix |
| Charts | TradingView Lightweight Charts | Gratuit, look professionnel |
| Real-time | SSE (Server-Sent Events) | Suffisant pour 1 utilisateur |
| Orchestration | APScheduler intégré Python | Pas de dépendance externe |
| Deploy | Docker Compose VPS | Contrôle total, coût nul |

---

## Ce que ce projet ne fait pas

- Pas d'exécution automatique de trades
- Pas de gestion de portefeuille (positions, P&L réel)
- Pas de connexion aux APIs de brokers
- Pas de multi-utilisateur
- Pas de données premium payantes
- Pas de HFT / scalping (minimum swing daily)
- Pas de Twitter/X scraping (bloqué + payant)
- Pas de machine learning complexe (V3 seulement)
