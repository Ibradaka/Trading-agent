"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, type WatchlistSignalEntry, type AssetQuote, type Position } from "@/lib/api";
import { useState, useRef, useEffect } from "react";
import { Plus, Loader2, TrendingUp, TrendingDown, Minus, X, Search } from "lucide-react";
import Link from "next/link";
import { cn, signalLabel, scoreToColor, formatScore, formatAssetPrice } from "@/lib/utils";
import { useSSE } from "@/lib/sse";
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

  const changeBadge = (val: number | null, label: string, muted = false) => {
    if (val === null) return null;
    const pos = val >= 0;
    return (
      <span
        className={cn(
          "font-mono",
          muted
            ? pos ? "text-emerald-400/60" : "text-red-400/60"
            : pos ? "text-emerald-400" : "text-red-400"
        )}
      >
        {label}:{pos ? "+" : ""}{val.toFixed(1)}%
      </span>
    );
  };

  return (
    <div className="flex items-center gap-3">
      {/* Prix + variations multi-timeframe */}
      <div className="min-w-[110px]">
        <p className="text-sm font-mono font-semibold text-slate-100">
          {formatAssetPrice(quote.current_price, quote.currency)}
        </p>
        <div className="flex items-center gap-1.5 text-xs mt-0.5 flex-wrap">
          <span className={cn("flex items-center gap-0.5 font-medium font-mono", positive ? "text-emerald-400" : "text-red-400")}>
            {positive ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
            {quote.change_pct !== null ? `${positive ? "+" : ""}${quote.change_pct.toFixed(2)}%` : "—"}
          </span>
          {changeBadge(quote.week_change_pct, "1S", true)}
          {changeBadge(quote.month_change_pct, "1M", true)}
        </div>
      </div>

      {/* Sparkline 1 mois */}
      {sparkData.length > 1 && (
        <div className="hidden lg:block">
          <Sparkline data={sparkData} positive={positive} />
        </div>
      )}
    </div>
  );
}

function PnLCell({ ticker, position }: { ticker: string; position: Position | undefined }) {
  const { data: quote } = useQuery<AssetQuote>({
    queryKey: ["quote", ticker],
    queryFn: () => api.assets.quote(ticker),
    staleTime: 30_000,
    enabled: !!position,
  });

  if (!position || !quote?.current_price) return <span className="text-slate-700 text-xs">—</span>;

  const isGBp = quote.currency === "GBp";
  const current = isGBp ? quote.current_price / 100 : quote.current_price;
  const avg = isGBp ? position.avg_price / 100 : position.avg_price;
  const pnl = (current - avg) * position.quantity;
  const pnl_pct = avg > 0 ? ((current - avg) / avg) * 100 : 0;
  const positive = pnl >= 0;

  return (
    <div>
      <p className={cn("text-sm font-mono font-semibold", positive ? "text-emerald-400" : "text-red-400")}>
        {positive ? "+" : ""}{pnl.toFixed(2)}
      </p>
      <p className={cn("text-xs font-mono", positive ? "text-emerald-400/70" : "text-red-400/70")}>
        {positive ? "+" : ""}{pnl_pct.toFixed(2)}%
      </p>
    </div>
  );
}

function AssetRow({
  entry,
  position,
  watchlistId,
  onRemove,
}: {
  entry: WatchlistSignalEntry;
  position: Position | undefined;
  watchlistId: string;
  onRemove: (ticker: string) => void;
}) {
  const { ticker, name, is_pea_eligible, asset_type, signal } = entry;

  return (
    <div className="relative flex items-center gap-3 px-4 py-3 hover:bg-slate-800/50 rounded-lg transition-colors group">
      <Link href={`/asset/${ticker}`} className="absolute inset-0 rounded-lg" />

      {/* Ticker + nom */}
      <div className="w-28 flex-shrink-0 relative z-10">
        <p className="text-sm font-semibold text-slate-100 group-hover:text-blue-400 transition-colors">{ticker}</p>
        <p className="text-xs text-slate-500 truncate max-w-[112px]">{name}</p>
      </div>

      {/* Badges */}
      <div className="flex gap-1 flex-shrink-0 w-16 relative z-10">
        {is_pea_eligible && (
          <span className="text-xs bg-blue-500/10 text-blue-400 border border-blue-500/20 px-1.5 py-0.5 rounded">
            PEA
          </span>
        )}
      </div>

      {/* Prix + sparkline */}
      <div className="flex-1 relative z-10">
        <PriceCell ticker={ticker} />
      </div>

      {/* P&L si position ouverte */}
      <div className="w-24 flex-shrink-0 text-right relative z-10">
        <PnLCell ticker={ticker} position={position} />
      </div>

      {/* Signal */}
      <div className="w-28 flex-shrink-0 text-center relative z-10">
        {signal ? (
          <SignalBadge type={signal.signal_type} strength={signal.strength} />
        ) : (
          <span className="text-xs text-slate-600">En attente</span>
        )}
      </div>

      {/* Score */}
      <div className="w-16 text-right flex-shrink-0 relative z-10">
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

      {/* Bouton supprimer — visible au survol */}
      <button
        onClick={(e) => { e.preventDefault(); e.stopPropagation(); onRemove(ticker); }}
        className="relative z-10 opacity-0 group-hover:opacity-100 transition-opacity ml-1 p-1 text-slate-600 hover:text-red-400 hover:bg-red-900/20 rounded"
        title="Retirer de la watchlist"
      >
        <X className="w-3.5 h-3.5" />
      </button>
    </div>
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

  const { data: positions = [] } = useQuery({
    queryKey: ["positions"],
    queryFn: api.portfolio.positions,
    staleTime: 60_000,
  });

  const removeMutation = useMutation({
    mutationFn: (ticker: string) => api.watchlists.removeAsset(watchlistId, ticker),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["watchlist-signals", watchlistId] }),
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
        <span className="w-16"></span>
        <span className="flex-1">Prix · 1J / 1S / 1M</span>
        <span className="w-24 text-right">P&L position</span>
        <span className="w-28 text-center">Signal</span>
        <span className="w-16 text-right">Score</span>
      </div>
      {sorted.map((entry) => (
        <AssetRow
          key={entry.ticker}
          entry={entry}
          position={positions.find((p) => p.ticker === entry.ticker && p.is_active)}
          watchlistId={watchlistId}
          onRemove={(ticker) => removeMutation.mutate(ticker)}
        />
      ))}
    </div>
  );
}

function AddAssetModal({ watchlistId, onClose }: { watchlistId: string; onClose: () => void }) {
  const qc = useQueryClient();
  const [ticker, setTicker] = useState("");
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => { inputRef.current?.focus(); }, []);

  const mutation = useMutation({
    mutationFn: async (t: string) => {
      const res = await api.assets.validateAndAdd(t);
      if ("error" in res && res.error) throw new Error(res.error as string);
      return api.watchlists.addAsset(watchlistId, t);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["watchlist-signals", watchlistId] });
      onClose();
    },
    onError: (e: Error) => setError(
      e.message.includes("not found") || e.message.includes("No market data")
        ? "Ticker introuvable. Vérifiez le suffixe (ex: SOI.PA, MC.PA pour les valeurs françaises)"
        : e.message || "Ticker invalide ou déjà présent"
    ),
  });

  const submit = () => {
    const t = ticker.trim().toUpperCase();
    if (!t) return;
    setError(null);
    mutation.mutate(t);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" onClick={onClose}>
      <div className="bg-slate-900 border border-slate-700 rounded-xl p-5 w-80 shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-medium text-slate-200">Ajouter un actif</h3>
          <button onClick={onClose} className="text-slate-500 hover:text-slate-300 transition-colors">
            <X className="w-4 h-4" />
          </button>
        </div>
        <div className="flex gap-2">
          <div className="relative flex-1">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-500" />
            <input
              ref={inputRef}
              className="w-full bg-slate-800 border border-slate-700 rounded-lg pl-8 pr-3 py-2 text-sm text-slate-100 focus:outline-none focus:border-blue-500 transition-colors uppercase"
              placeholder="NVDA, AAPL…"
              value={ticker}
              onChange={(e) => setTicker(e.target.value.toUpperCase())}
              onKeyDown={(e) => e.key === "Enter" && submit()}
            />
          </div>
          <button
            onClick={submit}
            disabled={mutation.isPending || !ticker.trim()}
            className="px-3 py-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-sm rounded-lg transition-colors"
          >
            {mutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : "Ajouter"}
          </button>
        </div>
        {error && <p className="mt-2 text-xs text-red-400">{error}</p>}
        <p className="mt-2 text-xs text-slate-600">
          Suffixes : <span className="text-slate-500">.PA</span> France · <span className="text-slate-500">.L</span> Londres · <span className="text-slate-500">.DE</span> Allemagne · <span className="text-slate-500">.MI</span> Italie
        </p>
      </div>
    </div>
  );
}

export function WatchlistPanel() {
  const [activeTab, setActiveTab] = useState<string | null>(null);
  const [showAddModal, setShowAddModal] = useState(false);

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
        <button
          className="ml-auto p-2 text-slate-600 hover:text-slate-300 transition-colors"
          title="Ajouter un actif"
          onClick={() => setShowAddModal(true)}
        >
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

      {showAddModal && currentId && (
        <AddAssetModal watchlistId={currentId} onClose={() => setShowAddModal(false)} />
      )}
    </div>
  );
}
