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
  if (res.status === 204 || res.headers.get("content-length") === "0") {
    return undefined as T;
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
  asset_label?: string;
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

export interface Position {
  id: string;
  asset_id: string;
  ticker: string;
  asset_name: string;
  account_type: "PEA" | "PEE" | "CTO" | "AUTRE";
  quantity: number;
  avg_price: number;
  currency: string | null;
  is_pea_eligible: boolean;
  opened_at: string | null;
  notes: string | null;
  is_active: boolean;
}

export interface SignalOutcome {
  days_elapsed: number;
  return_pct: number | null;
  was_correct: boolean | null;
  checked_at: string | null;
}

export interface SignalWithOutcome extends Signal {
  outcome: SignalOutcome | null;
}

export interface AccuracyStats {
  total_signals_tracked: number;
  message?: string;
  global_accuracy_pct: number | null;
  buy_accuracy_pct: number | null;
  sell_accuracy_pct: number | null;
  avg_return_all_pct: number | null;
  avg_return_correct_pct: number | null;
  avg_return_incorrect_pct: number | null;
  calibration: {
    high_confidence: { n: number; accuracy_pct: number | null };
    medium_confidence: { n: number; accuracy_pct: number | null };
  };
}

export interface BacktestMetrics {
  n_trades: number;
  win_rate_pct?: number;
  avg_return_pct?: number;
  sharpe_ratio?: number;
  max_drawdown_pct?: number;
  cumulative_return_pct?: number;
  horizon_days: number;
  calibration?: {
    high_confidence_win_rate_pct: number | null;
    medium_confidence_win_rate_pct: number | null;
    n_high: number;
    n_medium: number;
  };
}

export interface BacktestDiagnostics {
  label: "robust" | "noisy" | "over_traded" | "unstable" | "bearish_asset" | "mixed";
  label_reason: string;
  recommendation: "keep" | "monitor" | "exclude";
  recommendation_reason: string;
  signal_quality: {
    total_signals: number;
    buy_count: number;
    sell_count: number;
    signal_frequency_per_year: number;
    false_signal_rate_pct: number | null;
    return_std_pct: number;
    return_dispersion_p25: number;
    return_dispersion_p75: number;
    stability_first_half_wr: number | null;
    stability_second_half_wr: number | null;
    stability_delta_pct: number;
  };
  score_calibration: Record<string, { n: number; win_rate_pct: number | null; avg_return_pct: number | null }>;
  confidence_calibration: Record<string, { n: number; win_rate_pct: number | null; avg_return_pct: number | null }>;
  by_signal_type: Record<string, {
    n: number;
    win_rate_pct: number | null;
    avg_return_pct: number | null;
    sharpe: number | null;
    max_drawdown_pct?: number;
  }>;
  patterns_analysis: Record<string, {
    occurrences: number;
    win_rate_pct: number | null;
    avg_return_pct: number;
    avg_return_5d: number | null;
    avg_return_10d: number | null;
  }>;
  overtrading: {
    is_over_traded: boolean;
    signal_frequency_per_year: number;
    threshold: number;
    severity: "none" | "moderate" | "severe";
  };
}

export interface BacktestResult {
  ticker: string;
  period: string;
  total_signals: number;
  buy_signals: number;
  sell_signals: number;
  error?: string;
  metrics: BacktestMetrics;
  benchmarks: {
    buy_and_hold_pct: number;
    momentum_avg_return_pct: number;
    ma_crossover_avg_return_pct: number;
  };
  diagnostics?: BacktestDiagnostics;
  signals: Array<{
    date: string;
    signal_type: string;
    score: number;
    tech_score?: number;
    mom_score?: number;
    confidence: number;
    confidence_label: string;
    price: number;
    return_5d: number | null;
    return_10d: number | null;
    return_20d: number | null;
    correct_20d: boolean | null;
  }>;
}

export interface SystemSettings {
  telegram_enabled: boolean;
  panic_mode: boolean;
  alert_threshold: number;
  min_confidence: number;
  cooldown_minutes: number;
  quiet_start: number;
  quiet_end: number;
  daily_digest: boolean;
  buy_threshold: number;
  sell_threshold: number;
}

export interface SystemStatus {
  panic_mode: boolean;
  telegram_enabled: boolean;
  market_open: boolean;
  last_signal_at: string | null;
  sentiment_available: boolean;
  macro_available: boolean;
  timestamp: string;
}

export interface AgentStatus {
  id: string;
  label: string;
  icon: string;
  status: "ok" | "error" | "unknown";
  last_run: string | null;
  elapsed_seconds: number | null;
  ago: string;
  result: string;
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
    recent: (limit = 50) => request<SignalWithOutcome[]>(`/api/signals/recent?limit=${limit}`),
    top: () => request<Signal[]>("/api/signals/top"),
    outcome: (signalId: string) => request<SignalOutcome[]>(`/api/signals/${signalId}/outcome`),
  },

  backtest: {
    stats: () => request<AccuracyStats>("/api/backtest/stats"),
    run: (ticker: string, period = "5y", horizonDays = 20) =>
      request<BacktestResult>(`/api/backtest/${encodeURIComponent(ticker)}?period=${period}&horizon_days=${horizonDays}`),
    tickerAccuracy: (ticker: string) =>
      request<{ ticker: string; total_tracked: number; accuracy_pct?: number; avg_return_pct?: number }>(`/api/backtest/${encodeURIComponent(ticker)}/accuracy`),
    multi: (tickers: string[], period = "5y", horizonDays = 20) =>
      request<{ results: BacktestResult[]; comparison: Array<Record<string, unknown>> }>("/api/backtest/multi", {
        method: "POST",
        body: JSON.stringify({ tickers, period, horizon_days: horizonDays }),
      }),
  },

  portfolio: {
    positions: () => request<Position[]>("/api/portfolio/positions"),
    addPosition: (data: {
      ticker: string;
      account_type: string;
      quantity: number;
      avg_price: number;
      notes?: string;
    }) =>
      request<Position>("/api/portfolio/positions", {
        method: "POST",
        body: JSON.stringify(data),
      }),
    updatePosition: (
      id: string,
      data: Partial<{ account_type: string; quantity: number; avg_price: number; notes: string }>
    ) =>
      request<Position>(`/api/portfolio/positions/${id}`, {
        method: "PATCH",
        body: JSON.stringify(data),
      }),
    deletePosition: (id: string) =>
      request<{ deleted: boolean }>(`/api/portfolio/positions/${id}`, { method: "DELETE" }),
  },

  health: () => request<{ status: string; version: string }>("/health"),

  settings: {
    get: () => request<SystemSettings>("/api/settings"),
    update: (data: Partial<SystemSettings>) =>
      request<SystemSettings>("/api/settings", {
        method: "PATCH",
        body: JSON.stringify(data),
      }),
    togglePanic: () =>
      request<{ panic_mode: boolean }>("/api/settings/panic", { method: "POST" }),
    status: () => request<SystemStatus>("/api/settings/status"),
    refresh: () => request<{ triggered: boolean }>("/api/settings/refresh", { method: "POST" }),
  },

  agents: {
    status: () => request<AgentStatus[]>("/api/settings/agents"),
  },
};
