"use client";

import { useQuery } from "@tanstack/react-query";
import { api, type Signal, type AssetQuote, type NewsItem } from "@/lib/api";
import { Loader2, AlertTriangle, TrendingUp, TrendingDown, Minus, ExternalLink } from "lucide-react";
import { cn, scoreToColor, signalLabel, formatScore, formatAssetPrice } from "@/lib/utils";
import { TradingViewChart } from "@/components/charts/trading-view-chart";
import { ScoreRadar } from "@/components/signals/score-radar";

function formatVolume(v: number): string {
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
  if (v >= 1_000) return `${(v / 1_000).toFixed(0)}k`;
  return v.toLocaleString("fr-FR");
}

function relativeTime(ts: number | null): string {
  if (!ts) return "";
  const diff = Date.now() / 1000 - ts;
  if (diff < 3600) return `il y a ${Math.floor(diff / 60)} min`;
  if (diff < 86400) return `il y a ${Math.floor(diff / 3600)} h`;
  return `il y a ${Math.floor(diff / 86400)} j`;
}

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
          className={cn(
            "h-full rounded-full transition-all duration-500",
            value >= 70 ? "bg-emerald-500" : value >= 50 ? "bg-amber-500" : "bg-red-500"
          )}
          style={{ width: `${value}%` }}
        />
      </div>
    </div>
  );
}

function MarketStateBadge({ state }: { state: string | null }) {
  const config: Record<string, { label: string; dot: string; text: string }> = {
    REGULAR: { label: "Ouvert", dot: "bg-emerald-400", text: "text-emerald-400" },
    PRE: { label: "Pré-marché", dot: "bg-amber-400", text: "text-amber-400" },
    POST: { label: "Post-marché", dot: "bg-orange-400", text: "text-orange-400" },
    CLOSED: { label: "Fermé", dot: "bg-slate-500", text: "text-slate-500" },
  };
  const c = config[state ?? ""] ?? config.CLOSED;
  return (
    <span className={cn("flex items-center gap-1.5 text-xs font-medium", c.text)}>
      <span className={cn("w-1.5 h-1.5 rounded-full", c.dot)} />
      {c.label}
    </span>
  );
}

function PriceHeader({ quote }: { quote: AssetQuote | undefined }) {
  if (!quote?.current_price) {
    return (
      <div className="bg-slate-900 border border-slate-800 rounded-xl px-6 py-4 space-y-4">
        <div className="flex gap-3">
          <div className="w-40 h-9 bg-slate-800 rounded animate-pulse" />
          <div className="w-24 h-7 bg-slate-800 rounded animate-pulse" />
        </div>
        <div className="grid grid-cols-4 gap-3">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="h-14 bg-slate-800 rounded-lg animate-pulse" />
          ))}
        </div>
      </div>
    );
  }

  const positive = (quote.change_pct ?? 0) >= 0;
  const price = formatAssetPrice(quote.current_price, quote.currency);

  const week52Pct =
    quote.week52_high && quote.week52_low && quote.current_price
      ? Math.min(100, Math.max(0,
          ((quote.current_price - quote.week52_low) / (quote.week52_high - quote.week52_low)) * 100
        ))
      : null;

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl px-6 py-4 space-y-4">
      {/* Prix principal + variations */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <div className="flex items-center gap-3 flex-wrap">
            <span className="text-3xl font-mono font-bold text-slate-100">{price}</span>
            <div
              className={cn(
                "flex items-center gap-1 px-2.5 py-1 rounded-lg text-sm font-semibold",
                positive ? "bg-emerald-500/10 text-emerald-400" : "bg-red-500/10 text-red-400"
              )}
            >
              {positive ? <TrendingUp className="w-3.5 h-3.5" /> : <TrendingDown className="w-3.5 h-3.5" />}
              {quote.change_pct !== null
                ? `${positive ? "+" : ""}${quote.change_pct.toFixed(2)}%`
                : "—"}
            </div>
            <MarketStateBadge state={quote.market_state} />
          </div>
          <p className="text-xs text-slate-500 mt-1">
            {quote.exchange} · {quote.currency}
          </p>
        </div>

        {/* 1S / 1M */}
        <div className="flex items-center gap-5">
          {[
            { label: "1 semaine", val: quote.week_change_pct },
            { label: "1 mois", val: quote.month_change_pct },
          ].map(({ label, val }) => (
            <div key={label} className="text-right">
              <p className="text-xs text-slate-600">{label}</p>
              <p
                className={cn(
                  "text-sm font-mono font-semibold",
                  val === null ? "text-slate-600" : val >= 0 ? "text-emerald-400" : "text-red-400"
                )}
              >
                {val !== null ? `${val >= 0 ? "+" : ""}${val.toFixed(2)}%` : "—"}
              </p>
            </div>
          ))}
        </div>
      </div>

      {/* OHLC + Volume */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {[
          { label: "Ouverture", val: quote.open, isVol: false },
          { label: "Haut du jour", val: quote.day_high, isVol: false },
          { label: "Bas du jour", val: quote.day_low, isVol: false },
          { label: "Volume", val: quote.volume, isVol: true },
        ].map(({ label, val, isVol }) => (
          <div key={label} className="bg-slate-800/50 rounded-lg px-3 py-2">
            <p className="text-xs text-slate-500">{label}</p>
            <p className="text-sm font-mono font-semibold text-slate-200 mt-0.5">
              {val === null || val === undefined
                ? "—"
                : isVol
                ? formatVolume(val)
                : formatAssetPrice(val, quote.currency)}
            </p>
          </div>
        ))}
      </div>

      {/* Plage 52 semaines */}
      {week52Pct !== null && quote.week52_low && quote.week52_high && (
        <div>
          <div className="flex justify-between text-xs text-slate-600 mb-1.5">
            <span>52S Bas : {formatAssetPrice(quote.week52_low, quote.currency)}</span>
            <span>52S Haut : {formatAssetPrice(quote.week52_high, quote.currency)}</span>
          </div>
          <div className="relative h-1.5 bg-slate-800 rounded-full overflow-visible">
            <div
              className="h-full bg-slate-600 rounded-full"
              style={{ width: `${week52Pct}%` }}
            />
            <div
              className="absolute top-1/2 -translate-y-1/2 w-3 h-3 bg-blue-400 rounded-full border-2 border-slate-900 shadow"
              style={{ left: `calc(${week52Pct}% - 6px)` }}
            />
          </div>
        </div>
      )}
    </div>
  );
}

function NewsSection({ news }: { news: NewsItem[] }) {
  if (news.length === 0) return null;
  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
      <h3 className="text-sm font-medium text-slate-300 mb-3">Actualités récentes</h3>
      <div className="space-y-1">
        {news.map((item, i) => (
          <a
            key={i}
            href={item.link}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-start gap-3 group hover:bg-slate-800/50 -mx-2 px-2 py-2 rounded-lg transition-colors"
          >
            <div className="flex-1 min-w-0">
              <p className="text-sm text-slate-200 group-hover:text-blue-400 transition-colors leading-snug">
                {item.title}
              </p>
              <p className="text-xs text-slate-600 mt-0.5">
                {item.publisher}
                {item.published_at ? ` · ${relativeTime(item.published_at)}` : ""}
              </p>
            </div>
            <ExternalLink className="w-3.5 h-3.5 text-slate-700 group-hover:text-slate-400 flex-shrink-0 mt-0.5 transition-colors" />
          </a>
        ))}
      </div>
    </div>
  );
}

export function SignalDetailView({ ticker }: { ticker: string }) {
  const { data: signalData, isLoading: signalLoading, isError } = useQuery({
    queryKey: ["signal-latest", ticker],
    queryFn: () => api.signals.latest(ticker),
    refetchInterval: 60_000,
  });

  const { data: quote } = useQuery<AssetQuote>({
    queryKey: ["quote", ticker],
    queryFn: () => api.assets.quote(ticker),
    refetchInterval: 60_000,
    staleTime: 30_000,
  });

  const { data: news = [] } = useQuery<NewsItem[]>({
    queryKey: ["news", ticker],
    queryFn: () => api.assets.news(ticker),
    staleTime: 30 * 60_000,
    refetchInterval: 30 * 60_000,
  });

  if (signalLoading && !quote) {
    return (
      <div className="flex items-center justify-center py-24">
        <Loader2 className="w-6 h-6 text-slate-600 animate-spin" />
      </div>
    );
  }

  if (isError) {
    return (
      <div className="flex items-center gap-2 text-red-400 py-8">
        <AlertTriangle className="w-4 h-4" />
        <span className="text-sm">Erreur lors du chargement de {ticker}</span>
      </div>
    );
  }

  // Signal object has 'id'; no-signal response has 'signal: null'
  const signal: Signal | null =
    signalData && "id" in signalData ? (signalData as Signal) : null;

  const assetName = signal?.asset_name ?? quote?.ticker ?? ticker;

  return (
    <div className="space-y-4">
      {/* Titre */}
      <div>
        <h1 className="text-xl font-semibold text-slate-100">{assetName}</h1>
        <p className="text-slate-500 text-sm">{ticker}</p>
      </div>

      {/* En-tête prix enrichi */}
      <PriceHeader quote={quote} />

      {/* Chart + signal */}
      <div className="grid grid-cols-3 gap-6">
        {/* Colonne principale : chart + raisonnement */}
        <div className="col-span-2 space-y-4">
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
            <TradingViewChart ticker={ticker} />
          </div>
          {signal?.reasoning && (
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
              <h3 className="text-sm font-medium text-slate-300 mb-3">Raisonnement IA</h3>
              <p className="text-sm text-slate-400 leading-relaxed">{signal.reasoning}</p>
            </div>
          )}
        </div>

        {/* Sidebar : signal ou en attente */}
        <div className="space-y-4">
          {signal ? (
            <>
              <div className="bg-slate-900 border border-slate-800 rounded-xl px-4 py-3 flex items-center gap-3">
                <SignalIcon type={signal.signal_type} />
                <div>
                  <p className="text-sm font-semibold text-slate-100">
                    {signalLabel(signal.signal_type, signal.strength)}
                  </p>
                  <p className={cn("text-2xl font-bold font-mono", scoreToColor(signal.composite_score))}>
                    {formatScore(signal.composite_score)}
                  </p>
                </div>
              </div>

              <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
                <h3 className="text-sm font-medium text-slate-300 mb-4">Score détaillé</h3>
                <ScoreRadar scores={signal.scores} />
                <div className="mt-4 space-y-2">
                  <ScoreBar label="Technique" value={signal.scores.technical} />
                  <ScoreBar label="Patterns" value={signal.scores.patterns} />
                  <ScoreBar label="Momentum" value={signal.scores.momentum} />
                  <ScoreBar label="Macro" value={signal.scores.macro} />
                  <ScoreBar label="Sentiment" value={signal.scores.sentiment} />
                </div>
              </div>

              <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 space-y-3">
                <div>
                  <p className="text-xs text-slate-500">Horizon</p>
                  <p className="text-sm text-slate-200">{signal.horizon ?? "—"}</p>
                </div>
                <div>
                  <p className="text-xs text-slate-500">Confiance</p>
                  <p className="text-sm text-slate-200">{Math.round(signal.confidence * 100)}%</p>
                </div>
                {signal.invalidation_conditions && (
                  <div>
                    <p className="text-xs text-slate-500 mb-1">Invalidation</p>
                    <p className="text-sm text-red-400 bg-red-500/5 border border-red-500/10 px-2 py-1.5 rounded">
                      {signal.invalidation_conditions}
                    </p>
                  </div>
                )}
              </div>

              {signal.risks && signal.risks.length > 0 && (
                <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
                  <h3 className="text-sm font-medium text-slate-300 mb-3 flex items-center gap-1.5">
                    <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />
                    Risques
                  </h3>
                  <ul className="space-y-1.5">
                    {signal.risks.map((risk, i) => (
                      <li key={i} className="text-xs text-slate-400 flex items-start gap-1.5">
                        <span className="text-amber-500 mt-0.5">•</span>
                        {risk}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </>
          ) : (
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
              <div className="flex items-center gap-2 mb-2">
                <Loader2 className="w-4 h-4 text-slate-600 animate-spin" />
                <p className="text-sm font-medium text-slate-400">Analyse en cours</p>
              </div>
              <p className="text-xs text-slate-600">
                Le signal sera généré au prochain cycle de refresh.
              </p>
            </div>
          )}
        </div>
      </div>

      {/* Section news */}
      <NewsSection news={news} />
    </div>
  );
}
