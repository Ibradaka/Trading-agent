"use client";

import { useEffect, useRef, useState } from "react";
import {
  createChart,
  type IChartApi,
  type ISeriesApi,
  type CandlestickData,
  ColorType,
} from "lightweight-charts";
import { cn } from "@/lib/utils";

const RANGES = [
  { label: "5J", value: "5d" },
  { label: "1M", value: "1mo" },
  { label: "3M", value: "3mo" },
  { label: "6M", value: "6mo" },
  { label: "1A", value: "1y" },
] as const;

type Range = typeof RANGES[number]["value"];

interface Props {
  ticker: string;
  height?: number;
}

export function TradingViewChart({ ticker, height = 400 }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const [range, setRange] = useState<Range>("1mo");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!containerRef.current) return;

    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: "#0f172a" },
        textColor: "#64748b",
      },
      grid: {
        vertLines: { color: "#1e293b" },
        horzLines: { color: "#1e293b" },
      },
      crosshair: {
        vertLine: { color: "#334155", labelBackgroundColor: "#1e293b" },
        horzLine: { color: "#334155", labelBackgroundColor: "#1e293b" },
      },
      timeScale: {
        borderColor: "#1e293b",
        timeVisible: true,
        secondsVisible: false,
      },
      rightPriceScale: { borderColor: "#1e293b" },
      width: containerRef.current.clientWidth,
      height,
    });

    const candleSeries = chart.addCandlestickSeries({
      upColor: "#10b981",
      downColor: "#ef4444",
      borderUpColor: "#10b981",
      borderDownColor: "#ef4444",
      wickUpColor: "#10b981",
      wickDownColor: "#ef4444",
    });

    chartRef.current = chart;
    candleSeriesRef.current = candleSeries;

    const observer = new ResizeObserver(() => {
      if (containerRef.current) {
        chart.applyOptions({ width: containerRef.current.clientWidth });
      }
    });
    observer.observe(containerRef.current);

    return () => {
      observer.disconnect();
      chart.remove();
    };
  }, [height]);

  useEffect(() => {
    if (!candleSeriesRef.current) return;
    setLoading(true);

    fetch(`/api/assets/${ticker}/chart?range=${range}`)
      .then((r) => r.json())
      .then((data: CandlestickData[]) => {
        if (Array.isArray(data) && data.length > 0) {
          candleSeriesRef.current?.setData(data);
          chartRef.current?.timeScale().fitContent();
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [ticker, range]);

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <span className="text-sm font-medium text-slate-300">{ticker}</span>
        <div className="flex items-center gap-1">
          {RANGES.map((r) => (
            <button
              key={r.value}
              onClick={() => setRange(r.value)}
              className={cn(
                "px-2.5 py-1 text-xs rounded transition-colors",
                range === r.value
                  ? "bg-blue-600/20 text-blue-400 font-medium"
                  : "text-slate-500 hover:text-slate-300"
              )}
            >
              {r.label}
            </button>
          ))}
        </div>
      </div>
      <div className="relative">
        <div ref={containerRef} className="w-full rounded-lg overflow-hidden" style={{ height }} />
        {loading && (
          <div className="absolute inset-0 flex items-center justify-center bg-slate-900/50 rounded-lg">
            <div className="w-4 h-4 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
          </div>
        )}
      </div>
    </div>
  );
}
