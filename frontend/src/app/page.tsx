import { WatchlistPanel } from "@/components/watchlist/watchlist-panel";
import { ActiveSignalsPanel } from "@/components/signals/active-signals-panel";
import { SummaryBar } from "@/components/layout/summary-bar";
import { PortfolioWidget } from "@/components/portfolio/portfolio-widget";
import { MarketOverviewBar } from "@/components/layout/market-overview-bar";

export default function HomePage() {
  return (
    <div className="h-full space-y-4">
      <SummaryBar />
      <MarketOverviewBar />
      <PortfolioWidget />
      <div className="flex gap-6 items-start">
        <div className="flex-1 min-w-0">
          <WatchlistPanel />
        </div>
        <div className="w-72 flex-shrink-0">
          <ActiveSignalsPanel />
        </div>
      </div>
    </div>
  );
}
