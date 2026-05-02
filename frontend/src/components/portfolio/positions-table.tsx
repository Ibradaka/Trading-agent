"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient, useQueries } from "@tanstack/react-query";
import { api, type Position, type AssetQuote } from "@/lib/api";
import { Plus, Pencil, Trash2, Loader2, TrendingUp, TrendingDown, Check, X } from "lucide-react";
import { cn, formatAssetPrice } from "@/lib/utils";

const ACCOUNT_TYPES = ["PEA", "CTO", "PEE", "AUTRE"] as const;
const ACCOUNT_COLORS: Record<string, string> = {
  PEA: "bg-blue-500/10 text-blue-400 border-blue-500/20",
  CTO: "bg-purple-500/10 text-purple-400 border-purple-500/20",
  PEE: "bg-amber-500/10 text-amber-400 border-amber-500/20",
  AUTRE: "bg-slate-500/10 text-slate-400 border-slate-500/30",
};

function computePnL(position: Position, quote: AssetQuote | undefined) {
  if (!quote?.current_price) return null;
  const isGBp = quote.currency === "GBp";
  const current = isGBp ? quote.current_price / 100 : quote.current_price;
  const avg = isGBp ? position.avg_price / 100 : position.avg_price;
  const invested = avg * position.quantity;
  const market = current * position.quantity;
  const pnl = market - invested;
  const pnl_pct = invested > 0 ? (pnl / invested) * 100 : 0;
  const displayCurrency = isGBp ? "GBP" : (quote.currency ?? "");
  return { pnl, pnl_pct, market, invested, displayCurrency };
}

function AccountBadge({ type }: { type: string }) {
  return (
    <span className={cn("text-xs font-medium px-2 py-0.5 rounded border", ACCOUNT_COLORS[type] ?? ACCOUNT_COLORS.AUTRE)}>
      {type}
    </span>
  );
}

function AccountSummaryCard({
  accountType,
  positions,
  quotes,
}: {
  accountType: string;
  positions: Position[];
  quotes: Record<string, AssetQuote | undefined>;
}) {
  const acctPositions = positions.filter((p) => p.account_type === accountType);

  let totalInvested = 0;
  let totalMarket = 0;
  let hasQuotes = false;

  for (const pos of acctPositions) {
    const pnl = computePnL(pos, quotes[pos.ticker]);
    if (pnl) {
      totalInvested += pnl.invested;
      totalMarket += pnl.market;
      hasQuotes = true;
    } else {
      const isGBp = pos.currency === "GBp";
      const avg = isGBp ? pos.avg_price / 100 : pos.avg_price;
      totalInvested += avg * pos.quantity;
    }
  }

  const totalPnL = totalMarket - totalInvested;
  const totalPnLPct = totalInvested > 0 ? (totalPnL / totalInvested) * 100 : 0;
  const positive = totalPnL >= 0;

  return (
    <div className={cn("bg-slate-900 border rounded-xl p-4", acctPositions.length > 0 ? "border-slate-700" : "border-slate-800 opacity-50")}>
      <div className="flex items-center justify-between mb-2">
        <AccountBadge type={accountType} />
        <span className="text-xs text-slate-600">{acctPositions.length} pos.</span>
      </div>
      {acctPositions.length === 0 ? (
        <p className="text-sm text-slate-700">—</p>
      ) : (
        <>
          <p className="text-lg font-mono font-bold text-slate-100">
            {(hasQuotes ? totalMarket : totalInvested).toFixed(2)}
          </p>
          {hasQuotes && (
            <p className={cn("text-xs font-medium font-mono", positive ? "text-emerald-400" : "text-red-400")}>
              {positive ? "+" : ""}{totalPnL.toFixed(2)} ({positive ? "+" : ""}{totalPnLPct.toFixed(2)}%)
            </p>
          )}
          <p className="text-xs text-slate-600 mt-0.5">investi : {totalInvested.toFixed(2)}</p>
        </>
      )}
    </div>
  );
}

function AddPositionForm({ onSuccess, onCancel }: { onSuccess: () => void; onCancel: () => void }) {
  const [ticker, setTicker] = useState("");
  const [accountType, setAccountType] = useState<string>("PEA");
  const [quantity, setQuantity] = useState("");
  const [avgPrice, setAvgPrice] = useState("");
  const [notes, setNotes] = useState("");

  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: api.portfolio.addPosition,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["positions"] });
      onSuccess();
    },
  });

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        mutation.mutate({
          ticker,
          account_type: accountType,
          quantity: parseFloat(quantity),
          avg_price: parseFloat(avgPrice),
          notes: notes || undefined,
        });
      }}
      className="bg-slate-800/40 border border-slate-700 rounded-xl p-4 mb-4"
    >
      <p className="text-sm font-semibold text-slate-300 mb-3">Nouvelle position</p>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div>
          <label className="text-xs text-slate-500">Ticker</label>
          <input
            value={ticker}
            onChange={(e) => setTicker(e.target.value.toUpperCase())}
            placeholder="NVDA"
            required
            className="w-full mt-1 bg-slate-800 border border-slate-700 rounded-lg px-3 py-1.5 text-sm text-slate-100 focus:outline-none focus:border-blue-500 placeholder:text-slate-600"
          />
        </div>
        <div>
          <label className="text-xs text-slate-500">Compte</label>
          <select
            value={accountType}
            onChange={(e) => setAccountType(e.target.value)}
            className="w-full mt-1 bg-slate-800 border border-slate-700 rounded-lg px-3 py-1.5 text-sm text-slate-100 focus:outline-none focus:border-blue-500"
          >
            {ACCOUNT_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        </div>
        <div>
          <label className="text-xs text-slate-500">Quantité</label>
          <input
            type="number"
            step="any"
            min="0"
            value={quantity}
            onChange={(e) => setQuantity(e.target.value)}
            placeholder="10"
            required
            className="w-full mt-1 bg-slate-800 border border-slate-700 rounded-lg px-3 py-1.5 text-sm text-slate-100 focus:outline-none focus:border-blue-500 placeholder:text-slate-600"
          />
        </div>
        <div>
          <label className="text-xs text-slate-500">Prix moyen d'achat</label>
          <input
            type="number"
            step="any"
            min="0"
            value={avgPrice}
            onChange={(e) => setAvgPrice(e.target.value)}
            placeholder="150.00"
            required
            className="w-full mt-1 bg-slate-800 border border-slate-700 rounded-lg px-3 py-1.5 text-sm text-slate-100 focus:outline-none focus:border-blue-500 placeholder:text-slate-600"
          />
        </div>
      </div>
      <div className="mt-3">
        <label className="text-xs text-slate-500">Notes (facultatif)</label>
        <input
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder="Ex : Renforcement après pullback"
          className="w-full mt-1 bg-slate-800 border border-slate-700 rounded-lg px-3 py-1.5 text-sm text-slate-100 focus:outline-none focus:border-blue-500 placeholder:text-slate-600"
        />
      </div>
      {mutation.isError && (
        <p className="text-xs text-red-400 mt-2">
          Erreur : {(mutation.error as Error).message}
        </p>
      )}
      <div className="flex justify-end gap-2 mt-4">
        <button type="button" onClick={onCancel} className="px-3 py-1.5 text-sm text-slate-400 hover:text-slate-200 transition-colors">
          Annuler
        </button>
        <button
          type="submit"
          disabled={mutation.isPending}
          className="flex items-center gap-1.5 px-4 py-1.5 text-sm bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white rounded-lg transition-colors"
        >
          {mutation.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Check className="w-3.5 h-3.5" />}
          Enregistrer
        </button>
      </div>
    </form>
  );
}

function PositionRow({
  position,
  quote,
  onDelete,
}: {
  position: Position;
  quote: AssetQuote | undefined;
  onDelete: (id: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [editData, setEditData] = useState({
    account_type: position.account_type,
    quantity: position.quantity.toString(),
    avg_price: position.avg_price.toString(),
    notes: position.notes ?? "",
  });

  const queryClient = useQueryClient();
  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Parameters<typeof api.portfolio.updatePosition>[1] }) =>
      api.portfolio.updatePosition(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["positions"] });
      setEditing(false);
    },
  });

  const pnl = computePnL(position, quote);
  const positive = pnl ? pnl.pnl >= 0 : true;

  const currentPriceDisplay = (() => {
    if (!quote?.current_price) return "—";
    return formatAssetPrice(quote.current_price, quote.currency);
  })();

  if (editing) {
    return (
      <tr className="border-b border-slate-800 bg-slate-800/30">
        <td className="px-4 py-3 text-sm font-semibold text-slate-200">{position.ticker}</td>
        <td className="px-4 py-3">
          <select
            value={editData.account_type}
            onChange={(e) => setEditData({ ...editData, account_type: e.target.value as Position["account_type"] })}
            className="bg-slate-800 border border-slate-700 rounded px-2 py-1 text-sm text-slate-100 focus:outline-none focus:border-blue-500"
          >
            {ACCOUNT_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        </td>
        <td className="px-4 py-3">
          <input
            type="number"
            step="any"
            value={editData.quantity}
            onChange={(e) => setEditData({ ...editData, quantity: e.target.value })}
            className="w-24 bg-slate-800 border border-slate-700 rounded px-2 py-1 text-sm text-slate-100 focus:outline-none focus:border-blue-500"
          />
        </td>
        <td className="px-4 py-3">
          <input
            type="number"
            step="any"
            value={editData.avg_price}
            onChange={(e) => setEditData({ ...editData, avg_price: e.target.value })}
            className="w-28 bg-slate-800 border border-slate-700 rounded px-2 py-1 text-sm text-slate-100 focus:outline-none focus:border-blue-500"
          />
        </td>
        <td className="px-4 py-3 text-slate-500">—</td>
        <td className="px-4 py-3 text-slate-500">—</td>
        <td className="px-4 py-3">
          <input
            value={editData.notes}
            onChange={(e) => setEditData({ ...editData, notes: e.target.value })}
            className="w-full bg-slate-800 border border-slate-700 rounded px-2 py-1 text-sm text-slate-100 focus:outline-none focus:border-blue-500"
            placeholder="Notes…"
          />
        </td>
        <td className="px-4 py-3">
          <div className="flex gap-1">
            <button
              onClick={() =>
                updateMutation.mutate({
                  id: position.id,
                  data: {
                    account_type: editData.account_type,
                    quantity: parseFloat(editData.quantity),
                    avg_price: parseFloat(editData.avg_price),
                    notes: editData.notes,
                  },
                })
              }
              disabled={updateMutation.isPending}
              className="p-1.5 text-emerald-400 hover:bg-emerald-500/10 rounded"
            >
              <Check className="w-3.5 h-3.5" />
            </button>
            <button onClick={() => setEditing(false)} className="p-1.5 text-slate-400 hover:bg-slate-700 rounded">
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        </td>
      </tr>
    );
  }

  return (
    <tr className="border-b border-slate-800/60 hover:bg-slate-800/30 transition-colors group">
      <td className="px-4 py-3">
        <p className="text-sm font-semibold text-slate-200">{position.ticker}</p>
        <p className="text-xs text-slate-500 truncate max-w-[140px]">{position.asset_name}</p>
      </td>
      <td className="px-4 py-3">
        <AccountBadge type={position.account_type} />
      </td>
      <td className="px-4 py-3 text-sm font-mono text-slate-300">
        {position.quantity.toLocaleString("fr-FR")}
      </td>
      <td className="px-4 py-3 text-sm font-mono text-slate-300">
        {formatAssetPrice(position.avg_price, position.currency)}
      </td>
      <td className="px-4 py-3 text-sm font-mono text-slate-300">{currentPriceDisplay}</td>
      <td className="px-4 py-3">
        {pnl ? (
          <div>
            <p className={cn("text-sm font-mono font-semibold", positive ? "text-emerald-400" : "text-red-400")}>
              {positive ? "+" : ""}{pnl.pnl.toFixed(2)}
            </p>
            <p className={cn("text-xs font-mono", positive ? "text-emerald-400/70" : "text-red-400/70")}>
              {positive ? "+" : ""}{pnl.pnl_pct.toFixed(2)}%
            </p>
          </div>
        ) : (
          <span className="text-slate-600">—</span>
        )}
      </td>
      <td className="px-4 py-3 text-xs text-slate-500 max-w-[120px] truncate">
        {position.notes ?? "—"}
      </td>
      <td className="px-4 py-3">
        <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
          <button onClick={() => setEditing(true)} className="p-1.5 text-slate-400 hover:text-blue-400 hover:bg-blue-500/10 rounded">
            <Pencil className="w-3.5 h-3.5" />
          </button>
          <button onClick={() => onDelete(position.id)} className="p-1.5 text-slate-400 hover:text-red-400 hover:bg-red-500/10 rounded">
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        </div>
      </td>
    </tr>
  );
}

export function PositionsTable() {
  const [showAddForm, setShowAddForm] = useState(false);
  const queryClient = useQueryClient();

  const { data: positions = [], isLoading } = useQuery({
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
      refetchInterval: 60_000,
    })),
  });
  const quoteMap: Record<string, AssetQuote | undefined> = Object.fromEntries(
    uniqueTickers.map((ticker, i) => [ticker, quoteQueries[i].data])
  );

  const deleteMutation = useMutation({
    mutationFn: api.portfolio.deletePosition,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["positions"] }),
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-24">
        <Loader2 className="w-6 h-6 text-slate-600 animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-slate-100">Mon Portefeuille</h1>
          <p className="text-sm text-slate-500 mt-0.5">{positions.length} position{positions.length !== 1 ? "s" : ""} ouvertes</p>
        </div>
        <button
          onClick={() => setShowAddForm(!showAddForm)}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium rounded-lg transition-colors"
        >
          <Plus className="w-4 h-4" />
          Nouvelle position
        </button>
      </div>

      {/* Formulaire ajout */}
      {showAddForm && (
        <AddPositionForm
          onSuccess={() => setShowAddForm(false)}
          onCancel={() => setShowAddForm(false)}
        />
      )}

      {/* Résumé par compte */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {ACCOUNT_TYPES.map((type) => (
          <AccountSummaryCard
            key={type}
            accountType={type}
            positions={positions}
            quotes={quoteMap}
          />
        ))}
      </div>

      {/* Tableau des positions */}
      {positions.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 border border-dashed border-slate-800 rounded-xl">
          <TrendingUp className="w-8 h-8 text-slate-700 mb-3" />
          <p className="text-slate-500 text-sm">Aucune position enregistrée</p>
          <p className="text-slate-700 text-xs mt-1">Cliquez sur "Nouvelle position" pour commencer</p>
        </div>
      ) : (
        <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="border-b border-slate-800 text-xs text-slate-500">
                <th className="px-4 py-3 text-left font-medium">Actif</th>
                <th className="px-4 py-3 text-left font-medium">Compte</th>
                <th className="px-4 py-3 text-left font-medium">Qté</th>
                <th className="px-4 py-3 text-left font-medium">Prix moy.</th>
                <th className="px-4 py-3 text-left font-medium">Prix actuel</th>
                <th className="px-4 py-3 text-left font-medium">P&L</th>
                <th className="px-4 py-3 text-left font-medium">Notes</th>
                <th className="px-4 py-3 text-left font-medium w-16"></th>
              </tr>
            </thead>
            <tbody>
              {positions.map((pos) => (
                <PositionRow
                  key={pos.id}
                  position={pos}
                  quote={quoteMap[pos.ticker]}
                  onDelete={(id) => deleteMutation.mutate(id)}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
