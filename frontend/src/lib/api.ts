// Browser: relative URLs proxied by Next.js. SSR: internal backend URL.
const API_BASE = typeof window !== "undefined"
  ? ""
  : (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8899");

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  });
  if (!res.ok) {
    const body = await res.text();
    throw new ApiError(res.status, body);
  }
  return res.json() as Promise<T>;
}

// ===== Types =====

export interface Watchlist {
  id: string;
  name: string;
  description: string | null;
  refresh_interval_minutes: number;
  signal_threshold: number;
  is_active: boolean;
  created_at: string;
}

export interface WatchlistDetail extends Watchlist {
  assets: WatchlistAssetEntry[];
}

export interface WatchlistAssetEntry {
  ticker: string;
  name: string;
  asset_type: string;
  is_pea_eligible: boolean;
  currency: string;
  is_active: boolean;
  notes: string | null;
  target_buy_price: number | null;
  target_sell_price: number | null;
}

export interface TickerValidation {
  valid: boolean;
  ticker?: string;
  name?: string;
  asset_type?: string;
  exchange?: string;
  currency?: string;
  sector?: string;
  country?: string;
  is_pea_eligible?: boolean;
  current_price?: number;
  error?: string;
}

export interface ScoreBreakdown {
  technical: number;
  patterns: number;
  sentiment: number;
  macro: number;
  momentum: number;
}

export interface Signal {
  id: string;
  ticker: string;
  asset_name: string;
  signal_type: "BUY" | "SELL" | "HOLD";
  strength: "strong" | "weak";
  composite_score: number;
  confidence: number;
  scores: ScoreBreakdown;
  reasoning: string;
  risks: string[];
  invalidation_conditions: string;
  horizon: string;
  timestamp: string;
  is_active: boolean;
}

export interface OHLCBar {
  date: number;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number;
  volume: number | null;
}

export interface AssetQuote {
  ticker: string;
  current_price: number | null;
  previous_close: number | null;
  change_pct: number | null;
  week_change_pct: number | null;
  month_change_pct: number | null;
  currency: string | null;
  exchange: string | null;
  market_state: string | null;
  open: number | null;
  day_high: number | null;
  day_low: number | null;
  volume: number | null;
  week52_high: number | null;
  week52_low: number | null;
  history: OHLCBar[];
}

export interface NewsItem {
  title: string;
  title_original: string;
  link: string;
  publisher: string;
  published_at: number | null;
}

export interface WatchlistSignalEntry {
  ticker: string;
  name: string;
  is_pea_eligible: boolean;
  asset_type: string;
  signal: Signal | null;
}

// ===== Watchlists =====

export const api = {
  watchlists: {
    list: () => request<Watchlist[]>("/api/watchlists/"),
    get: (id: string) => request<WatchlistDetail>(`/api/watchlists/${id}`),
    create: (data: { name: string; description?: string; refresh_interval_minutes?: number }) =>
      request<{ id: string; name: string }>("/api/watchlists/", {
        method: "POST",
        body: JSON.stringify(data),
      }),
    update: (id: string, data: Partial<Watchlist>) =>
      request<{ updated: boolean }>(`/api/watchlists/${id}`, {
        method: "PATCH",
        body: JSON.stringify(data),
      }),
    delete: (id: string) =>
      request<void>(`/api/watchlists/${id}`, { method: "DELETE" }),
    addAsset: (watchlistId: string, ticker: string, notes?: string) =>
      request<{ ticker: string; added: boolean }>(`/api/watchlists/${watchlistId}/assets`, {
        method: "POST",
        body: JSON.stringify({ ticker, notes }),
      }),
    removeAsset: (watchlistId: string, ticker: string) =>
      request<void>(`/api/watchlists/${watchlistId}/assets/${ticker}`, { method: "DELETE" }),
    signals: (watchlistId: string) =>
      request<WatchlistSignalEntry[]>(`/api/signals/watchlist/${watchlistId}`),
  },

  assets: {
    validate: (ticker: string) =>
      request<TickerValidation>(`/api/assets/validate?ticker=${encodeURIComponent(ticker)}`),
    validateAndAdd: (ticker: string) =>
      request<{ ticker: string; created: boolean }>(`/api/assets/validate/add?ticker=${encodeURIComponent(ticker)}`, {
        method: "POST",
      }),
    search: (q: string) =>
      request<WatchlistAssetEntry[]>(`/api/assets/search?q=${encodeURIComponent(q)}`),
    quote: (ticker: string) =>
      request<AssetQuote>(`/api/assets/${encodeURIComponent(ticker)}/quote`),
    news: (ticker: string) =>
      request<NewsItem[]>(`/api/assets/${encodeURIComponent(ticker)}/news`),
  },

  signals: {
    latest: (ticker: string) => request<Signal | { signal: null }>(`/api/signals/${ticker}/latest`),
    history: (ticker: string, limit = 20) =>
      request<Signal[]>(`/api/signals/${ticker}/history?limit=${limit}`),
    active: () => request<Signal[]>("/api/signals/active"),
  },

  health: () => request<{ status: string; version: string }>("/health"),
};
