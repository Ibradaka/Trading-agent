import { SignalDetailView } from "@/components/signals/signal-detail-view";

interface Props {
  params: { ticker: string };
}

export default function AssetPage({ params }: Props) {
  return <SignalDetailView ticker={params.ticker.toUpperCase()} />;
}
