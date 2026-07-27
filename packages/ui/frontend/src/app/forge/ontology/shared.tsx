"use client";

import type { ReactNode } from "react";
import { Loader2 } from "lucide-react";
import type { CanonLevel, SimulationScope } from "@/lib/types";

// Shared bits for the /forge/ontology tabs (F2-2 phase 6): labelled form
// fields, enum option lists, and small display helpers.

export const CANON_LEVELS: CanonLevel[] = [
  "proposed",
  "canon",
  "rumor",
  "character_belief",
  "player_knowledge",
  "retconned",
  "superseded",
];

export const SIMULATION_SCOPES: SimulationScope[] = [
  "local",
  "regional",
  "global",
  "cosmic",
];

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <p className="text-[10px] text-slate-600 uppercase tracking-wider mb-1">{label}</p>
      {children}
    </div>
  );
}

export function EnumSelect({
  ariaLabel,
  value,
  onChange,
  options,
  allowAll,
}: {
  ariaLabel: string;
  value: string;
  onChange: (v: string) => void;
  options: readonly string[];
  /** When set, prepends an "All" option with this sentinel value (""). */
  allowAll?: boolean;
}) {
  return (
    <select
      aria-label={ariaLabel}
      className="input-cyber py-1 text-xs"
      value={value}
      onChange={(e) => onChange(e.target.value)}
    >
      {allowAll && <option value="">All</option>}
      {options.map((o) => (
        <option key={o} value={o}>
          {o.replace(/_/g, " ")}
        </option>
      ))}
    </select>
  );
}

export function Tag({ children }: { children: ReactNode }) {
  return <span className="tag-dim capitalize">{children}</span>;
}

export function ListState({
  isLoading,
  isError,
  error,
  isEmpty,
  emptyMessage,
}: {
  isLoading: boolean;
  isError: boolean;
  error?: unknown;
  isEmpty: boolean;
  emptyMessage: string;
}) {
  if (isLoading) {
    return (
      <div className="flex items-center gap-2 text-slate-500 text-sm py-8 justify-center">
        <Loader2 className="w-4 h-4 animate-spin" /> Loading…
      </div>
    );
  }
  if (isError) {
    return (
      <p className="text-sm text-red-300 py-8 text-center">
        Query failed: {(error as Error)?.message ?? "unknown error"}
      </p>
    );
  }
  if (isEmpty) {
    return <p className="text-sm text-slate-600 py-8 text-center">{emptyMessage}</p>;
  }
  return null;
}

/** datetime-local input value → ISO string for the API (null when empty). */
export function localToIso(v: string): string | null {
  if (!v) return null;
  const d = new Date(v);
  return Number.isNaN(d.getTime()) ? null : d.toISOString();
}

/** ISO timestamp → datetime-local input value. */
export function isoToLocal(v: string | null | undefined): string {
  if (!v) return "";
  const d = new Date(v);
  if (Number.isNaN(d.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
