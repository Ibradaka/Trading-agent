"use client";

import { useQuery } from "@tanstack/react-query";
import { api, type WatchlistSignalEntry } from "@/lib/api";
import { useState } from "react";
import { Plus, Loader2 } from "lucide-react";
import Link from "next/link";
import { cn, signalLabel, scoreToColor, formatScore } from "@/lib/utils";
import { useSSE } from "@/lib/sse";
import { useQueryClient } from "@tanstack/react-query";

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

function AssetRow({ entry }: { entry: WatchlistSignalEntry }) {
  const { ticker, name, is_pea_eligible, signal } = entry;

  return (
    <Link
      href={`/asset/${ticker}`}
      className="flex items-center gap-4 px-4 py-3 hover:bg-slate-800/50 rounded-lg transition-colors group"
    >
      {/* Ticker + nom */}
      <div className="w-32 flex-shrink-0">
        <p className="text-sm font-medium text-slate-100 group-hover:text-blue-400 transition-colors">{ticker}</p>
        <p className="text-xs text-slate-500 truncate">{name}</p>
      </div>

      {/* Badge PEA */}
      <div className="w-12 flex-shrink-0">
        {is_pea_eligible && (
          <span className="text-xs bg-blue-500/10 text-blue-400 border border-blue-500/20 px-1.5 py-0.5 rounded">
            PEA
          </span>
        )}
      </div>

      {/* Signal */}
      <div className="flex-1">
        {signal ? (
          <SignalBadge type={signal.signal_type} strength={signal.strength} />
        ) : (
          <span className="text-xs text-slate-600">—</span>
        )}
      </div>

      {/* Score */}
      <div className="w-20 text-right">
        {signal ? (
          <span className={cn("text-sm font-mono font-medium", scoreToColor(signal.composite_score))}>
            {formatScore(signal.composite_score)}
          </span>
        ) : (
          <span className="text-xs text-slate-600">—</span>
        )}
      </div>

      {/* Confiance */}
      <div className="w-16 text-right">
        {signal ? (
          <span className="text-xs text-slate-500">{Math.round(signal.confidence * 100)}%</span>
        ) : null}
      </div>
    </Link>
  );
}

function WatchlistTab({ watchlistId, threshold }: { watchlistId: string; threshold: number }) {
  const queryClient = useQueryClient();

  // SSE — invalide la query quand un signal est mis à jour
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

  // Trie par score décroissant
  const sorted = [...entries].sort((a, b) => {
    const sa = a.signal?.composite_score ?? 50;
    const sb = b.signal?.composite_score ?? 50;
    return sb - sa;
  });

  return (
    <div className="space-y-1">
      {/* En-têtes */}
      <div className="flex items-center gap-4 px-4 py-2 text-xs text-slate-600 border-b border-slate-800 mb-2">
        <span className="w-32">Actif</span>
        <span className="w-12">Type</span>
        <span className="flex-1">Signal</span>
        <span className="w-20 text-right">Score</span>
        <span className="w-16 text-right">Confiance</span>
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
        <button className="ml-auto p-2 text-slate-600 hover:text-slate-300 transition-colors">
          <Plus className="w-4 h-4" />
        </button>
      </div>

      {/* Contenu */}
      <div className="p-4">
        {currentId && (
          <WatchlistTab
            key={currentId}
            watchlistId={currentId}
            threshold={watchlists.find((w) => w.id === currentId)?.signal_threshold ?? 70}
          />
        )}
      </div>
    </div>
  );
}
