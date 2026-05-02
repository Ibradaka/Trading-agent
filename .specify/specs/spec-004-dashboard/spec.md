# Spec 004 — Dashboard (Next.js)

## Objectif
Dashboard professionnel, dark mode par défaut, temps réel via SSE.
Tout ce dont l'utilisateur a besoin pour exploiter les signaux de trading au quotidien.

## Pages

### Page principale `/` — Vue Watchlist
- Liste toutes les watchlists avec leurs actifs
- Score composite + signal (BUY/SELL/HOLD) colorés par actif
- Mini sparkline 30 jours par actif
- Badge PEA / CTO
- Fraîcheur du signal (dernière analyse)
- Barre de recherche pour filtrer
- Accès rapide aux watchlists par onglets

### Page `/asset/[ticker]` — Vue Détail Actif
- Header : nom, ticker, prix actuel, variation %, signal courant
- Chart TradingView (chandeliers + overlays configurables)
  - EMA 20/50/200 toggleables
  - Bollinger Bands toggleable
  - Volume subplot
  - RSI subplot (14)
  - MACD subplot
- Panneau latéral droit :
  - Score composite gauge circulaire
  - Breakdown radar (technique/patterns/momentum/macro/sentiment)
  - Raisonnement LLM explicité
  - Risques identifiés
  - Condition d'invalidation
  - Horizon temporel recommandé
  - Position sizing recommandée
- Historique des signaux sur cet actif (timeline)
- News RSS récentes liées à l'actif

### Page `/history` — Historique & Performance
- Timeline chronologique de tous les signaux générés
- Filtre par watchlist, signal type, période
- Accuracy tracking : % de signaux corrects (J+5, J+10, J+20)
- Graphe de performance hypothétique (backtest replay)
- Heatmap des signaux par actif et par semaine

### Page `/settings` — Configuration
- Gestion des watchlists (CRUD complet)
- Ajout/suppression d'actifs (avec validation live)
- Cadence de refresh par watchlist
- Seuils d'alerte Telegram
- Poids du scoring ajustables
- Clés API (masquées)

## Critères d'acceptation

- [ ] Dashboard charge en < 2s (LCP)
- [ ] SSE : les scores se mettent à jour sans reload page
- [ ] Chart TradingView : chandeliers + 3 overlays + 2 subgraphes
- [ ] Score radar animé à chaque mise à jour
- [ ] Responsive : utilisable sur tablette (1024px+)
- [ ] Dark mode par défaut, toggle light optionnel
- [ ] Ajout d'un ticker : validation live en < 1s avec preview métadonnées
- [ ] Drag & drop actifs entre watchlists
- [ ] Toasts non-intrusifs pour les signaux forts

## Stack UI
- shadcn/ui : Card, Badge, Button, Input, Select, Tabs, Sheet, Toast, Tooltip
- Recharts : RadarChart (scoring breakdown), LineChart (performance)
- TradingView Lightweight Charts : chart principal
- Framer Motion : transitions page, animations score
- date-fns : formatage dates
- clsx + tailwind-merge : classes conditionnelles
