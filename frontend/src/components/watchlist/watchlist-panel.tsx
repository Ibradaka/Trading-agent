"use client";

import { useQuery } from "@tanstack/react-query";
import { api, type WatchlistSignalEntry, type AssetQuote } from "@/lib/api";
import { useState } from "react";
import { Plus, Loader2, TrendingUp, TrendingDown, Minus } from "lucide-react";
import Link from "next/link";
import { cn, signalLabel, scoreToColor, formatScore } from "@/lib/utils";
import { useSSE } from "@/lib/sse";
import { useQueryClient } from "@tanstack/react-query";
import {
  LineChart,
  Line,
  ResponsiveContainer,
  Tooltip,
} from "recharts";

function SignalBadge({ type, strength }: { type: string; strength: string }) {
  const label = signalLabel(type, strength);
  const classes: Record<string, string> = {
    "ACHAT FORT": "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30",
    "ACHAT": "bg-emerald-500/10 text-emerald-300 border border-emerald-500/20",
    "NEUTRE": "bg-slate-500/10 text-slate-400 border border-slate-500/30",
    "VENTE": "bg-red-500/10 text-red-300 border border-red-500/20",
    "VENTE FORTE": "bg-red-500/20 text-red-400 border border-red-500/30",
  };
  return (
    <span className={cn("text-xs font-medium px-2 py-0.5 rounded", classes[label] ?? classes["NEUTRE"])}>
      {label}
    </span>
  );
}

function Sparkline({ data, positive }: { data: { v: number }[]; positive: boolean }) {
  const color = positive ? "#10b981" : "#ef4444";
  return (
    <ResponsiveContainer width={80} height={32}>
      <LineChart data={data} margin={{ top: 2, right: 2, bottom: 2, left: 2 }}>
        <Line
          type="monotone"
          dataKey="v"
          stroke={color}
          strokeWidth={1.5}
          dot={false}
          isAnimationActive={false}
        />
        <Tooltip
          content={() => null}
          cursor={false}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}

function PriceCell({ ticker }: { ticker: string }) {
  const { data: quote, isLoading } = useQuery<AssetQuote>({
    queryKey: ["quote", ticker],
    queryFn: () => api.assets.quote(ticker),
    refetchInterval: 60_000,
    staleTime: 30_000,
  });

  if (isLoading) {
    return (
      <div className="flex items-center gap-3">
        <div className="w-20 h-4 bg-slate-800 rounded animate-pulse" />
        <div className="w-[80px] h-8 bg-slate-800 rounded animate-pulse" />
      </div>
    );
  }

  if (!quote || !quote.current_price) {
    return <span className="text-xs text-slate-600">—</span>;
  }

  const positive = (quote.change_pct ?? 0) >= 0;
  const sparkData = quote.history.map((b) => ({ v: b.close }));

  const formatPrice = (p: number, currency: string | null) => {
    const sym = currency === "GBP" ? "£" : currency === "EUR" ? "€" : currency === "USD" ? "$" : (currency ?? "");
    // GBp (pence) → divide by 100
    if (currency === "GBp") return `£${(p / 100).toFixed(2)}`;
    return `${sym}${p.toLocaleString("fr-FR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  };

  return (
    <div className="flex items-center gap-3">
      {/* Prix + variation */}
      <div className="text-right min-w-[90px]">
        <p className="text-sm font-mono font-semibold text-slate-100">
          {formatPrice(quote.current_price, quote.currency)}
        </p>
        <div className={cn("flex items-center justify-end gap-0.5 text-xs font-medium", positive ? "text-emerald-400" : "text-red-400")}>
          {positive ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
          {quote.change_pct !== null ? `${positive ? "+" : ""}${quote.change_pct.toFixed(2)}%` : "—"}
        </div>
      </div>

      {/* Sparkline 5j */}
      {sparkData.length > 1 && (
        <div className="hidden sm:block">
          <Sparkline data={sparkData} positive={positive} />
        </div>
      )}
    </div>
  );
}

function AssetRow({ entry }: { entry: WatchlistSignalEntry }) {
  const { ticker, name, is_pea_eligible, asset_type, signal } = entry;

  return (
    <Link
      href={`/asset/${ticker}`}
      className="flex items-center gap-3 px-4 py-3 hover:bg-slate-800/50 rounded-lg transition-colors group"
    >
      {/* Ticker + nom */}
      <div className="w-28 flex-shrink-0">
        <p className="text-sm font-semibold text-slate-100 group-hover:text-blue-400 transition-colors">{ticker}</p>
        <p className="text-xs text-slate-500 truncate max-w-[112px]">{name}</p>
      </div>

      {/* Badges */}
      <div className="flex gap-1 flex-shrink-0 w-20">
        {is_pea_eligible && (
          <span className="text-xs bg-blue-500/10 text-blue-400 border border-blue-500/20 px-1.5 py-0.5 rounded">
            PEA
          </span>
        )}
        {asset_type && asset_type !== "equity" && (
          <span className="text-xs bg-slate-700/50 text-slate-400 border border-slate-700 px-1.5 py-0.5 rounded capitalize">
            {asset_type}
          </span>
        )}
      </div>

      {/* Prix + sparkline */}
      <div className="flex-1">
        <PriceCell ticker={ticker} />
      </div>

      {/* Signal */}
      <div className="w-28 flex-shrink-0 text-center">
        {signal ? (
          <SignalBadge type={signal.signal_type} strength={signal.strength} />
        ) : (
          <span className="text-xs text-slate-600">En attente</span>
        )}
      </div>

      {/* Score */}
      <div className="w-16 text-right flex-shrink-0">
        {signal ? (
          <div>
            <span className={cn("text-sm font-mono font-semibold", scoreToColor(signal.composite_score))}>
              {formatScore(signal.composite_score)}
            </span>
            <p className="text-xs text-slate-600">{Math.round(signal.confidence * 100)}%</p>
          </div>
        ) : (
          <span className="text-xs text-slate-700">—</span>
        )}
      </div>
    </Link>
  );
}

function WatchlistTab({ watchlistId, threshold }: { watchlistId: string; threshold: number }) {
  const queryClient = useQueryClient();

  useSSE((msg) => {
    if (msg.type === "signal_updated") {
      queryClient.invalidateQueries({ queryKey: ["watchlist-signals", watchlistId] });
    }
  });

  const { data: entries = [], isLoading } = useQuery({
    queryKey: ["watchlist-signals", watchlistId],
    queryFn: () => api.watchlists.signals(watchlistId),
    refetchInterval: 60_000,
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 className="w-6 h-6 text-slate-600 animate-spin" />
      </div>
    );
  }

  if (entries.length === 0) {
    return (
      <div className="flex items-center justify-center py-16 border border-dashed border-slate-800 rounded-xl">
        <div className="text-center">
          <p className="text-slate-600 text-sm">Aucun actif dans cette watchlist</p>
          <p className="text-slate-700 text-xs mt-1">Utilisez le bouton + pour en ajouter</p>
        </div>
      </div>
    );
  }

  const sorted = [...entries].sort((a, b) => {
    const sa = a.signal?.composite_score ?? 50;
    const sb = b.signal?.composite_score ?? 50;
    return sb - sa;
  });

  return (
    <div className="space-y-0.5">
      {/* En-têtes */}
      <div className="flex items-center gap-3 px-4 py-2 text-xs text-slate-600 border-b border-slate-800 mb-1">
        <span className="w-28">Actif</span>
        <span className="w-20">Type</span>
        <span className="flex-1">Prix / 5 jours</span>
        <span className="w-28 text-center">Signal</span>
        <span className="w-16 text-right">Score</span>
      </div>
      {sorted.map((entry) => (
        <AssetRow key={entry.ticker} entry={entry} />
      ))}
    </div>
  );
}

export function WatchlistPanel() {
  const [activeTab, setActiveTab] = useState<string | null>(null);

  const { data: watchlists = [], isLoading } = useQuery({
    queryKey: ["watchlists"],
    queryFn: api.watchlists.list,
  });

  const currentId = activeTab ?? watchlists[0]?.id;
  const currentWl = watchlists.find((w) => w.id === currentId);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 className="w-6 h-6 text-slate-600 animate-spin" />
      </div>
    );
  }

  if (watchlists.length === 0) {
    return (
      <div className="flex items-center justify-center py-24 border border-dashed border-slate-800 rounded-xl">
        <div className="text-center">
          <p className="text-slate-500">Aucune watchlist créée</p>
          <p className="text-slate-700 text-xs mt-1">Créez votre première watchlist dans les paramètres</p>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-slate-900 rounded-xl border border-slate-800">
      {/* Tabs + metadata */}
      <div className="flex items-center border-b border-slate-800 px-4">
        {watchlists.map((wl) => (
          <button
            key={wl.id}
            onClick={() => setActiveTab(wl.id)}
            className={cn(
              "px-4 py-3 text-sm font-medium border-b-2 transition-colors -mb-px",
              currentId === wl.id
                ? "border-blue-500 text-blue-400"
                : "border-transparent text-slate-500 hover:text-slate-300"
            )}
          >
            {wl.name}
          </button>
        ))}
        {currentWl && (
          <div className="ml-4 text-xs text-slate-600 hidden sm:block">
            Seuil signal : <span className="text-slate-400">{currentWl.signal_threshold}</span>
            {" · "}Rafraîchi toutes les <span className="text-slate-400">{currentWl.refresh_interval_minutes} min</span>
          </div>
        )}
        <button className="ml-auto p-2 text-slate-600 hover:text-slate-300 transition-colors" title="Ajouter un actif">
          <Plus className="w-4 h-4" />
        </button>
      </div>

      {/* Contenu */}
      <div className="p-4">
        {currentId && (
          <WatchlistTab
            key={currentId}
            watchlistId={currentId}
            threshold={currentWl?.signal_threshold ?? 70}
          />
        )}
      </div>
    </div>
  );
}
