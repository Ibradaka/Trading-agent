import { WatchlistPanel } from "@/components/watchlist/watchlist-panel";
import { ActiveSignalsPanel } from "@/components/signals/active-signals-panel";
import { SummaryBar } from "@/components/layout/summary-bar";
import { PortfolioWidget } from "@/components/portfolio/portfolio-widget";

export default function HomePage() {
  return (
    <div className="h-full space-y-4">
      <SummaryBar />
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
