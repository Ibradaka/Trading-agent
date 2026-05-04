"use client";

import { useQueries } from "@tanstack/react-query";
import { api, AssetQuote } from "@/lib/api";
import { cn } from "@/lib/utils";
import { TrendingUp, TrendingDown, Minus } from "lucide-react";

const MARKET_GROUPS = [
  {
    label: "Indices",
    items: [
      { ticker: "^GSPC",  label: "S&P 500",  yf: "^GSPC" },
      { ticker: "^IXIC",  label: "Nasdaq",   yf: "^IXIC" },
      { ticker: "^FCHI",  label: "CAC 40",   yf: "^FCHI" },
      { ticker: "^N225",  label: "Nikkei",   yf: "^N225" },
      { ticker: "000001.SS", label: "SSE",   yf: "000001.SS" },
    ],
  },
  {
    label: "Matières",
    items: [
      { ticker: "GC=F", label: "Or",      yf: "GC=F" },
      { ticker: "CL=F", label: "Pétrole", yf: "CL=F" },
    ],
  },
  {
    label: "Crypto",
    items: [
      { ticker: "BTC-USD", label: "BTC", yf: "BTC-USD" },
      { ticker: "ETH-USD", label: "ETH", yf: "ETH-USD" },
    ],
  },
  {
    label: "Macro",
    items: [
      { ticker: "^TNX",     label: "T-Note 10Y", yf: "^TNX" },
      { ticker: "DX-Y.NYB", label: "USD Index",  yf: "DX-Y.NYB" },
      { ticker: "^VIX",     label: "VIX",        yf: "^VIX" },
      { ticker: "EURUSD=X", label: "€/$",        yf: "EURUSD=X" },
    ],
  },
];

const ALL_ITEMS = MARKET_GROUPS.flatMap((g) => g.items);

function formatPrice(price: number | null, ticker: string): string {
  if (price === null) return "—";
  if (ticker.startsWith("^VIX") || ticker === "^TNX") return price.toFixed(2);
  if (price >= 1000) return Math.round(price).toString().replace(/\B(?=(\d{3})+(?!\d))/g, " ");
  if (price >= 100) return price.toFixed(2);
  return price.toFixed(2);
}

function MarketBubble({
  label,
  ticker,
  yf,
  quote,
  loading,
}: {
  label: string;
  ticker: string;
  yf: string;
  quote: AssetQuote | undefined;
  loading: boolean;
}) {
  const pct = quote?.change_pct ?? null;
  const price = quote?.current_price ?? null;

  const isPositive = pct !== null && pct > 0;
  const isNegative = pct !== null && pct < 0;

  const pctColor = isPositive ? "text-emerald-400" : isNegative ? "text-red-400" : "text-slate-400";
  const borderColor = isPositive
    ? "border-emerald-500/20 hover:border-emerald-500/50"
    : isNegative
    ? "border-red-500/20 hover:border-red-500/50"
    : "border-slate-700/50 hover:border-slate-600";
  const bgGlow = isPositive ? "hover:bg-emerald-500/5" : isNegative ? "hover:bg-red-500/5" : "hover:bg-slate-800/50";

  return (
    <a
      href={`https://finance.yahoo.com/quote/${encodeURIComponent(yf)}`}
      target="_blank"
      rel="noopener noreferrer"
      className={cn(
        "flex flex-col gap-0.5 px-2.5 py-1.5 rounded-lg border bg-slate-900/60 transition-all duration-200 min-w-[78px]",
        borderColor,
        bgGlow
      )}
    >
      <span className="text-[10px] font-medium text-slate-500 truncate">{label}</span>

      {loading ? (
        <div className="h-4 w-12 bg-slate-800 rounded animate-pulse" />
      ) : (
        <>
          <span className="text-xs font-mono font-semibold text-slate-200 leading-tight">
            {formatPrice(price, ticker)}
          </span>
          <div className={cn("flex items-center gap-0.5 text-[10px] font-medium", pctColor)}>
            {pct === null ? (
              <Minus className="w-2 h-2" />
            ) : isPositive ? (
              <TrendingUp className="w-2 h-2" />
            ) : (
              <TrendingDown className="w-2 h-2" />
            )}
            <span>{pct !== null ? `${pct >= 0 ? "+" : ""}${pct.toFixed(2)}%` : "—"}</span>
          </div>
        </>
      )}
    </a>
  );
}

export function MarketOverviewBar() {
  const results = useQueries({
    queries: ALL_ITEMS.map((item) => ({
      queryKey: ["quote", item.ticker],
      queryFn: () => api.assets.quote(item.ticker),
      refetchInterval: 60_000,
      staleTime: 30_000,
      retry: false,
    })),
  });

  const quoteMap: Record<string, AssetQuote> = {};
  ALL_ITEMS.forEach((item, i) => {
    const data = results[i]?.data;
    if (data) quoteMap[item.ticker] = data;
  });

  return (
    <div className="px-3 py-2 bg-slate-900 rounded-xl border border-slate-800">
      <div className="flex gap-3 overflow-x-auto scrollbar-none items-center">
        {MARKET_GROUPS.map((group, gi) => (
          <div key={gi} className="flex items-center gap-1.5 flex-shrink-0">
            <span className="text-[9px] font-semibold text-slate-600 uppercase tracking-wider whitespace-nowrap mr-0.5">
              {group.label}
            </span>
            <div className="flex gap-1.5">
              {group.items.map((item) => {
                const idx = ALL_ITEMS.findIndex((x) => x.ticker === item.ticker);
                return (
                  <MarketBubble
                    key={item.ticker}
                    label={item.label}
                    ticker={item.ticker}
                    yf={item.yf}
                    quote={quoteMap[item.ticker]}
                    loading={results[idx]?.isLoading ?? true}
                  />
                );
              })}
            </div>
            {gi < MARKET_GROUPS.length - 1 && (
              <div className="w-px self-stretch bg-slate-800 mx-1" />
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
