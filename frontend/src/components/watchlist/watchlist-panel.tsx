"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, type WatchlistSignalEntry, type AssetQuote, type Position, type AgentStatus } from "@/lib/api";
import { useState, useRef, useEffect } from "react";
import { Plus, Loader2, TrendingUp, TrendingDown, X, Search } from "lucide-react";
import Link from "next/link";
import { cn, signalLabel, formatAssetPrice } from "@/lib/utils";
import { useSSE } from "@/lib/sse";
import { LineChart, Line, ResponsiveContainer, Tooltip } from "recharts";

// ─── Helpers ────────────────────────────────────────────────────────────────

function fmtAgo(iso: string | undefined): string {
  if (!iso) return "";
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return "à l'instant";
  if (diff < 3600) return `il y a ${Math.floor(diff / 60)} min`;
  if (diff < 86400) return `il y a ${Math.floor(diff / 3600)} h`;
  return `il y a ${Math.floor(diff / 86400)} j`;
}

const PROFILE_LABELS: Record<string, { label: string; color: string }> = {
  robust:       { label: "Robuste",   color: "text-emerald-400/70" },
  noisy:        { label: "Bruité",    color: "text-amber-400/70" },
  over_traded:  { label: "Sur-tradé", color: "text-orange-400/70" },
  unstable:     { label: "Instable",  color: "text-red-400/70" },
  bearish_asset:{ label: "Baissier",  color: "text-red-400/70" },
  mixed:        { label: "Mixte",     color: "text-slate-400/70" },
  unknown:      { label: "Inconnu",   color: "text-slate-600" },
};

const SIGNAL_CONFIG: Record<string, { border: string; bg: string; badge: string; text: string; dot: string }> = {
  "ACHAT FORT": {
    border: "border-l-emerald-500",
    bg: "bg-emerald-500/5",
    badge: "bg-emerald-500/20 border-emerald-500/40 text-emerald-300",
    text: "text-emerald-400",
    dot: "bg-emerald-500",
  },
  "ACHAT": {
    border: "border-l-emerald-400/60",
    bg: "bg-emerald-500/3",
    badge: "bg-emerald-500/10 border-emerald-500/20 text-emerald-400",
    text: "text-emerald-400",
    dot: "bg-emerald-400",
  },
  "NEUTRE": {
    border: "border-l-slate-600",
    bg: "",
    badge: "bg-slate-700/50 border-slate-600/50 text-slate-400",
    text: "text-slate-400",
    dot: "bg-slate-500",
  },
  "VENTE": {
    border: "border-l-red-400/60",
    bg: "bg-red-500/3",
    badge: "bg-red-500/10 border-red-500/20 text-red-400",
    text: "text-red-400",
    dot: "bg-red-400",
  },
  "VENTE FORTE": {
    border: "border-l-red-500",
    bg: "bg-red-500/5",
    badge: "bg-red-500/20 border-red-500/40 text-red-300",
    text: "text-red-400",
    dot: "bg-red-500",
  },
};

// ─── Sparkline ───────────────────────────────────────────────────────────────

function Sparkline({ data, positive }: { data: { v: number }[]; positive: boolean }) {
  return (
    <ResponsiveContainer width={72} height={28}>
      <LineChart data={data} margin={{ top: 2, right: 2, bottom: 2, left: 2 }}>
        <Line type="monotone" dataKey="v" stroke={positive ? "#10b981" : "#ef4444"} strokeWidth={1.5} dot={false} isAnimationActive={false} />
        <Tooltip content={() => null} cursor={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}

// ─── Score arc SVG ───────────────────────────────────────────────────────────

function ScoreArc({ score }: { score: number }) {
  const r = 18;
  const circ = Math.PI * r; // demi-cercle
  const pct = Math.max(0, Math.min(100, score)) / 100;
  const dash = pct * circ;
  const color = score >= 65 ? "#10b981" : score >= 50 ? "#f59e0b" : score >= 40 ? "#64748b" : "#ef4444";

  return (
    <svg width={44} height={26} viewBox="0 0 44 26">
      {/* Track */}
      <path
        d="M 4 24 A 18 18 0 0 1 40 24"
        fill="none" stroke="#1e293b" strokeWidth={4} strokeLinecap="round"
      />
      {/* Fill */}
      <path
        d="M 4 24 A 18 18 0 0 1 40 24"
        fill="none" stroke={color} strokeWidth={4} strokeLinecap="round"
        strokeDasharray={`${dash} ${circ}`}
        style={{ transition: "stroke-dasharray 0.5s ease" }}
      />
      <text x="22" y="20" textAnchor="middle" fontSize="9" fontWeight="700" fill={color} fontFamily="monospace">
        {Math.round(score)}
      </text>
    </svg>
  );
}

// ─── Agents dots ─────────────────────────────────────────────────────────────

const AGENT_KEYS = ["market_data", "technical", "patterns", "sentiment", "macro", "risk_score", "llm"];

function AgentsDots({ agents }: { agents: AgentStatus[] }) {
  const agentMap = Object.fromEntries(agents.map((a) => [a.id, a]));
  const ok = AGENT_KEYS.filter((k) => {
    const a = agentMap[k];
    return a && a.status === "ok" && a.elapsed_seconds !== null && a.elapsed_seconds < 7200;
  }).length;
  const total = AGENT_KEYS.length;
  const color = ok === total ? "text-emerald-400" : ok >= 5 ? "text-amber-400" : "text-red-400";

  return (
    <div className="flex flex-col items-center gap-0.5">
      <div className="flex gap-0.5">
        {AGENT_KEYS.map((k) => {
          const a = agentMap[k];
          const isOk = a && a.status === "ok" && a.elapsed_seconds !== null && a.elapsed_seconds < 7200;
          const isErr = a && a.status === "error";
          return (
            <span
              key={k}
              title={a ? `${a.label} — ${a.ago}` : k}
              className={cn(
                "w-1.5 h-1.5 rounded-full",
                isOk ? "bg-emerald-500" : isErr ? "bg-red-500" : "bg-slate-700"
              )}
            />
          );
        })}
      </div>
      <span className={cn("text-[9px] font-semibold tabular-nums", color)}>
        {ok}/{total}
      </span>
    </div>
  );
}

// ─── AssetCard ───────────────────────────────────────────────────────────────

function AssetCard({
  entry,
  position,
  agents,
  watchlistId,
  onRemove,
}: {
  entry: WatchlistSignalEntry;
  position: Position | undefined;
  agents: AgentStatus[];
  watchlistId: string;
  onRemove: (ticker: string) => void;
}) {
  const { ticker, name, signal } = entry;
  const label = signal ? signalLabel(signal.signal_type, signal.strength) : "NEUTRE";
  const cfg = SIGNAL_CONFIG[label] ?? SIGNAL_CONFIG["NEUTRE"];

  const { data: quote } = useQuery<AssetQuote>({
    queryKey: ["quote", ticker],
    queryFn: () => api.assets.quote(ticker),
    refetchInterval: 60_000,
    staleTime: 30_000,
  });

  const positive = (quote?.change_pct ?? 0) >= 0;
  const sparkData = (quote?.history ?? []).map((b) => ({ v: b.close }));
  const price = quote?.current_price ? formatAssetPrice(quote.current_price, quote.currency) : "—";

  // P&L
  let pnl: number | null = null;
  let pnl_pct: number | null = null;
  if (position && quote?.current_price) {
    const isGBp = quote.currency === "GBp";
    const cur = isGBp ? quote.current_price / 100 : quote.current_price;
    const avg = isGBp ? position.avg_price / 100 : position.avg_price;
    pnl = (cur - avg) * position.quantity;
    pnl_pct = avg > 0 ? ((cur - avg) / avg) * 100 : 0;
  }

  return (
    <div className={cn(
      "relative group rounded-xl border border-slate-800 border-l-4 bg-slate-900 transition-all duration-200 hover:border-slate-700 hover:shadow-lg hover:shadow-black/20",
      cfg.border,
      cfg.bg,
    )}>
      {/* Lien transparent sur toute la card */}
      <Link href={`/asset/${ticker}`} className="absolute inset-0 rounded-xl z-0" />

      <div className="relative z-10 flex items-center gap-3 px-4 py-2.5">

        {/* Colonne 1 : Ticker + nom */}
        <div className="w-28 flex-shrink-0">
          <p className="text-sm font-bold text-slate-100 group-hover:text-blue-400 transition-colors leading-tight">
            {ticker}
          </p>
          <p className="text-xs text-slate-500 truncate mt-0.5" title={name}>{name}</p>
        </div>

        {/* Colonne 2 : Prix + variations + sparkline */}
        <div className="flex-1 min-w-0">
          {quote ? (
            <div className="flex items-center gap-3">
              <div>
                <p className="text-sm font-mono font-semibold text-slate-100 leading-tight">{price}</p>
                <div className="flex items-center gap-1.5 mt-0.5 text-[11px] flex-wrap">
                  <span className={cn("flex items-center gap-0.5 font-medium font-mono", positive ? "text-emerald-400" : "text-red-400")}>
                    {positive ? <TrendingUp className="w-2.5 h-2.5" /> : <TrendingDown className="w-2.5 h-2.5" />}
                    {quote.change_pct !== null ? `${positive ? "+" : ""}${quote.change_pct.toFixed(2)}%` : "—"}
                  </span>
                  {quote.week_change_pct !== null && (
                    <span className={cn("font-mono", quote.week_change_pct >= 0 ? "text-emerald-400/60" : "text-red-400/60")}>
                      1S:{quote.week_change_pct >= 0 ? "+" : ""}{quote.week_change_pct.toFixed(1)}%
                    </span>
                  )}
                  {quote.month_change_pct !== null && (
                    <span className={cn("font-mono", quote.month_change_pct >= 0 ? "text-emerald-400/60" : "text-red-400/60")}>
                      1M:{quote.month_change_pct >= 0 ? "+" : ""}{quote.month_change_pct.toFixed(1)}%
                    </span>
                  )}
                </div>
              </div>
              {sparkData.length > 1 && (
                <div className="hidden lg:block opacity-70">
                  <Sparkline data={sparkData} positive={positive} />
                </div>
              )}
            </div>
          ) : (
            <div className="space-y-1.5">
              <div className="w-20 h-4 bg-slate-800 rounded animate-pulse" />
              <div className="w-32 h-3 bg-slate-800 rounded animate-pulse" />
            </div>
          )}
        </div>

        {/* Colonne 3 : P&L */}
        <div className="w-20 flex-shrink-0 text-right hidden md:block">
          {pnl !== null && pnl_pct !== null ? (
            <>
              <p className={cn("text-sm font-mono font-semibold leading-tight", pnl >= 0 ? "text-emerald-400" : "text-red-400")}>
                {pnl >= 0 ? "+" : ""}{pnl.toFixed(0)}
              </p>
              <p className={cn("text-[11px] font-mono", pnl >= 0 ? "text-emerald-400/70" : "text-red-400/70")}>
                {pnl >= 0 ? "+" : ""}{pnl_pct.toFixed(1)}%
              </p>
            </>
          ) : (
            <span className="text-slate-700 text-xs">—</span>
          )}
        </div>

        {/* Colonne 4 : Score arc + badge signal */}
        <div className="flex items-center gap-3 flex-shrink-0">
          {signal ? (
            <>
              <div className="flex flex-col items-center gap-0.5">
                <ScoreArc score={signal.composite_score} />
                {(() => {
                  const prof = PROFILE_LABELS[signal.asset_label ?? "unknown"] ?? PROFILE_LABELS.unknown;
                  return signal.asset_label && signal.asset_label !== "unknown" ? (
                    <span className={cn("text-[9px] font-medium leading-none", prof.color)}>
                      {prof.label}
                    </span>
                  ) : null;
                })()}
              </div>
              <div className={cn("px-2.5 py-1.5 rounded-lg border text-center min-w-[90px]", cfg.badge)}>
                <p className="text-xs font-bold leading-tight tracking-wide">{label}</p>
                <p className="text-[10px] opacity-80">
                  {signal.confidence != null ? `${Math.round(signal.confidence * 100)}% confiance` : "—"}
                </p>
                <p className="text-[9px] opacity-50">{fmtAgo(signal.timestamp)}</p>
              </div>
            </>
          ) : (
            <>
              <ScoreArc score={50} />
              <div className="px-2.5 py-1.5 rounded-lg border border-slate-700/50 bg-slate-800/30 text-center min-w-[90px]">
                <p className="text-xs text-slate-500 font-medium">En attente</p>
                <p className="text-[9px] text-slate-600">Prochain cycle</p>
              </div>
            </>
          )}
        </div>

        {/* Colonne 5 : Agents dots */}
        <div className="flex-shrink-0 hidden lg:block">
          <AgentsDots agents={agents} />
        </div>

        {/* Bouton supprimer */}
        <button
          onClick={(e) => { e.preventDefault(); e.stopPropagation(); onRemove(ticker); }}
          className="flex-shrink-0 opacity-0 group-hover:opacity-100 transition-opacity p-1.5 text-slate-600 hover:text-red-400 hover:bg-red-900/20 rounded-lg"
          title="Retirer de la watchlist"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  );
}

// ─── WatchlistTab ─────────────────────────────────────────────────────────────

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

  const { data: agents = [] } = useQuery({
    queryKey: ["agents-status"],
    queryFn: api.agents.status,
    refetchInterval: 60_000,
    staleTime: 30_000,
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
    const order = { BUY: 0, SELL: 1, HOLD: 2 };
    const ta = order[a.signal?.signal_type as keyof typeof order] ?? 2;
    const tb = order[b.signal?.signal_type as keyof typeof order] ?? 2;
    if (ta !== tb) return ta - tb;
    return (b.signal?.composite_score ?? 50) - (a.signal?.composite_score ?? 50);
  });

  return (
    <div className="space-y-1.5">
      {sorted.map((entry) => (
        <AssetCard
          key={entry.ticker}
          entry={entry}
          position={positions.find((p) => p.ticker === entry.ticker && p.is_active)}
          agents={agents}
          watchlistId={watchlistId}
          onRemove={(ticker) => removeMutation.mutate(ticker)}
        />
      ))}
    </div>
  );
}

// ─── AddAssetModal ────────────────────────────────────────────────────────────

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

// ─── WatchlistPanel ───────────────────────────────────────────────────────────

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
    <div className="bg-slate-900/50 rounded-xl border border-slate-800">
      {/* Tabs */}
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
