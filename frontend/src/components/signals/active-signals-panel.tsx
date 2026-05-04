"use client";

import { useQuery } from "@tanstack/react-query";
import { api, type SignalWithOutcome } from "@/lib/api";
import Link from "next/link";
import { cn, signalLabel, scoreToColor, formatScore } from "@/lib/utils";
import { Loader2, TrendingUp, TrendingDown, Clock } from "lucide-react";

function timeAgo(ts: string): string {
  const diff = Math.floor((Date.now() - new Date(ts).getTime()) / 1000);
  if (diff < 60) return "à l'instant";
  if (diff < 3600) return `il y a ${Math.floor(diff / 60)} min`;
  if (diff < 86400) return `il y a ${Math.floor(diff / 3600)}h`;
  return `il y a ${Math.floor(diff / 86400)}j`;
}

export function ActiveSignalsPanel() {
  const { data: signals = [], isLoading } = useQuery({
    queryKey: ["signals-active"],
    queryFn: api.signals.active,
    refetchInterval: 60_000,
  });

  const recent = signals.filter((s) => s.signal_type !== "HOLD").slice(0, 5);

  return (
    <div className="bg-slate-900 rounded-xl border border-slate-800">
      <div className="px-4 py-3 border-b border-slate-800 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-slate-200">Alertes récentes</h2>
        {recent.length > 0 && (
          <span className="text-xs text-slate-500">{recent.length}</span>
        )}
      </div>

      {isLoading ? (
        <div className="flex justify-center py-8">
          <Loader2 className="w-5 h-5 text-slate-600 animate-spin" />
        </div>
      ) : recent.length === 0 ? (
        <div className="px-4 py-10 text-center">
          <p className="text-sm text-slate-600">Aucune alerte récente</p>
          <p className="text-xs text-slate-700 mt-1">Les BUY/SELL apparaîtront ici</p>
        </div>
      ) : (
        <div className="divide-y divide-slate-800/60">
          {recent.map((s: SignalWithOutcome) => (
            <Link
              key={s.id}
              href={`/asset/${s.ticker}`}
              className="flex items-center gap-3 px-4 py-3 hover:bg-slate-800/50 transition-colors group"
            >
              <div
                className={cn(
                  "w-1.5 h-10 rounded-full flex-shrink-0",
                  s.signal_type === "BUY" ? "bg-emerald-500" : "bg-red-500"
                )}
              />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold text-slate-200 group-hover:text-blue-400 transition-colors">
                  {s.ticker}
                </p>
                <div className="flex items-center gap-1 mt-0.5">
                  <Clock className="w-2.5 h-2.5 text-slate-600" />
                  <span className="text-[10px] text-slate-600">
                    {s.timestamp ? timeAgo(s.timestamp) : "—"}
                  </span>
                </div>
              </div>
              <div className="text-right">
                <p className={cn("text-sm font-mono font-bold", scoreToColor(s.composite_score))}>
                  {formatScore(s.composite_score)}
                </p>
                <div
                  className={cn(
                    "flex items-center justify-end gap-0.5 text-xs font-medium",
                    s.signal_type === "BUY" ? "text-emerald-400" : "text-red-400"
                  )}
                >
                  {s.signal_type === "BUY"
                    ? <TrendingUp className="w-3 h-3" />
                    : <TrendingDown className="w-3 h-3" />}
                  {signalLabel(s.signal_type, s.strength)}
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
