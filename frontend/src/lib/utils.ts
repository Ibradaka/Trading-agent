import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";
import type { Signal } from "./api";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function scoreToColor(score: number): string {
  if (score >= 70) return "text-emerald-400";
  if (score >= 50) return "text-amber-400";
  return "text-red-400";
}

export function signalToClasses(signal: Signal): string {
  if (signal.signal_type === "BUY" && signal.strength === "strong") return "signal-buy-strong";
  if (signal.signal_type === "BUY") return "signal-buy-weak";
  if (signal.signal_type === "SELL" && signal.strength === "strong") return "signal-sell-strong";
  if (signal.signal_type === "SELL") return "signal-sell-weak";
  return "signal-hold";
}

export function signalLabel(type: string, strength: string): string {
  if (type === "BUY" && strength === "strong") return "ACHAT FORT";
  if (type === "BUY") return "ACHAT";
  if (type === "SELL" && strength === "strong") return "VENTE FORTE";
  if (type === "SELL") return "VENTE";
  return "NEUTRE";
}

export function formatPrice(price: number, currency = "EUR"): string {
  return new Intl.NumberFormat("fr-FR", {
    style: "currency",
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(price);
}

export function formatScore(score: number): string {
  return `${Math.round(score)}/100`;
}
