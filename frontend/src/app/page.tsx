import { WatchlistPanel } from "@/components/watchlist/watchlist-panel";

export default function HomePage() {
  return (
    <div className="h-full">
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-slate-100">Watchlists</h1>
        <p className="text-sm text-slate-500 mt-1">Suivi des signaux en temps réel</p>
      </div>
      <WatchlistPanel />
    </div>
  );
}
