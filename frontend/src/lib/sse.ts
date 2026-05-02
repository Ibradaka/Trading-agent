"use client";

import { useEffect, useRef, useCallback } from "react";

const SSE_URL = "/api/stream/signals";
const MAX_RETRY_DELAY = 30_000;
const INITIAL_RETRY_DELAY = 1_000;

export type SSEEventType = "signal_updated" | "price_updated" | "agent_status" | "update";

export interface SSEMessage<T = unknown> {
  type: SSEEventType;
  ticker?: string;
  data: T;
  timestamp?: string;
}

type SSEHandler<T = unknown> = (message: SSEMessage<T>) => void;

export function useSSE(onMessage: SSEHandler, enabled = true) {
  const eventSourceRef = useRef<EventSource | null>(null);
  const retryDelayRef = useRef(INITIAL_RETRY_DELAY);
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const connect = useCallback(() => {
    if (!enabled) return;

    const es = new EventSource(SSE_URL);
    eventSourceRef.current = es;

    es.onopen = () => {
      retryDelayRef.current = INITIAL_RETRY_DELAY; // reset backoff on success
    };

    const handleEvent = (event: MessageEvent, type: SSEEventType) => {
      try {
        const data = JSON.parse(event.data);
        onMessage({ type, ticker: data.ticker, data, timestamp: new Date().toISOString() });
      } catch {
        // ignore malformed events
      }
    };

    es.addEventListener("signal_updated", (e) => handleEvent(e as MessageEvent, "signal_updated"));
    es.addEventListener("price_updated", (e) => handleEvent(e as MessageEvent, "price_updated"));
    es.addEventListener("agent_status", (e) => handleEvent(e as MessageEvent, "agent_status"));
    es.onmessage = (e) => handleEvent(e, "update");

    es.onerror = () => {
      es.close();
      eventSourceRef.current = null;

      // Reconnexion avec exponential backoff
      retryTimerRef.current = setTimeout(() => {
        retryDelayRef.current = Math.min(retryDelayRef.current * 2, MAX_RETRY_DELAY);
        connect();
      }, retryDelayRef.current);
    };
  }, [enabled, onMessage]);

  useEffect(() => {
    connect();
    return () => {
      eventSourceRef.current?.close();
      if (retryTimerRef.current) clearTimeout(retryTimerRef.current);
    };
  }, [connect]);
}
