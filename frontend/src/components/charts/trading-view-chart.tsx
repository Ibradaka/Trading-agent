"use client";

import { useEffect, useRef } from "react";
import {
  createChart,
  type IChartApi,
  type ISeriesApi,
  type CandlestickData,
  ColorType,
} from "lightweight-charts";

interface Props {
  ticker: string;
  height?: number;
}

export function TradingViewChart({ ticker, height = 400 }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);

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

    // Resize observer
    const observer = new ResizeObserver(() => {
      if (containerRef.current) {
        chart.applyOptions({ width: containerRef.current.clientWidth });
      }
    });
    if (containerRef.current) observer.observe(containerRef.current);

    return () => {
      observer.disconnect();
      chart.remove();
    };
  }, [height]);

  // Charge les données OHLC depuis l'API backend
  useEffect(() => {
    if (!candleSeriesRef.current) return;

    fetch(`/api/assets/${ticker}/ohlc?timeframe=1d&limit=180`)
      .then((r) => r.json())
      .then((data: CandlestickData[]) => {
        if (Array.isArray(data) && data.length > 0) {
          candleSeriesRef.current?.setData(data);
          chartRef.current?.timeScale().fitContent();
        }
      })
      .catch(() => {
        // Données non disponibles encore — affichage vide
      });
  }, [ticker]);

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <span className="text-sm font-medium text-slate-300">{ticker} — Quotidien</span>
        <div className="flex gap-2 text-xs text-slate-600">
          <span className="text-blue-400">EMA 20</span>
          <span className="text-orange-400">EMA 50</span>
          <span className="text-red-400">EMA 200</span>
        </div>
      </div>
      <div ref={containerRef} className="w-full rounded-lg overflow-hidden" style={{ height }} />
    </div>
  );
}
