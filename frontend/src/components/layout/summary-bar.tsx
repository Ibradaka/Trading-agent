"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { TrendingUp, TrendingDown, Activity } from "lucide-react";

export function SummaryBar() {
  const { data: signals = [] } = useQuery({
    queryKey: ["signals-active"],
    queryFn: api.signals.active,
    refetchInterval: 60_000,
  });

  const buyCount = signals.filter((s) => s.signal_type === "BUY").length;
  const sellCount = signals.filter((s) => s.signal_type === "SELL").length;

  return (
    <div className="flex items-center gap-6 px-4 py-2.5 bg-slate-900 rounded-xl border border-slate-800">
      <div className="flex items-center gap-2 text-xs text-slate-500">
        <Activity className="w-3.5 h-3.5" />
        <span>Signaux</span>
      </div>

      <div className="flex items-center gap-3">
        <div className="flex items-center gap-1.5 text-xs font-medium text-emerald-400">
          <TrendingUp className="w-3.5 h-3.5" />
          <span className="font-mono font-bold text-sm">{buyCount}</span>
          <span className="text-emerald-400/70">achat</span>
        </div>
        <span className="text-slate-700">·</span>
        <div className="flex items-center gap-1.5 text-xs font-medium text-red-400">
          <TrendingDown className="w-3.5 h-3.5" />
          <span className="font-mono font-bold text-sm">{sellCount}</span>
          <span className="text-red-400/70">vente</span>
        </div>
      </div>

      {/* Capital / P&L — Phase 2 */}
      <div className="ml-auto flex items-center gap-4 text-xs text-slate-700">
        <span>Capital</span>
        <span className="text-slate-800">—</span>
        <span>P&L du jour</span>
        <span className="text-slate-800">—</span>
        <span className="text-slate-800 italic">disponible en Phase 2</span>
      </div>
    </div>
  );
}
