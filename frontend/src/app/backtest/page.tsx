"use client";

import { useState } from "react";
import { api, BacktestResult, BacktestDiagnostics } from "@/lib/api";
import { cn } from "@/lib/utils";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from "recharts";

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

const LABEL_CONFIG: Record<string, { color: string; bg: string; icon: string }> = {
  robust:       { color: "text-emerald-400", bg: "bg-emerald-900/20 border-emerald-800",  icon: "✦" },
  noisy:        { color: "text-amber-400",   bg: "bg-amber-900/20 border-amber-800",      icon: "~" },
  over_traded:  { color: "text-orange-400",  bg: "bg-orange-900/20 border-orange-800",    icon: "!" },
  unstable:     { color: "text-red-400",     bg: "bg-red-900/20 border-red-800",          icon: "≈" },
  bearish_asset:{ color: "text-red-500",     bg: "bg-red-900/30 border-red-700",          icon: "↓" },
  mixed:        { color: "text-slate-400",   bg: "bg-slate-800/50 border-slate-700",      icon: "?" },
};

const REC_CONFIG: Record<string, { color: string; label: string }> = {
  keep:    { color: "text-emerald-400", label: "Conserver" },
  monitor: { color: "text-amber-400",   label: "Surveiller" },
  exclude: { color: "text-red-400",     label: "Exclure" },
};

function DiagnosticBanner({ d }: { d: BacktestDiagnostics }) {
  const lc = LABEL_CONFIG[d.label] ?? LABEL_CONFIG.mixed;
  const rc = REC_CONFIG[d.recommendation] ?? REC_CONFIG.monitor;
  return (
    <div className={cn("border rounded-xl p-4 flex flex-col sm:flex-row sm:items-center gap-3", lc.bg)}>
      <div className="flex items-center gap-3 flex-1">
        <span className={cn("text-2xl font-bold w-8 text-center", lc.color)}>{lc.icon}</span>
        <div>
          <div className="flex items-center gap-2">
            <span className={cn("text-sm font-semibold uppercase tracking-wide", lc.color)}>{d.label.replace("_", " ")}</span>
            <span className="text-slate-600">·</span>
            <span className={cn("text-sm font-medium", rc.color)}>{rc.label}</span>
          </div>
          <p className="text-xs text-slate-400 mt-0.5">{d.label_reason}</p>
        </div>
      </div>
      <p className="text-xs text-slate-500 sm:text-right sm:max-w-xs">{d.recommendation_reason}</p>
    </div>
  );
}

function StatRow({ label, value, sub }: { label: string; value: string | null; sub?: string }) {
  return (
    <div className="flex justify-between items-center py-1.5 border-b border-slate-800/50 last:border-0">
      <span className="text-xs text-slate-500">{label}</span>
      <div className="text-right">
        <span className="text-sm text-slate-200 font-medium">{value ?? "—"}</span>
        {sub && <span className="text-xs text-slate-600 ml-1">{sub}</span>}
      </div>
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

interface SimTrade {
  date: string;
  type: "BUY" | "SELL";
  price: number;
  returnPct: number;
  capitalBefore: number;
  capitalAfter: number;
  gain: number;
  won: boolean;
}

interface SimResult {
  trades: SimTrade[];
  curve: { label: string; capital: number }[];
  initialCapital: number;
  finalCapital: number;
  totalGain: number;
  totalGainPct: number;
  nWon: number;
  nLost: number;
  bestTrade: SimTrade | null;
  worstTrade: SimTrade | null;
  maxDrawdown: number;
}

function computeSimulation(result: BacktestResult, initialCapital = 1000): SimResult {
  const horizon = result.metrics.horizon_days;
  const returnKey = horizon <= 5 ? "return_5d" : horizon <= 10 ? "return_10d" : "return_20d";

  const validSignals = result.signals.filter((s) => {
    const r = s[returnKey as keyof typeof s] as number | null;
    return r !== null;
  });

  if (validSignals.length === 0) {
    return {
      trades: [],
      curve: [{ label: "Départ", capital: initialCapital }],
      initialCapital,
      finalCapital: initialCapital,
      totalGain: 0,
      totalGainPct: 0,
      nWon: 0,
      nLost: 0,
      bestTrade: null,
      worstTrade: null,
      maxDrawdown: 0,
    };
  }

  const positionSize = initialCapital / validSignals.length;
  let capital = initialCapital;
  const trades: SimTrade[] = [];
  const curve: { label: string; capital: number }[] = [{ label: "Départ", capital: initialCapital }];
  let peak = initialCapital;
  let maxDrawdown = 0;

  for (const sig of validSignals) {
    const returnPct = (sig[returnKey as keyof typeof sig] as number) ?? 0;
    const adjustedReturn = sig.signal_type === "SELL" ? -returnPct : returnPct;
    const capitalBefore = capital;
    const gain = positionSize * (adjustedReturn / 100);
    capital = capital + gain;
    const won = adjustedReturn > 0;

    const trade: SimTrade = {
      date: sig.date,
      type: sig.signal_type as "BUY" | "SELL",
      price: sig.price,
      returnPct: adjustedReturn,
      capitalBefore,
      capitalAfter: capital,
      gain,
      won,
    };
    trades.push(trade);

    const label = new Date(sig.date).toLocaleDateString("fr-FR", { month: "short", year: "2-digit" });
    curve.push({ label, capital: Math.round(capital * 100) / 100 });

    if (capital > peak) peak = capital;
    const dd = ((peak - capital) / peak) * 100;
    if (dd > maxDrawdown) maxDrawdown = dd;
  }

  const sortedByGain = [...trades].sort((a, b) => b.gain - a.gain);

  return {
    trades,
    curve,
    initialCapital,
    finalCapital: capital,
    totalGain: capital - initialCapital,
    totalGainPct: ((capital - initialCapital) / initialCapital) * 100,
    nWon: trades.filter((t) => t.won).length,
    nLost: trades.filter((t) => !t.won).length,
    bestTrade: sortedByGain[0] ?? null,
    worstTrade: sortedByGain[sortedByGain.length - 1] ?? null,
    maxDrawdown,
  };
}

function SimulationPanel({ result }: { result: BacktestResult }) {
  const sim = computeSimulation(result);
  const positive = sim.totalGain >= 0;

  const CustomTooltip = ({ active, payload, label }: { active?: boolean; payload?: Array<{ value: number }>; label?: string }) => {
    if (!active || !payload?.length) return null;
    const val = payload[0].value;
    const diff = val - sim.initialCapital;
    const pct = ((diff / sim.initialCapital) * 100).toFixed(1);
    return (
      <div className="bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-xs">
        <p className="text-slate-400 mb-0.5">{label}</p>
        <p className="font-semibold text-slate-100">{val.toFixed(0)} €</p>
        <p className={cn("font-medium", diff >= 0 ? "text-emerald-400" : "text-red-400")}>
          {diff >= 0 ? "+" : ""}{diff.toFixed(0)} € ({diff >= 0 ? "+" : ""}{pct}%)
        </p>
      </div>
    );
  };

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold text-slate-200">Simulation 1 000 €</h3>
          <p className="text-xs text-slate-500 mt-0.5">
            {sim.trades.length} trades · {sim.initialCapital / sim.trades.length > 0 ? `${(sim.initialCapital / sim.trades.length).toFixed(0)} € par position` : "—"}
          </p>
        </div>
        <div className="text-right">
          <p className={cn("text-3xl font-bold font-mono", positive ? "text-emerald-400" : "text-red-400")}>
            {sim.finalCapital.toFixed(0)} €
          </p>
          <p className={cn("text-sm font-medium font-mono", positive ? "text-emerald-400/80" : "text-red-400/80")}>
            {positive ? "+" : ""}{sim.totalGain.toFixed(0)} € ({positive ? "+" : ""}{sim.totalGainPct.toFixed(1)}%)
          </p>
        </div>
      </div>

      {/* Courbe d'évolution */}
      <div className="h-44">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={sim.curve} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
            <defs>
              <linearGradient id="capitalGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor={positive ? "#10b981" : "#ef4444"} stopOpacity={0.25} />
                <stop offset="95%" stopColor={positive ? "#10b981" : "#ef4444"} stopOpacity={0} />
              </linearGradient>
            </defs>
            <XAxis dataKey="label" tick={{ fill: "#475569", fontSize: 10 }} tickLine={false} axisLine={false} interval="preserveStartEnd" />
            <YAxis tick={{ fill: "#475569", fontSize: 10 }} tickLine={false} axisLine={false} tickFormatter={(v) => `${v}€`} width={52} />
            <Tooltip content={<CustomTooltip />} />
            <ReferenceLine y={sim.initialCapital} stroke="#334155" strokeDasharray="4 3" />
            <Area
              type="monotone"
              dataKey="capital"
              stroke={positive ? "#10b981" : "#ef4444"}
              strokeWidth={2}
              fill="url(#capitalGrad)"
              dot={false}
              isAnimationActive={false}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {/* Stats récapitulatives */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="bg-slate-800/50 rounded-lg p-3">
          <p className="text-xs text-slate-500 mb-1">Trades gagnants</p>
          <p className="text-lg font-semibold text-emerald-400">{sim.nWon}</p>
          <p className="text-xs text-slate-600">{sim.trades.length > 0 ? `${((sim.nWon / sim.trades.length) * 100).toFixed(0)}% de réussite` : "—"}</p>
        </div>
        <div className="bg-slate-800/50 rounded-lg p-3">
          <p className="text-xs text-slate-500 mb-1">Trades perdants</p>
          <p className="text-lg font-semibold text-red-400">{sim.nLost}</p>
          <p className="text-xs text-slate-600">{sim.trades.length > 0 ? `${((sim.nLost / sim.trades.length) * 100).toFixed(0)}% des trades` : "—"}</p>
        </div>
        <div className="bg-slate-800/50 rounded-lg p-3">
          <p className="text-xs text-slate-500 mb-1">Meilleur trade</p>
          <p className="text-lg font-semibold text-emerald-400">
            {sim.bestTrade ? `+${sim.bestTrade.gain.toFixed(0)} €` : "—"}
          </p>
          <p className="text-xs text-slate-600">
            {sim.bestTrade ? `${sim.bestTrade.returnPct > 0 ? "+" : ""}${sim.bestTrade.returnPct.toFixed(1)}% · ${new Date(sim.bestTrade.date).toLocaleDateString("fr-FR", { day: "numeric", month: "short" })}` : ""}
          </p>
        </div>
        <div className="bg-slate-800/50 rounded-lg p-3">
          <p className="text-xs text-slate-500 mb-1">Pire trade</p>
          <p className="text-lg font-semibold text-red-400">
            {sim.worstTrade ? `${sim.worstTrade.gain.toFixed(0)} €` : "—"}
          </p>
          <p className="text-xs text-slate-600">
            {sim.worstTrade ? `${sim.worstTrade.returnPct.toFixed(1)}% · ${new Date(sim.worstTrade.date).toLocaleDateString("fr-FR", { day: "numeric", month: "short" })}` : ""}
          </p>
        </div>
      </div>

      {sim.maxDrawdown > 0 && (
        <div className="flex items-center gap-2 text-xs text-slate-500 border-t border-slate-800 pt-3">
          <span className="text-slate-600">Drawdown max :</span>
          <span className={cn("font-medium", sim.maxDrawdown > 20 ? "text-red-400" : sim.maxDrawdown > 10 ? "text-amber-400" : "text-slate-400")}>
            -{sim.maxDrawdown.toFixed(1)}%
          </span>
          <span className="text-slate-700">·</span>
          <span className="text-slate-600">Soit -{((sim.maxDrawdown / 100) * sim.initialCapital).toFixed(0)} € au pire moment</span>
        </div>
      )}
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

          {/* Simulation 1 000 € */}
          <SimulationPanel result={result} />

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

          {/* Diagnostic Phase 5.5 */}
          {result.diagnostics && (() => {
            const d = result.diagnostics!;
            const sq = d.signal_quality;
            return (
              <div className="space-y-4">
                {/* Bannière label + recommandation */}
                <DiagnosticBanner d={d} />

                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  {/* Qualité des signaux */}
                  <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
                    <h3 className="text-sm font-medium text-slate-300 mb-3">Qualité des signaux</h3>
                    <StatRow label="Fréquence" value={`${sq.signal_frequency_per_year} / an`} />
                    <StatRow label="Faux signaux" value={sq.false_signal_rate_pct != null ? `${sq.false_signal_rate_pct}%` : null} />
                    <StatRow label="Dispersion retours" value={`${sq.return_dispersion_p25}% → ${sq.return_dispersion_p75}%`} sub="P25/P75" />
                    <StatRow label="Stabilité (1ère moitié)" value={sq.stability_first_half_wr != null ? `${sq.stability_first_half_wr}%` : null} />
                    <StatRow label="Stabilité (2ème moitié)" value={sq.stability_second_half_wr != null ? `${sq.stability_second_half_wr}%` : null} />
                    <StatRow
                      label="Delta stabilité"
                      value={`${sq.stability_delta_pct} pts`}
                    />
                    {d.overtrading.is_over_traded && (
                      <div className="mt-2 px-2 py-1 bg-orange-900/20 border border-orange-800/50 rounded text-xs text-orange-400">
                        Sur-trading détecté ({d.overtrading.severity})
                      </div>
                    )}
                  </div>

                  {/* BUY vs SELL */}
                  <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
                    <h3 className="text-sm font-medium text-slate-300 mb-3">Performance par type</h3>
                    {Object.entries(d.by_signal_type).map(([type, stats]) => (
                      <div key={type} className="mb-3 last:mb-0">
                        <div className="flex items-center gap-2 mb-1.5">
                          <span className={cn(
                            "px-1.5 py-0.5 rounded text-xs font-medium",
                            type === "BUY" ? "bg-emerald-900/50 text-emerald-400" : "bg-red-900/50 text-red-400"
                          )}>{type}</span>
                          <span className="text-xs text-slate-500">{stats.n} signaux</span>
                        </div>
                        <StatRow label="Win rate" value={stats.win_rate_pct != null ? `${stats.win_rate_pct}%` : null} />
                        <StatRow label="Retour moyen" value={stats.avg_return_pct != null ? `${stats.avg_return_pct > 0 ? "+" : ""}${stats.avg_return_pct}%` : null} />
                        <StatRow label="Sharpe" value={stats.sharpe != null ? stats.sharpe.toFixed(2) : null} />
                      </div>
                    ))}
                    {Object.keys(d.by_signal_type).length === 0 && (
                      <p className="text-xs text-slate-600">Aucun signal valide</p>
                    )}
                  </div>

                  {/* Calibration score */}
                  <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
                    <h3 className="text-sm font-medium text-slate-300 mb-3">Calibration par score</h3>
                    {Object.entries(d.score_calibration).map(([bucket, stats]) => (
                      <div key={bucket} className="flex justify-between items-center py-1.5 border-b border-slate-800/50 last:border-0">
                        <div>
                          <span className="text-xs text-slate-400">Score {bucket}</span>
                          <span className="text-xs text-slate-600 ml-1">({stats.n})</span>
                        </div>
                        <span className={cn(
                          "text-sm font-medium",
                          stats.win_rate_pct == null ? "text-slate-600" :
                          stats.win_rate_pct >= 60 ? "text-emerald-400" :
                          stats.win_rate_pct < 45 ? "text-red-400" : "text-amber-400"
                        )}>
                          {stats.win_rate_pct != null ? `${stats.win_rate_pct}%` : "—"}
                        </span>
                      </div>
                    ))}
                    <h3 className="text-sm font-medium text-slate-300 mt-4 mb-2">Par confiance</h3>
                    {Object.entries(d.confidence_calibration).map(([label, stats]) => (
                      <div key={label} className="flex justify-between items-center py-1.5 border-b border-slate-800/50 last:border-0">
                        <div>
                          <span className={cn(
                            "text-xs",
                            label === "high" ? "text-blue-400" : label === "medium" ? "text-amber-400" : "text-slate-500"
                          )}>{label}</span>
                          <span className="text-xs text-slate-600 ml-1">({stats.n})</span>
                        </div>
                        <span className={cn(
                          "text-sm font-medium",
                          stats.win_rate_pct == null ? "text-slate-600" :
                          stats.win_rate_pct >= 60 ? "text-emerald-400" :
                          stats.win_rate_pct < 45 ? "text-red-400" : "text-amber-400"
                        )}>
                          {stats.win_rate_pct != null ? `${stats.win_rate_pct}%` : "—"}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            );
          })()}

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
