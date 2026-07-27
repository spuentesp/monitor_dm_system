"use client";

/**
 * Formal world-coverage panel (F2-1 wave 2 — FORGE_EXPANSION.md §2).
 *
 * Renders the 8 coverage dimensions from `GET /architect/{id}/coverage` as
 * cards: status badge (missing/thin/ok), key counts, and an actionable gap
 * list. Clicking a gap pre-fills the architect composer with a suggested
 * prompt (`promptForGap`). Mechanics / random-tables cards render muted as
 * "not required" when the world has no mechanical-play / procedural intent;
 * the settings popover exposes those applicability toggles.
 */

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  BookOpen,
  CheckCircle2,
  Compass,
  Dices,
  Fingerprint,
  Lightbulb,
  Link2,
  Loader2,
  Network,
  ScrollText,
  Settings2,
  Shapes,
  XCircle,
} from "lucide-react";
import { architectApi } from "@/lib/api";
import { ARCHITECT_KEYS } from "@/lib/query-keys";
import { promptForGap } from "@/lib/coverage-prompts";
import type {
  CoverageGap,
  CoverageStatus,
  DimensionCoverage,
  WorldCoverage,
} from "@/lib/types";
import { cn } from "@/lib/utils";

// ─── Status idiom (icon + text, never color-only) ─────────────

const STATUS_CONFIG: Record<
  CoverageStatus,
  { label: string; icon: React.ElementType; text: string; border: string }
> = {
  missing: {
    label: "Missing",
    icon: XCircle,
    text: "text-red-400",
    border: "border-red-500/20",
  },
  thin: {
    label: "Thin",
    icon: AlertTriangle,
    text: "text-amber-400",
    border: "border-amber-500/20",
  },
  ok: {
    label: "OK",
    icon: CheckCircle2,
    text: "text-emerald-400",
    border: "border-emerald-500/20",
  },
};

export function StatusBadge({ status }: { status: CoverageStatus }) {
  const cfg = STATUS_CONFIG[status];
  const Icon = cfg.icon;
  return (
    <span className={cn("inline-flex items-center gap-1 text-[10px] font-medium", cfg.text)}>
      <Icon className="w-3 h-3" />
      {cfg.label}
    </span>
  );
}

// ─── Gap list (actionable) ────────────────────────────────────

function GapList({
  gaps,
  onSuggestGap,
}: {
  gaps: CoverageGap[];
  onSuggestGap: (prompt: string) => void;
}) {
  if (gaps.length === 0) return null;
  return (
    <ul className="space-y-1">
      {gaps.map((gap) => (
        <li key={gap.code}>
          <button
            type="button"
            onClick={() => onSuggestGap(promptForGap(gap))}
            title="Suggest a prompt for the Architect"
            className="w-full text-left flex items-start gap-1.5 rounded px-1.5 py-1 text-[10px] text-slate-400 hover:text-purple-200 hover:bg-purple-500/10 transition-colors group"
          >
            <Lightbulb className="w-3 h-3 mt-px flex-shrink-0 text-amber-500/70 group-hover:text-amber-300" />
            <span className="leading-snug">{gap.message}</span>
          </button>
        </li>
      ))}
    </ul>
  );
}

// ─── Dimension card ───────────────────────────────────────────

interface DimensionSpec {
  key: string;
  label: string;
  icon: React.ElementType;
  iconColor: string;
  dimension: DimensionCoverage;
  /** Key counts / facts shown under the card title. */
  stats: Array<[string, string]>;
  /** When false the dimension is not applicable to this world's intent. */
  applicable: boolean;
  notApplicableReason?: string;
}

function DimensionCard({
  spec,
  onSuggestGap,
}: {
  spec: DimensionSpec;
  onSuggestGap: (prompt: string) => void;
}) {
  const Icon = spec.icon;

  if (!spec.applicable) {
    return (
      <div className="rounded-lg border border-white/5 bg-white/[0.02] px-3 py-2 opacity-50">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-1.5 min-w-0">
            <Icon className={cn("w-3.5 h-3.5 flex-shrink-0", spec.iconColor)} />
            <span className="text-[11px] font-medium text-slate-400 truncate">{spec.label}</span>
          </div>
          <span className="text-[10px] text-slate-600 italic">Not required</span>
        </div>
        {spec.notApplicableReason && (
          <p className="text-[10px] text-slate-700 mt-1">{spec.notApplicableReason}</p>
        )}
      </div>
    );
  }

  const cfg = STATUS_CONFIG[spec.dimension.status];
  return (
    <div className={cn("rounded-lg border bg-white/[0.03] px-3 py-2 space-y-1.5", cfg.border)}>
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5 min-w-0">
          <Icon className={cn("w-3.5 h-3.5 flex-shrink-0", spec.iconColor)} />
          <span className="text-[11px] font-medium text-slate-200 truncate">{spec.label}</span>
        </div>
        <StatusBadge status={spec.dimension.status} />
      </div>
      {spec.stats.length > 0 && (
        <div className="flex flex-wrap gap-x-3 gap-y-0.5">
          {spec.stats.map(([label, value]) => (
            <span key={label} className="text-[10px] text-slate-500">
              <span className="text-slate-600">{label}:</span> {value}
            </span>
          ))}
        </div>
      )}
      <GapList gaps={spec.dimension.gaps} onSuggestGap={onSuggestGap} />
    </div>
  );
}

// ─── Per-dimension stats ──────────────────────────────────────

function histogramSummary(histogram: Record<string, Record<string, number>>): string {
  const totals: Record<string, number> = {};
  for (const levels of Object.values(histogram)) {
    for (const [level, count] of Object.entries(levels)) {
      totals[level] = (totals[level] ?? 0) + count;
    }
  }
  return Object.entries(totals)
    .map(([level, count]) => `${count} ${level}`)
    .join(" · ");
}

function countMapSummary(map: Record<string, number>, limit = 4): string {
  const entries = Object.entries(map);
  if (entries.length === 0) return "—";
  const shown = entries.slice(0, limit).map(([k, v]) => `${k} ${v}`);
  return entries.length > limit ? `${shown.join(", ")}…` : shown.join(", ");
}

function dimensionSpecs(coverage: WorldCoverage): DimensionSpec[] {
  const { identity, entity_taxonomy, fact_taxonomy, axioms, relationships, mechanics, random_tables, provenance } =
    coverage;
  return [
    {
      key: "identity",
      label: "Identity",
      icon: Fingerprint,
      iconColor: "text-purple-400",
      dimension: identity,
      applicable: true,
      stats: [
        ["Name", identity.name ?? "—"],
        ["Genre", identity.genre ?? "—"],
        ["Tone", identity.tone ?? "—"],
        ["System", identity.default_system_name ?? "—"],
      ],
    },
    {
      key: "entity_taxonomy",
      label: "Entities",
      icon: Shapes,
      iconColor: "text-cyan-400",
      dimension: entity_taxonomy,
      applicable: true,
      stats: [
        ["Total", String(entity_taxonomy.total)],
        ["Types", countMapSummary(entity_taxonomy.by_type)],
        ["Detail", histogramSummary(entity_taxonomy.detail_histogram) || "—"],
        ["Stubs", String(entity_taxonomy.stub_count)],
      ],
    },
    {
      key: "fact_taxonomy",
      label: "Facts",
      icon: BookOpen,
      iconColor: "text-teal-400",
      dimension: fact_taxonomy,
      applicable: true,
      stats: [
        ["Active", String(fact_taxonomy.total_active)],
        ["Types", countMapSummary(fact_taxonomy.by_type)],
        ["Conflict", String(fact_taxonomy.current_conflict)],
        ["Historical", String(fact_taxonomy.historical_founding)],
      ],
    },
    {
      key: "axioms",
      label: "Axioms",
      icon: ScrollText,
      iconColor: "text-amber-400",
      dimension: axioms,
      applicable: true,
      stats: [
        ["Total", String(axioms.total)],
        ["Domains", axioms.domains.length > 0 ? axioms.domains.join(", ") : "—"],
      ],
    },
    {
      key: "relationships",
      label: "Relationships",
      icon: Network,
      iconColor: "text-emerald-400",
      dimension: relationships,
      applicable: true,
      stats: [
        ["Edges", String(relationships.total_edges)],
        ["Categories", countMapSummary(relationships.by_category)],
        ["Isolated", String(relationships.isolated_entities.length)],
      ],
    },
    {
      key: "mechanics",
      label: "Game System",
      icon: Dices,
      iconColor: "text-orange-400",
      dimension: mechanics,
      applicable: mechanics.applicable,
      notApplicableReason: "Enable “Mechanical play” in settings if this world needs a rules system.",
      stats: [
        ["System", mechanics.system_name ?? "—"],
        ["Attributes", String(mechanics.attribute_count)],
        ["Skills", String(mechanics.skill_count)],
        ["Resolution", String(mechanics.resolution_mechanic_count)],
        ["Conditions", String(mechanics.condition_count)],
      ],
    },
    {
      key: "random_tables",
      label: "Random Tables",
      icon: Compass,
      iconColor: "text-pink-400",
      dimension: random_tables,
      applicable: random_tables.applicable,
      notApplicableReason: "Enable “Procedural generation” in settings if this world relies on random tables.",
      stats: [
        ["Total", String(random_tables.total)],
        ["Types", countMapSummary(random_tables.by_type)],
        ["Linked", `${random_tables.linked_to_universe + random_tables.linked_to_system}`],
      ],
    },
    {
      key: "provenance",
      label: "Provenance",
      icon: Link2,
      iconColor: "text-slate-400",
      dimension: provenance,
      applicable: true,
      stats: [
        ["Primitives", String(provenance.primitives_total)],
        ["Sourced", String(provenance.with_source_refs)],
        [
          "Confidence",
          provenance.avg_confidence !== null ? provenance.avg_confidence.toFixed(2) : "—",
        ],
        ["Pending", String(provenance.pending_review)],
      ],
    },
  ];
}

// ─── Panel ────────────────────────────────────────────────────

export function CoveragePanel({
  universeId,
  onSuggestGap,
}: {
  universeId: string | null;
  onSuggestGap: (prompt: string) => void;
}) {
  const [requireMechanics, setRequireMechanics] = useState(false);
  const [requireRandomTables, setRequireRandomTables] = useState(false);
  const [showSettings, setShowSettings] = useState(false);

  const opts = { requireMechanics, requireRandomTables };
  const { data: coverage, isLoading } = useQuery({
    queryKey: ARCHITECT_KEYS.coverage(universeId, opts),
    queryFn: () =>
      architectApi.coverage(universeId!, {
        require_mechanics: requireMechanics,
        require_random_tables: requireRandomTables,
      }),
    enabled: Boolean(universeId),
  });

  if (!universeId) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center px-4 space-y-2">
        <Compass className="w-8 h-8 text-slate-700" />
        <p className="text-xs text-slate-600">Select a universe to see coverage</p>
      </div>
    );
  }
  if (isLoading || !coverage) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="w-5 h-5 text-slate-600 animate-spin" />
      </div>
    );
  }

  return (
    <div className="p-3 space-y-3">
      {/* Rollup: floor + overall status + applicability toggles */}
      <div className="flex items-center gap-2 flex-wrap">
        <StatusBadge status={coverage.overall_status} />
        <span
          className={cn(
            "inline-flex items-center gap-1 text-[10px] font-medium",
            coverage.floor_met ? "text-emerald-400" : "text-red-400",
          )}
        >
          {coverage.floor_met ? (
            <CheckCircle2 className="w-3 h-3" />
          ) : (
            <XCircle className="w-3 h-3" />
          )}
          {coverage.floor_met ? "Floor met" : "Floor not met"}
        </span>
        <span className="text-[10px] text-slate-700">identity + ≥1 axiom</span>
        <button
          type="button"
          onClick={() => setShowSettings((p) => !p)}
          aria-label="Coverage settings"
          title="Coverage settings"
          className={cn(
            "ml-auto p-1 rounded transition-colors",
            showSettings ? "text-purple-300" : "text-slate-600 hover:text-slate-300",
          )}
        >
          <Settings2 className="w-3.5 h-3.5" />
        </button>
      </div>

      {showSettings && (
        <div className="rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2 space-y-1.5">
          <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wide">
            World intent
          </p>
          <label className="flex items-center gap-2 text-[11px] text-slate-400 cursor-pointer">
            <input
              type="checkbox"
              checked={requireMechanics}
              onChange={(e) => setRequireMechanics(e.target.checked)}
              className="accent-purple-500"
            />
            Mechanical play (require game system)
          </label>
          <label className="flex items-center gap-2 text-[11px] text-slate-400 cursor-pointer">
            <input
              type="checkbox"
              checked={requireRandomTables}
              onChange={(e) => setRequireRandomTables(e.target.checked)}
              className="accent-purple-500"
            />
            Procedural generation (require random tables)
          </label>
        </div>
      )}

      <div className="space-y-2">
        {dimensionSpecs(coverage).map((spec) => (
          <DimensionCard key={spec.key} spec={spec} onSuggestGap={onSuggestGap} />
        ))}
      </div>
    </div>
  );
}
