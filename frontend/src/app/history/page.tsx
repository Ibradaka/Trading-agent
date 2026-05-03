"use client";

import { useEffect, useState } from "react";
import { api, SignalWithOutcome, AccuracyStats } from "@/lib/api";
import { cn } from "@/lib/utils";

function StatCard({ label, value, sub }: { label: string; value: string | null; sub?: string }) {
  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
      <p className="text-xs text-slate-500 mb-1">{label}</p>
      <p className="text-2xl font-semibold text-slate-100">{value ?? "—"}</p>
      {sub && <p className="text-xs text-slate-500 mt-1">{sub}</p>}
    </div>
  );
}

function OutcomeBadge({ outcome }: { outcome: SignalWithOutcome["outcome"] }) {
  if (!outcome) {
    return <span className="text-xs text-slate-600">En attente</span>;
  }
  const color = outcome.was_correct ? "text-emerald-400" : "text-red-400";
  const sign = (outcome.return_pct ?? 0) > 0 ? "+" : "";
  return (
    <div className="flex flex-col items-end gap-0.5">
      <span className={cn("text-sm font-medium", color)}>
        {sign}{outcome.return_pct?.toFixed(1) ?? "—"}%
      </span>
      <span className="text-xs text-slate-600">J+{outcome.days_elapsed}</span>
    </div>
  );
}

function SignalBadge({ type }: { type: string }) {
  if (type === "BUY") return <span className="px-2 py-0.5 rounded text-xs font-medium bg-emerald-900/50 text-emerald-400">BUY</span>;
  if (type === "SELL") return <span className="px-2 py-0.5 rounded text-xs font-medium bg-red-900/50 text-red-400">SELL</span>;
  return <span className="px-2 py-0.5 rounded text-xs font-medium bg-slate-800 text-slate-400">HOLD</span>;
}

function ConfidenceBadge({ label }: { label: string }) {
  const colors: Record<string, string> = {
    high: "text-blue-400",
    medium: "text-amber-400",
    low: "text-slate-500",
  };
  const conf = label ?? "low";
  return <span className={cn("text-xs", colors[conf] ?? "text-slate-500")}>{conf}</span>;
}

export default function HistoryPage() {
  const [signals, setSignals] = useState<SignalWithOutcome[]>([]);
  const [stats, setStats] = useState<AccuracyStats | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([api.signals.recent(50), api.backtest.stats()])
      .then(([sigs, st]) => {
        setSignals(sigs);
        setStats(st);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  const confidenceLabel = (confidence: number) =>
    confidence >= 0.70 ? "high" : confidence >= 0.45 ? "medium" : "low";

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <p className="text-slate-500 text-sm">Chargement…</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-slate-100">Historique des signaux</h1>
        <p className="text-sm text-slate-500 mt-1">Tracking de la performance et de l'accuracy</p>
      </div>

      {/* Stats globales */}
      {stats && stats.total_signals_tracked > 0 ? (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatCard
            label="Accuracy globale"
            value={stats.global_accuracy_pct != null ? `${stats.global_accuracy_pct}%` : null}
            sub={`${stats.total_signals_tracked} signaux trackés`}
          />
          <StatCard
            label="Accuracy BUY"
            value={stats.buy_accuracy_pct != null ? `${stats.buy_accuracy_pct}%` : null}
          />
          <StatCard
            label="Accuracy SELL"
            value={stats.sell_accuracy_pct != null ? `${stats.sell_accuracy_pct}%` : null}
          />
          <StatCard
            label="Retour moyen"
            value={stats.avg_return_all_pct != null ? `${stats.avg_return_all_pct > 0 ? "+" : ""}${stats.avg_return_all_pct}%` : null}
            sub="Tous signaux"
          />
        </div>
      ) : (
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
          <p className="text-sm text-slate-500">
            Aucun outcome disponible — les premiers résultats apparaîtront à J+5 après les premiers signaux.
          </p>
          {stats?.calibration && (
            <div className="mt-3 grid grid-cols-2 gap-4">
              <div>
                <p className="text-xs text-slate-500">High confidence</p>
                <p className="text-sm text-slate-300">
                  {stats.calibration.high_confidence.accuracy_pct != null
                    ? `${stats.calibration.high_confidence.accuracy_pct}% (${stats.calibration.high_confidence.n})`
                    : "—"}
                </p>
              </div>
              <div>
                <p className="text-xs text-slate-500">Medium confidence</p>
                <p className="text-sm text-slate-300">
                  {stats.calibration.medium_confidence.accuracy_pct != null
                    ? `${stats.calibration.medium_confidence.accuracy_pct}% (${stats.calibration.medium_confidence.n})`
                    : "—"}
                </p>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Table des signaux */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
        <div className="px-4 py-3 border-b border-slate-800">
          <h2 className="text-sm font-medium text-slate-300">Signaux récents ({signals.length})</h2>
        </div>
        {signals.length === 0 ? (
          <div className="flex items-center justify-center h-32">
            <p className="text-slate-600 text-sm">Aucun signal généré pour le moment</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-800">
                  <th className="text-left px-4 py-2.5 text-xs text-slate-500 font-medium">Ticker</th>
                  <th className="text-left px-4 py-2.5 text-xs text-slate-500 font-medium">Signal</th>
                  <th className="text-right px-4 py-2.5 text-xs text-slate-500 font-medium">Score</th>
                  <th className="text-left px-4 py-2.5 text-xs text-slate-500 font-medium">Confiance</th>
                  <th className="text-left px-4 py-2.5 text-xs text-slate-500 font-medium">Date</th>
                  <th className="text-right px-4 py-2.5 text-xs text-slate-500 font-medium">Outcome</th>
                </tr>
              </thead>
              <tbody>
                {signals.map((sig) => (
                  <tr key={sig.id} className="border-b border-slate-800/50 hover:bg-slate-800/30 transition-colors">
                    <td className="px-4 py-3 font-medium text-slate-100">{sig.ticker}</td>
                    <td className="px-4 py-3"><SignalBadge type={sig.signal_type} /></td>
                    <td className="px-4 py-3 text-right text-slate-300">{sig.composite_score?.toFixed(0) ?? "—"}</td>
                    <td className="px-4 py-3">
                      <ConfidenceBadge label={confidenceLabel(sig.confidence ?? 0)} />
                    </td>
                    <td className="px-4 py-3 text-slate-500 text-xs">
                      {sig.timestamp ? new Date(sig.timestamp).toLocaleDateString("fr-FR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }) : "—"}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <OutcomeBadge outcome={sig.outcome} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
