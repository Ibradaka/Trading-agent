"use client";

import { useState } from "react";
import { api, BacktestResult } from "@/lib/api";
import { cn } from "@/lib/utils";

function KpiCard({ label, value, sub, highlight }: { label: string; value: string | null; sub?: string; highlight?: "good" | "bad" | "neutral" }) {
  const colors = { good: "text-emerald-400", bad: "text-red-400", neutral: "text-slate-100" };
  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
      <p className="text-xs text-slate-500 mb-1">{label}</p>
      <p className={cn("text-2xl font-semibold", highlight ? colors[highlight] : "text-slate-100")}>{value ?? "—"}</p>
      {sub && <p className="text-xs text-slate-500 mt-1">{sub}</p>}
    </div>
  );
}

function BenchmarkRow({ label, value, systemValue }: { label: string; value: number; systemValue: number }) {
  const diff = systemValue - value;
  return (
    <div className="flex items-center justify-between py-2 border-b border-slate-800/50 last:border-0">
      <span className="text-sm text-slate-400">{label}</span>
      <div className="flex items-center gap-4">
        <span className="text-sm text-slate-300">{value > 0 ? "+" : ""}{value.toFixed(1)}%</span>
        <span className={cn("text-xs", diff > 0 ? "text-emerald-400" : "text-red-400")}>
          {diff > 0 ? "▲" : "▼"} {Math.abs(diff).toFixed(1)}%
        </span>
      </div>
    </div>
  );
}

export default function BacktestPage() {
  const [ticker, setTicker] = useState("");
  const [period, setPeriod] = useState("5y");
  const [horizon, setHorizon] = useState(20);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleRun = async () => {
    if (!ticker.trim()) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await api.backtest.run(ticker.trim().toUpperCase(), period, horizon);
      if (res.error) {
        setError(res.error);
      } else {
        setResult(res);
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Erreur inconnue");
    } finally {
      setLoading(false);
    }
  };

  const m = result?.metrics;
  const b = result?.benchmarks;
  const systemAvgReturn = m?.avg_return_pct ?? 0;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-slate-100">Backtesting walk-forward</h1>
        <p className="text-sm text-slate-500 mt-1">
          Simulation sur historique yfinance — aucune fuite de données futures
        </p>
      </div>

      {/* Formulaire */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 flex flex-wrap gap-3 items-end">
        <div className="flex flex-col gap-1">
          <label className="text-xs text-slate-500">Ticker</label>
          <input
            className="bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-100 w-32 focus:outline-none focus:border-blue-500"
            placeholder="NVDA"
            value={ticker}
            onChange={(e) => setTicker(e.target.value.toUpperCase())}
            onKeyDown={(e) => e.key === "Enter" && handleRun()}
          />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs text-slate-500">Période</label>
          <select
            className="bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-100 focus:outline-none focus:border-blue-500"
            value={period}
            onChange={(e) => setPeriod(e.target.value)}
          >
            <option value="1y">1 an</option>
            <option value="2y">2 ans</option>
            <option value="5y">5 ans</option>
          </select>
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs text-slate-500">Horizon mesure</label>
          <select
            className="bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-100 focus:outline-none focus:border-blue-500"
            value={horizon}
            onChange={(e) => setHorizon(Number(e.target.value))}
          >
            <option value={5}>J+5</option>
            <option value={10}>J+10</option>
            <option value={20}>J+20</option>
          </select>
        </div>
        <button
          className="px-4 py-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-sm rounded-lg transition-colors"
          onClick={handleRun}
          disabled={loading || !ticker.trim()}
        >
          {loading ? "Calcul…" : "Lancer"}
        </button>
      </div>

      {error && (
        <div className="bg-red-900/20 border border-red-800 rounded-xl p-4">
          <p className="text-sm text-red-400">{error}</p>
        </div>
      )}

      {result && m && (
        <div className="space-y-6">
          {/* KPIs */}
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
            <KpiCard
              label="Signaux générés"
              value={String(result.total_signals)}
              sub={`${result.buy_signals} BUY / ${result.sell_signals} SELL`}
            />
            <KpiCard
              label="Win rate"
              value={m.win_rate_pct != null ? `${m.win_rate_pct}%` : null}
              highlight={m.win_rate_pct != null ? (m.win_rate_pct >= 55 ? "good" : m.win_rate_pct < 45 ? "bad" : "neutral") : "neutral"}
            />
            <KpiCard
              label="Retour moyen"
              value={m.avg_return_pct != null ? `${m.avg_return_pct > 0 ? "+" : ""}${m.avg_return_pct}%` : null}
              sub={`à J+${m.horizon_days}`}
              highlight={m.avg_return_pct != null ? (m.avg_return_pct > 0 ? "good" : "bad") : "neutral"}
            />
            <KpiCard
              label="Sharpe ratio"
              value={m.sharpe_ratio != null ? m.sharpe_ratio.toFixed(2) : null}
              highlight={m.sharpe_ratio != null ? (m.sharpe_ratio >= 1 ? "good" : m.sharpe_ratio < 0 ? "bad" : "neutral") : "neutral"}
            />
            <KpiCard
              label="Max drawdown"
              value={m.max_drawdown_pct != null ? `${m.max_drawdown_pct.toFixed(1)}%` : null}
              highlight={m.max_drawdown_pct != null ? (m.max_drawdown_pct > -10 ? "good" : "bad") : "neutral"}
            />
            <KpiCard
              label="Retour cumulé"
              value={m.cumulative_return_pct != null ? `${m.cumulative_return_pct > 0 ? "+" : ""}${m.cumulative_return_pct}%` : null}
              highlight={m.cumulative_return_pct != null ? (m.cumulative_return_pct > 0 ? "good" : "bad") : "neutral"}
            />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Benchmarks */}
            {b && (
              <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
                <h3 className="text-sm font-medium text-slate-300 mb-3">
                  Comparaison benchmarks
                  <span className="ml-2 text-xs text-slate-500">(retour moyen à J+{m.horizon_days})</span>
                </h3>
                <BenchmarkRow label="Buy & Hold (total)" value={b.buy_and_hold_pct} systemValue={m.cumulative_return_pct ?? 0} />
                <BenchmarkRow label="Momentum simple" value={b.momentum_avg_return_pct} systemValue={systemAvgReturn} />
                <BenchmarkRow label="Croisement MA20/MA50" value={b.ma_crossover_avg_return_pct} systemValue={systemAvgReturn} />
              </div>
            )}

            {/* Calibration */}
            {m.calibration && (
              <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
                <h3 className="text-sm font-medium text-slate-300 mb-3">Calibration confidence</h3>
                <div className="space-y-3">
                  <div className="flex justify-between items-center">
                    <div>
                      <p className="text-sm text-blue-400">High confidence</p>
                      <p className="text-xs text-slate-500">{m.calibration.n_high} signaux</p>
                    </div>
                    <p className="text-lg font-semibold text-slate-100">
                      {m.calibration.high_confidence_win_rate_pct != null ? `${m.calibration.high_confidence_win_rate_pct}%` : "—"}
                    </p>
                  </div>
                  <div className="flex justify-between items-center">
                    <div>
                      <p className="text-sm text-amber-400">Medium confidence</p>
                      <p className="text-xs text-slate-500">{m.calibration.n_medium} signaux</p>
                    </div>
                    <p className="text-lg font-semibold text-slate-100">
                      {m.calibration.medium_confidence_win_rate_pct != null ? `${m.calibration.medium_confidence_win_rate_pct}%` : "—"}
                    </p>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Signaux simulés */}
          <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
            <div className="px-4 py-3 border-b border-slate-800">
              <h3 className="text-sm font-medium text-slate-300">
                Signaux simulés — {result.ticker} ({result.period})
              </h3>
            </div>
            <div className="overflow-x-auto max-h-96">
              <table className="w-full text-xs">
                <thead className="sticky top-0 bg-slate-900">
                  <tr className="border-b border-slate-800">
                    <th className="text-left px-4 py-2 text-slate-500 font-medium">Date</th>
                    <th className="text-left px-4 py-2 text-slate-500 font-medium">Signal</th>
                    <th className="text-right px-4 py-2 text-slate-500 font-medium">Score</th>
                    <th className="text-left px-4 py-2 text-slate-500 font-medium">Conf.</th>
                    <th className="text-right px-4 py-2 text-slate-500 font-medium">Prix</th>
                    <th className="text-right px-4 py-2 text-slate-500 font-medium">J+5</th>
                    <th className="text-right px-4 py-2 text-slate-500 font-medium">J+10</th>
                    <th className="text-right px-4 py-2 text-slate-500 font-medium">J+20</th>
                  </tr>
                </thead>
                <tbody>
                  {result.signals.map((sig, idx) => {
                    const ret20 = sig.return_20d;
                    const correct = sig.correct_20d;
                    return (
                      <tr key={idx} className="border-b border-slate-800/50 hover:bg-slate-800/20">
                        <td className="px-4 py-2 text-slate-500">
                          {new Date(sig.date).toLocaleDateString("fr-FR")}
                        </td>
                        <td className="px-4 py-2">
                          <span className={cn(
                            "px-1.5 py-0.5 rounded text-xs font-medium",
                            sig.signal_type === "BUY" ? "bg-emerald-900/50 text-emerald-400" : "bg-red-900/50 text-red-400"
                          )}>
                            {sig.signal_type}
                          </span>
                        </td>
                        <td className="px-4 py-2 text-right text-slate-300">{sig.score}</td>
                        <td className="px-4 py-2">
                          <span className={cn(
                            "text-xs",
                            sig.confidence_label === "high" ? "text-blue-400" : sig.confidence_label === "medium" ? "text-amber-400" : "text-slate-500"
                          )}>
                            {sig.confidence_label}
                          </span>
                        </td>
                        <td className="px-4 py-2 text-right text-slate-400">{sig.price.toFixed(2)}</td>
                        {[sig.return_5d, sig.return_10d, ret20].map((r, i) => (
                          <td key={i} className={cn(
                            "px-4 py-2 text-right font-medium",
                            r == null ? "text-slate-600" : r > 0 ? "text-emerald-400" : "text-red-400"
                          )}>
                            {r == null ? "—" : `${r > 0 ? "+" : ""}${r.toFixed(1)}%`}
                          </td>
                        ))}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
