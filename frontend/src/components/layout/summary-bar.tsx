"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { TrendingUp, TrendingDown, Activity, ShieldAlert, BellOff, WifiOff, Clock } from "lucide-react";
import { cn } from "@/lib/utils";

export function SummaryBar() {
  const { data: signals = [] } = useQuery({
    queryKey: ["signals-active"],
    queryFn: api.signals.active,
    refetchInterval: 60_000,
  });

  const { data: status } = useQuery({
    queryKey: ["system-status"],
    queryFn: api.settings.status,
    refetchInterval: 30_000,
  });

  const buyCount = signals.filter((s) => s.signal_type === "BUY").length;
  const sellCount = signals.filter((s) => s.signal_type === "SELL").length;

  const alerts: { icon: React.ElementType; label: string; color: string }[] = [];

  if (status?.panic_mode) {
    alerts.push({ icon: ShieldAlert, label: "Mode sécurité actif", color: "text-red-400" });
  }
  if (status && !status.telegram_enabled) {
    alerts.push({ icon: BellOff, label: "Alertes Telegram suspendues", color: "text-amber-400" });
  }
  if (status && !status.macro_available) {
    alerts.push({ icon: WifiOff, label: "Données macro en cache expiré", color: "text-slate-500" });
  }
  if (status && !status.sentiment_available) {
    alerts.push({ icon: Clock, label: "Sentiment en attente", color: "text-slate-500" });
  }

  return (
    <div className="space-y-2">
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

        {alerts.length > 0 && (
          <div className="ml-auto flex items-center gap-4">
            {alerts.map(({ icon: Icon, label, color }, i) => (
              <div key={i} className={cn("flex items-center gap-1.5 text-xs", color)}>
                <Icon className="w-3.5 h-3.5 flex-shrink-0" />
                <span>{label}</span>
              </div>
            ))}
          </div>
        )}

        {alerts.length === 0 && (
          <div className="ml-auto flex items-center gap-1.5 text-xs text-slate-600">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500/50" />
            <span>Système opérationnel</span>
          </div>
        )}
      </div>

      {status?.panic_mode && (
        <div className="flex items-center gap-2 px-4 py-2 bg-red-900/20 border border-red-800/50 rounded-xl text-xs text-red-400 animate-pulse">
          <ShieldAlert className="w-3.5 h-3.5 flex-shrink-0" />
          <span>Mode sécurité activé — aucune alerte Telegram envoyée</span>
        </div>
      )}
    </div>
  );
}
