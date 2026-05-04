"use client";

import { RefreshCw, Wifi, WifiOff } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { formatDistanceToNow } from "date-fns";
import { fr } from "date-fns/locale";
import { useState, useEffect } from "react";
import { cn } from "@/lib/utils";

export function Header() {
  const [lastUpdate] = useState(new Date());

  const { data: health, isError } = useQuery({
    queryKey: ["health"],
    queryFn: api.health,
    refetchInterval: 30_000,
  });

  const isOnline = !!health && !isError;

  return (
    <header className="h-14 flex items-center justify-between px-6 bg-slate-900 border-b border-slate-800 flex-shrink-0">
      <div className="flex items-center gap-3">
        <div className={cn("flex items-center gap-1.5", isOnline ? "text-emerald-400" : "text-red-400")}>
          {isOnline ? <Wifi className="w-4 h-4" /> : <WifiOff className="w-4 h-4" />}
          <span className="text-xs">{isOnline ? "Connecté" : "Hors ligne"}</span>
        </div>
        <span className="text-slate-700">|</span>
        <span className="text-xs text-slate-500">
          Mis à jour {formatDistanceToNow(lastUpdate, { locale: fr, addSuffix: true })}
        </span>
      </div>

      <div className="flex items-center gap-3">
        <button
          className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-slate-100 transition-colors"
          title="Rafraîchir manuellement"
        >
          <RefreshCw className="w-3.5 h-3.5" />
          Rafraîchir
        </button>

        {/* Heure marché */}
        <MarketStatus />
      </div>
    </header>
  );
}

function MarketStatus() {
  const [isOpen, setIsOpen] = useState<boolean | null>(null);

  useEffect(() => {
    const check = () => {
      const now = new Date();
      const day = now.getDay();
      const isWeekend = day === 0 || day === 6;
      const timeInMinutes = now.getHours() * 60 + now.getMinutes();
      setIsOpen(!isWeekend && timeInMinutes >= 9 * 60 && timeInMinutes <= 17 * 60 + 30);
    };
    check();
    const id = setInterval(check, 60_000);
    return () => clearInterval(id);
  }, []);

  if (isOpen === null) return null;

  return (
    <div className={cn("flex items-center gap-1.5 text-xs px-2 py-1 rounded", isOpen ? "text-emerald-400 bg-emerald-500/10" : "text-slate-500 bg-slate-800")}>
      <span className={cn("w-1.5 h-1.5 rounded-full", isOpen ? "bg-emerald-400 animate-pulse" : "bg-slate-600")} />
      {isOpen ? "Marché ouvert" : "Marché fermé"}
    </div>
  );
}
