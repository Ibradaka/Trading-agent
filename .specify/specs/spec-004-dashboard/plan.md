# Plan 004 — Dashboard (Next.js)

## Architecture frontend

```
src/
├── app/
│   ├── layout.tsx              — root layout (providers, sidebar, dark mode)
│   ├── page.tsx                — watchlist overview
│   ├── asset/[ticker]/page.tsx — detail actif
│   ├── history/page.tsx        — historique signaux
│   └── settings/page.tsx       — configuration
├── components/
│   ├── layout/
│   │   ├── sidebar.tsx         — navigation latérale
│   │   └── header.tsx          — barre du haut (status, dernière MAJ)
│   ├── watchlist/
│   │   ├── watchlist-panel.tsx — liste watchlists + tabs
│   │   ├── asset-row.tsx       — ligne actif (score, signal, sparkline)
│   │   └── add-asset-modal.tsx — ajout ticker avec validation live
│   ├── signals/
│   │   ├── signal-badge.tsx    — badge BUY/SELL/HOLD coloré
│   │   ├── signal-card.tsx     — card signal complet
│   │   ├── score-gauge.tsx     — gauge circulaire composite
│   │   └── score-radar.tsx     — radar 5 axes (Recharts)
│   ├── charts/
│   │   ├── trading-view-chart.tsx  — wrapper TradingView LC
│   │   └── sparkline.tsx           — mini chart 30j
│   └── history/
│       ├── signal-timeline.tsx     — timeline signaux
│       └── accuracy-chart.tsx      — graphe accuracy
├── hooks/
│   ├── use-sse.ts              — SSE connection hook
│   ├── use-signals.ts          — TanStack Query signals
│   └── use-watchlist.ts        — TanStack Query watchlists
└── lib/
    ├── api.ts                  — client API typé
    ├── sse.ts                  — SSE reconnection logic
    └── utils.ts                — formatSignal, scoreToColor, etc.
```

## SSE Architecture

```typescript
// backend publie sur Redis → FastAPI lit → SSE stream
// frontend s'abonne à /api/stream/signals

interface SSEEvent {
  type: "signal_updated" | "price_updated" | "agent_status"
  ticker: string
  data: SignalUpdate | PriceUpdate | AgentStatus
  timestamp: string
}

// Hook useSSE reconnecte automatiquement (expo backoff)
// TanStack Query invalidate sur reception événement SSE
```

## TradingView Chart

```typescript
// @ts-ignore — TradingView pas de types officiels
import { createChart, CandlestickSeries, LineSeries } from "lightweight-charts"

// Séries :
// 1. CandlestickSeries (OHLC principal)
// 2. LineSeries EMA20 (bleu, épaisseur 1)
// 3. LineSeries EMA50 (orange, épaisseur 1.5)
// 4. LineSeries EMA200 (rouge, épaisseur 2)
// 5. LineSeries BB Upper (gris, pointillé)
// 6. LineSeries BB Lower (gris, pointillé)
// Subgraphes : Volume (histogramme), RSI (line), MACD (line + signal + histo)
```

## Couleurs signaux (Tailwind)
```
BUY fort   : emerald-500 / bg-emerald-500/20
BUY faible : emerald-400 / bg-emerald-400/10
HOLD       : slate-400   / bg-slate-400/10
SELL faible: red-400     / bg-red-400/10
SELL fort  : red-500     / bg-red-500/20
Score > 75 : text-emerald-400
Score 50-75: text-amber-400
Score < 50 : text-red-400
```

## Score Radar (Recharts)
```typescript
const RADAR_AXES = [
  { key: "technical", label: "Technique" },
  { key: "patterns",  label: "Patterns" },
  { key: "momentum",  label: "Momentum" },
  { key: "macro",     label: "Macro" },
  { key: "sentiment", label: "Sentiment" },
]
// RadarChart filled area avec opacity 0.3, stroke selon signal
```
