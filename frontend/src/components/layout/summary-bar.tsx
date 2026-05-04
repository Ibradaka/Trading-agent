"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, AgentStatus } from "@/lib/api";
import { TrendingUp, TrendingDown, Activity, ShieldAlert, BellOff, WifiOff, Clock } from "lucide-react";
import { cn } from "@/lib/utils";

// Max freshness threshold per agent (seconds) — aligned with their actual run cycles
const AGENT_MAX_AGE: Record<string, number> = {
  market_data: 45 * 60,   // 15min cycle → ok if < 45min
  technical:   45 * 60,
  patterns:    45 * 60,
  risk_score:  45 * 60,
  llm:         45 * 60,
  sentiment:   5 * 3600,  // 4h cycle → ok if < 5h
  macro:       7 * 3600,  // 6h cycle → ok if < 7h
};

function AgentDot({ agent }: { agent: AgentStatus }) {
  const [open, setOpen] = useState(false);

  const maxAge = AGENT_MAX_AGE[agent.id] ?? 1800;
  const dotColor =
    agent.status === "ok" && agent.elapsed_seconds !== null && agent.elapsed_seconds < maxAge
      ? "bg-emerald-500"
      : agent.status === "error"
      ? "bg-red-500"
      : "bg-slate-600";

  return (
    <div className="relative" onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}>
      <button className="flex items-center gap-1 group">
        <span className={cn("w-2 h-2 rounded-full flex-shrink-0", dotColor)} />
        <span className="text-xs text-slate-500 group-hover:text-slate-300 transition-colors hidden sm:inline">
          {agent.label}
        </span>
      </button>

      {open && (
        <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 z-50 w-48 bg-slate-800 border border-slate-700 rounded-lg shadow-xl p-3 pointer-events-none">
          <div className="flex items-center gap-2 mb-1.5">
            <span className={cn("w-2 h-2 rounded-full flex-shrink-0", dotColor)} />
            <span className="text-xs font-semibold text-slate-200">{agent.label}</span>
          </div>
          <p className="text-xs text-slate-400">{agent.ago}</p>
          <p className="text-xs text-slate-500 mt-0.5 truncate">{agent.result}</p>
          {/* flèche */}
          <div className="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-slate-700" />
        </div>
      )}
    </div>
  );
}

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

  const { data: agents = [] } = useQuery({
    queryKey: ["agents-status"],
    queryFn: api.agents.status,
    refetchInterval: 60_000,
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
      <div className="flex items-center gap-4 px-4 py-2.5 bg-slate-900 rounded-xl border border-slate-800 flex-wrap">
        {/* Signaux */}
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

        {/* Séparateur */}
        {agents.length > 0 && <span className="text-slate-700 hidden sm:inline">|</span>}

        {/* Agents */}
        {agents.length > 0 && (
          <div className="flex items-center gap-3">
            <span className="text-xs text-slate-600 hidden sm:inline">Agents</span>
            {agents.map((agent) => (
              <AgentDot key={agent.id} agent={agent} />
            ))}
          </div>
        )}

        {/* Alertes système */}
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
