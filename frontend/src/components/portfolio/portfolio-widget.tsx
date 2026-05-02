"use client";

import Link from "next/link";
import { useQuery, useQueries } from "@tanstack/react-query";
import { api, type AssetQuote } from "@/lib/api";
import { cn, formatAssetPrice } from "@/lib/utils";
import { ChevronRight, TrendingUp, TrendingDown } from "lucide-react";

const ACCOUNT_COLORS: Record<string, string> = {
  PEA: "text-blue-400",
  CTO: "text-purple-400",
  PEE: "text-amber-400",
  AUTRE: "text-slate-400",
};

export function PortfolioWidget() {
  const { data: positions = [] } = useQuery({
    queryKey: ["positions"],
    queryFn: api.portfolio.positions,
    refetchInterval: 60_000,
  });

  const uniqueTickers = [...new Set(positions.map((p) => p.ticker))];
  const quoteQueries = useQueries({
    queries: uniqueTickers.map((ticker) => ({
      queryKey: ["quote", ticker],
      queryFn: () => api.assets.quote(ticker),
      staleTime: 30_000,
    })),
  });
  const quoteMap: Record<string, AssetQuote | undefined> = Object.fromEntries(
    uniqueTickers.map((ticker, i) => [ticker, quoteQueries[i].data])
  );

  if (positions.length === 0) return null;

  // Compute totals per account
  const accountTotals = (["PEA", "CTO", "PEE", "AUTRE"] as const).map((type) => {
    const acctPositions = positions.filter((p) => p.account_type === type);
    if (acctPositions.length === 0) return null;

    let totalInvested = 0;
    let totalMarket = 0;
    let hasQuotes = false;

    for (const pos of acctPositions) {
      const quote = quoteMap[pos.ticker];
      const isGBp = pos.currency === "GBp";
      const avg = isGBp ? pos.avg_price / 100 : pos.avg_price;
      totalInvested += avg * pos.quantity;
      if (quote?.current_price) {
        const cur = isGBp ? quote.current_price / 100 : quote.current_price;
        totalMarket += cur * pos.quantity;
        hasQuotes = true;
      }
    }

    const pnl = totalMarket - totalInvested;
    const pnlPct = totalInvested > 0 ? (pnl / totalInvested) * 100 : 0;
    const positive = pnl >= 0;
    const displayValue = hasQuotes ? totalMarket : totalInvested;

    return { type, displayValue, pnl, pnlPct, positive, hasQuotes, count: acctPositions.length };
  }).filter(Boolean);

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl px-4 py-3">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-sm font-semibold text-slate-300">Portefeuille</h2>
        <Link
          href="/portfolio"
          className="flex items-center gap-1 text-xs text-slate-500 hover:text-blue-400 transition-colors"
        >
          Gérer <ChevronRight className="w-3 h-3" />
        </Link>
      </div>
      <div className="flex items-center gap-6 flex-wrap">
        {accountTotals.map((acct) => {
          if (!acct) return null;
          return (
            <div key={acct.type} className="flex items-center gap-2">
              <span className={cn("text-xs font-semibold", ACCOUNT_COLORS[acct.type])}>
                {acct.type}
              </span>
              <div>
                <span className="text-sm font-mono font-semibold text-slate-200">
                  {acct.displayValue.toFixed(0)}
                </span>
                {acct.hasQuotes && (
                  <span className={cn("ml-1.5 text-xs font-mono", acct.positive ? "text-emerald-400" : "text-red-400")}>
                    {acct.positive ? "+" : ""}{acct.pnlPct.toFixed(1)}%
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
