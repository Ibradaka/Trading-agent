# Tasks 004 — Dashboard (Next.js)

## État : EN ATTENTE (après spec-003)

### Setup & Layout
- [ ] `frontend/src/app/layout.tsx` — providers (TanStack Query, Toaster), sidebar, dark mode
- [ ] `frontend/src/components/layout/sidebar.tsx` — navigation (Watchlist, Historique, Settings)
- [ ] `frontend/src/components/layout/header.tsx` — status agents, dernière MAJ, refresh manuel

### Page principale — Watchlist
- [ ] `frontend/src/app/page.tsx` — Tabs par watchlist + liste actifs
- [ ] `frontend/src/components/watchlist/watchlist-panel.tsx` — panel complet
- [ ] `frontend/src/components/watchlist/asset-row.tsx` — ligne avec signal, score, sparkline, badge PEA
- [ ] `frontend/src/components/watchlist/add-asset-modal.tsx` — modal ajout ticker (validation live)
- [ ] `frontend/src/components/charts/sparkline.tsx` — mini chart 30j (Lightweight Charts)
- [ ] `frontend/src/components/signals/signal-badge.tsx` — badge coloré BUY/SELL/HOLD

### Page détail actif
- [ ] `frontend/src/app/asset/[ticker]/page.tsx` — layout detail
- [ ] `frontend/src/components/charts/trading-view-chart.tsx` — chart TradingView + overlays
- [ ] `frontend/src/components/signals/score-gauge.tsx` — gauge circulaire composite
- [ ] `frontend/src/components/signals/score-radar.tsx` — radar 5 axes (Recharts)
- [ ] `frontend/src/components/signals/signal-card.tsx` — raisonnement + risques + invalidation

### Page historique
- [ ] `frontend/src/app/history/page.tsx` — layout historique
- [ ] `frontend/src/components/history/signal-timeline.tsx` — timeline chronologique
- [ ] `frontend/src/components/history/accuracy-chart.tsx` — graphe accuracy (Recharts)

### Page settings
- [ ] `frontend/src/app/settings/page.tsx` — gestion watchlists + poids scoring + Telegram

### Hooks & Data layer
- [ ] `frontend/src/hooks/use-sse.ts` — SSE avec reconnexion auto
- [ ] `frontend/src/hooks/use-signals.ts` — TanStack Query + SSE invalidation
- [ ] `frontend/src/hooks/use-watchlist.ts` — CRUD watchlists
- [ ] `frontend/src/lib/api.ts` — client API typé complet
- [ ] `frontend/src/lib/sse.ts` — logique SSE + reconnect backoff

### UX polish
- [ ] Toasts pour signaux forts (emerald/red)
- [ ] Loading skeletons sur tous les composants async
- [ ] Framer Motion transitions entre pages
- [ ] Responsive tablette (1024px)
