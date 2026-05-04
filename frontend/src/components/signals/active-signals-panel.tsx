"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type Signal } from "@/lib/api";
import Link from "next/link";
import { cn, scoreToColor, formatScore } from "@/lib/utils";
import { Loader2, TrendingUp, TrendingDown, Minus, RefreshCw } from "lucide-react";
import { useState } from "react";

export function ActiveSignalsPanel() {
  const queryClient = useQueryClient();
  const [refreshing, setRefreshing] = useState(false);

  const { data: recent = [], isLoading } = useQuery({
    queryKey: ["signals-top"],
    queryFn: api.signals.top,
    refetchInterval: 60_000,
  });

  async function handleRefresh() {
    setRefreshing(true);
    try {
      await api.settings.refresh();
      setTimeout(() => {
        queryClient.invalidateQueries({ queryKey: ["signals-top"] });
        queryClient.invalidateQueries({ queryKey: ["signals-active"] });
        setRefreshing(false);
      }, 5000);
    } catch {
      setRefreshing(false);
    }
  }

  return (
    <div className="bg-slate-900 rounded-xl border border-slate-800">
      <div className="px-4 py-3 border-b border-slate-800 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-slate-200">Alertes récentes</h2>
        <div className="flex items-center gap-2">
          {recent.length > 0 && (
            <span className="text-xs text-slate-500">{recent.length}</span>
          )}
          <button
            onClick={handleRefresh}
            disabled={refreshing}
            className="p-1 rounded hover:bg-slate-800 transition-colors disabled:opacity-40"
            title="Forcer un cycle de scoring"
          >
            <RefreshCw className={cn("w-3.5 h-3.5 text-slate-500", refreshing && "animate-spin")} />
          </button>
        </div>
      </div>

      {isLoading ? (
        <div className="flex justify-center py-8">
          <Loader2 className="w-5 h-5 text-slate-600 animate-spin" />
        </div>
      ) : recent.length === 0 ? (
        <div className="px-4 py-10 text-center">
          <p className="text-sm text-slate-600">Aucune donnée</p>
        </div>
      ) : (
        <div className="divide-y divide-slate-800/60">
          {recent.map((s: Signal) => (
            <Link
              key={s.ticker}
              href={`/asset/${s.ticker}`}
              className="flex items-center gap-3 px-4 py-3 hover:bg-slate-800/50 transition-colors group"
            >
              <div
                className={cn(
                  "w-1.5 h-10 rounded-full flex-shrink-0",
                  s.signal_type === "BUY" ? "bg-emerald-500/70" :
                  s.signal_type === "SELL" ? "bg-red-500/70" : "bg-slate-600/50"
                )}
              />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold text-slate-200 group-hover:text-blue-400 transition-colors">
                  {s.ticker}
                </p>
                <p className="text-[10px] text-slate-600">{s.asset_label ?? "—"}</p>
              </div>
              <div className="text-right">
                <p className={cn("text-sm font-mono font-bold", scoreToColor(s.composite_score))}>
                  {formatScore(s.composite_score)}
                </p>
                <div
                  className={cn(
                    "flex items-center justify-end gap-0.5 text-xs font-medium",
                    s.signal_type === "BUY" ? "text-emerald-400" :
                    s.signal_type === "SELL" ? "text-red-400" : "text-slate-500"
                  )}
                >
                  {s.signal_type === "BUY" ? <TrendingUp className="w-3 h-3" /> :
                   s.signal_type === "SELL" ? <TrendingDown className="w-3 h-3" /> :
                   <Minus className="w-3 h-3" />}
                  <span>{s.signal_type}</span>
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
