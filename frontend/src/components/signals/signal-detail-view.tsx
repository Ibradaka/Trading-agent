"use client";

import { useQuery } from "@tanstack/react-query";
import { api, type Signal } from "@/lib/api";
import { Loader2, AlertTriangle, TrendingUp, TrendingDown, Minus } from "lucide-react";
import { cn, scoreToColor, signalLabel, formatScore } from "@/lib/utils";
import { TradingViewChart } from "@/components/charts/trading-view-chart";
import { ScoreRadar } from "@/components/signals/score-radar";

function SignalIcon({ type }: { type: string }) {
  if (type === "BUY") return <TrendingUp className="w-5 h-5 text-emerald-400" />;
  if (type === "SELL") return <TrendingDown className="w-5 h-5 text-red-400" />;
  return <Minus className="w-5 h-5 text-slate-400" />;
}

function ScoreBar({ label, value }: { label: string; value: number }) {
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs">
        <span className="text-slate-400">{label}</span>
        <span className={scoreToColor(value)}>{Math.round(value)}</span>
      </div>
      <div className="h-1.5 bg-slate-800 rounded-full overflow-hidden">
        <div
          className={cn("h-full rounded-full transition-all duration-500", value >= 70 ? "bg-emerald-500" : value >= 50 ? "bg-amber-500" : "bg-red-500")}
          style={{ width: `${value}%` }}
        />
      </div>
    </div>
  );
}

export function SignalDetailView({ ticker }: { ticker: string }) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["signal-latest", ticker],
    queryFn: () => api.signals.latest(ticker),
    refetchInterval: 60_000,
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-24">
        <Loader2 className="w-6 h-6 text-slate-600 animate-spin" />
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="flex items-center gap-2 text-red-400 py-8">
        <AlertTriangle className="w-4 h-4" />
        <span className="text-sm">Erreur lors du chargement de {ticker}</span>
      </div>
    );
  }

  const signal = "signal" in data && data.signal ? data.signal : null;

  if (!signal) {
    return (
      <div>
        <h1 className="text-xl font-semibold text-slate-100 mb-2">{ticker}</h1>
        <p className="text-slate-500 text-sm">Aucun signal disponible pour le moment. L'analyse sera générée au prochain cycle de refresh.</p>
      </div>
    );
  }

  const s = signal as Signal;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-xl font-semibold text-slate-100">{s.asset_name}</h1>
          <p className="text-slate-500 text-sm">{ticker}</p>
        </div>
        <div className="flex items-center gap-2 bg-slate-900 border border-slate-800 rounded-xl px-4 py-3">
          <SignalIcon type={s.signal_type} />
          <div className="text-right">
            <p className="text-sm font-semibold text-slate-100">{signalLabel(s.signal_type, s.strength)}</p>
            <p className={cn("text-2xl font-bold font-mono", scoreToColor(s.composite_score))}>
              {formatScore(s.composite_score)}
            </p>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-6">
        {/* Chart — occupe 2/3 */}
        <div className="col-span-2 space-y-4">
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
            <TradingViewChart ticker={ticker} />
          </div>

          {/* Raisonnement */}
          {s.reasoning && (
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
              <h3 className="text-sm font-medium text-slate-300 mb-3">Raisonnement IA</h3>
              <p className="text-sm text-slate-400 leading-relaxed">{s.reasoning}</p>
            </div>
          )}
        </div>

        {/* Panneau latéral — 1/3 */}
        <div className="space-y-4">
          {/* Score radar */}
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
            <h3 className="text-sm font-medium text-slate-300 mb-4">Score détaillé</h3>
            <ScoreRadar scores={s.scores} />
            <div className="mt-4 space-y-2">
              <ScoreBar label="Technique" value={s.scores.technical} />
              <ScoreBar label="Patterns" value={s.scores.patterns} />
              <ScoreBar label="Momentum" value={s.scores.momentum} />
              <ScoreBar label="Macro" value={s.scores.macro} />
              <ScoreBar label="Sentiment" value={s.scores.sentiment} />
            </div>
          </div>

          {/* Méta */}
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 space-y-3">
            <div>
              <p className="text-xs text-slate-500">Horizon</p>
              <p className="text-sm text-slate-200">{s.horizon ?? "—"}</p>
            </div>
            <div>
              <p className="text-xs text-slate-500">Confiance</p>
              <p className="text-sm text-slate-200">{Math.round(s.confidence * 100)}%</p>
            </div>
            {s.invalidation_conditions && (
              <div>
                <p className="text-xs text-slate-500 mb-1">Invalidation</p>
                <p className="text-sm text-red-400 bg-red-500/5 border border-red-500/10 px-2 py-1.5 rounded">
                  {s.invalidation_conditions}
                </p>
              </div>
            )}
          </div>

          {/* Risques */}
          {s.risks && s.risks.length > 0 && (
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
              <h3 className="text-sm font-medium text-slate-300 mb-3 flex items-center gap-1.5">
                <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />
                Risques
              </h3>
              <ul className="space-y-1.5">
                {s.risks.map((risk, i) => (
                  <li key={i} className="text-xs text-slate-400 flex items-start gap-1.5">
                    <span className="text-amber-500 mt-0.5">•</span>
                    {risk}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
