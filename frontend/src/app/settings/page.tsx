"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, SystemSettings } from "@/lib/api";
import { cn } from "@/lib/utils";
import { ShieldAlert, Bell, Clock, Sliders, AlertTriangle } from "lucide-react";
import { useState, useEffect } from "react";

function Section({ title, icon: Icon, children }: { title: string; icon: React.ElementType; children: React.ReactNode }) {
  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
      <div className="px-5 py-3.5 border-b border-slate-800 flex items-center gap-2.5">
        <Icon className="w-4 h-4 text-slate-400" />
        <h2 className="text-sm font-medium text-slate-200">{title}</h2>
      </div>
      <div className="p-5 space-y-4">{children}</div>
    </div>
  );
}

function Row({ label, sub, children }: { label: string; sub?: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <div>
        <p className="text-sm text-slate-300">{label}</p>
        {sub && <p className="text-xs text-slate-600 mt-0.5">{sub}</p>}
      </div>
      <div className="flex-shrink-0">{children}</div>
    </div>
  );
}

function Toggle({ value, onChange, disabled }: { value: boolean; onChange: (v: boolean) => void; disabled?: boolean }) {
  return (
    <button
      onClick={() => !disabled && onChange(!value)}
      disabled={disabled}
      className={cn(
        "relative w-10 h-5 rounded-full transition-colors duration-200 focus:outline-none",
        value ? "bg-blue-600" : "bg-slate-700",
        disabled && "opacity-40 cursor-not-allowed"
      )}
    >
      <span className={cn(
        "absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white transition-transform duration-200",
        value ? "translate-x-5" : "translate-x-0"
      )} />
    </button>
  );
}

function NumberInput({ value, onChange, min, max, step, unit }: {
  value: number; onChange: (v: number) => void;
  min?: number; max?: number; step?: number; unit?: string;
}) {
  return (
    <div className="flex items-center gap-1.5">
      <input
        type="number"
        className="w-20 bg-slate-800 border border-slate-700 rounded-lg px-2.5 py-1.5 text-sm text-slate-100 text-right focus:outline-none focus:border-blue-500 transition-colors"
        value={value}
        min={min}
        max={max}
        step={step ?? 1}
        onChange={(e) => onChange(Number(e.target.value))}
      />
      {unit && <span className="text-xs text-slate-500">{unit}</span>}
    </div>
  );
}

export default function SettingsPage() {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ["settings"],
    queryFn: api.settings.get,
  });

  const [draft, setDraft] = useState<SystemSettings | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (data && !draft) setDraft(data);
  }, [data, draft]);

  const updateMutation = useMutation({
    mutationFn: api.settings.update,
    onSuccess: (updated) => {
      setDraft(updated);
      qc.setQueryData(["settings"], updated);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    },
  });

  const panicMutation = useMutation({
    mutationFn: api.settings.togglePanic,
    onSuccess: ({ panic_mode }) => {
      setDraft((d) => d ? { ...d, panic_mode } : d);
      qc.invalidateQueries({ queryKey: ["settings"] });
      qc.invalidateQueries({ queryKey: ["system-status"] });
    },
  });

  const set = <K extends keyof SystemSettings>(key: K, val: SystemSettings[K]) =>
    setDraft((d) => d ? { ...d, [key]: val } : d);

  const save = () => {
    if (draft) updateMutation.mutate(draft);
  };

  if (isLoading || !draft) {
    return (
      <div className="flex items-center justify-center h-64">
        <p className="text-slate-500 text-sm">Chargement…</p>
      </div>
    );
  }

  const isPanic = draft.panic_mode;

  return (
    <div className="space-y-6 max-w-3xl">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-xl font-semibold text-slate-100">Configuration</h1>
          <p className="text-sm text-slate-500 mt-1">Paramètres opérationnels du système</p>
        </div>
        <button
          onClick={save}
          disabled={updateMutation.isPending}
          className={cn(
            "px-4 py-2 rounded-lg text-sm font-medium transition-all duration-150",
            saved
              ? "bg-emerald-600/20 text-emerald-400 border border-emerald-800"
              : "bg-blue-600 hover:bg-blue-500 text-white disabled:opacity-50"
          )}
        >
          {saved ? "Sauvegardé ✓" : updateMutation.isPending ? "Sauvegarde…" : "Sauvegarder"}
        </button>
      </div>

      {/* Mode sécurité */}
      <div className={cn(
        "rounded-xl border p-5 transition-colors duration-300",
        isPanic
          ? "bg-red-900/20 border-red-800"
          : "bg-slate-900 border-slate-800"
      )}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <ShieldAlert className={cn("w-5 h-5", isPanic ? "text-red-400" : "text-slate-400")} />
            <div>
              <p className={cn("text-sm font-medium", isPanic ? "text-red-300" : "text-slate-200")}>
                Mode sécurité (Panic)
              </p>
              <p className="text-xs text-slate-500 mt-0.5">
                {isPanic
                  ? "Actif — aucune alerte Telegram envoyée"
                  : "Inactif — alertes Telegram normales"}
              </p>
            </div>
          </div>
          <button
            onClick={() => panicMutation.mutate()}
            disabled={panicMutation.isPending}
            className={cn(
              "px-4 py-2 rounded-lg text-sm font-medium transition-colors",
              isPanic
                ? "bg-red-600 hover:bg-red-500 text-white"
                : "bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700"
            )}
          >
            {isPanic ? "Désactiver" : "Activer"}
          </button>
        </div>
        {isPanic && (
          <div className="mt-3 flex items-center gap-2 text-xs text-red-400">
            <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0" />
            Les agents continuent de calculer. Le tableau de bord reste actif. Aucune recommandation n'est poussée.
          </div>
        )}
      </div>

      {/* Seuils de signal */}
      <Section title="Seuils de signal" icon={Sliders}>
        <Row label="Seuil BUY" sub="Score technique minimum pour générer un signal BUY">
          <NumberInput value={draft.buy_threshold} onChange={(v) => set("buy_threshold", v)} min={50} max={90} step={0.5} unit="/ 100" />
        </Row>
        <Row label="Seuil SELL" sub="Score technique maximum pour générer un signal SELL">
          <NumberInput value={draft.sell_threshold} onChange={(v) => set("sell_threshold", v)} min={10} max={50} step={0.5} unit="/ 100" />
        </Row>
        <Row label="Seuil alerte Telegram" sub="Score composite minimum pour envoyer une alerte">
          <NumberInput value={Math.round(draft.alert_threshold * 100)} onChange={(v) => set("alert_threshold", v / 100)} min={50} max={95} step={1} unit="%" />
        </Row>
        <Row label="Confiance minimum" sub="Niveau de confiance minimum (medium = 45%)">
          <NumberInput value={Math.round(draft.min_confidence * 100)} onChange={(v) => set("min_confidence", v / 100)} min={30} max={80} step={5} unit="%" />
        </Row>
      </Section>

      {/* Alertes Telegram */}
      <Section title="Alertes Telegram" icon={Bell}>
        <Row label="Alertes activées" sub="Active ou suspend toutes les alertes Telegram">
          <Toggle value={draft.telegram_enabled} onChange={(v) => set("telegram_enabled", v)} />
        </Row>
        <Row label="Digest quotidien" sub="Résumé du matin à 08h00 CET">
          <Toggle value={draft.daily_digest} onChange={(v) => set("daily_digest", v)} />
        </Row>
        <Row label="Délai entre alertes" sub="Cooldown par actif — évite les doublons">
          <NumberInput value={draft.cooldown_minutes} onChange={(v) => set("cooldown_minutes", v)} min={15} max={480} step={15} unit="min" />
        </Row>
      </Section>

      {/* Heures silencieuses */}
      <Section title="Heures silencieuses" icon={Clock}>
        <Row label="Début silence" sub="Heure de début (CET) — les alertes sont mises en file">
          <NumberInput value={draft.quiet_start} onChange={(v) => set("quiet_start", v)} min={18} max={23} unit="h CET" />
        </Row>
        <Row label="Fin silence" sub="Heure de fin (CET) — les alertes en attente sont envoyées">
          <NumberInput value={draft.quiet_end} onChange={(v) => set("quiet_end", v)} min={5} max={10} unit="h CET" />
        </Row>
      </Section>
    </div>
  );
}
