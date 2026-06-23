"use client";

/**
 * Pack Editor (MP-4)
 *
 * Entry points (via ?mode= query param):
 *   slice  — select a subset of ?pack= to save as a new pack
 *   merge  — combine ?pack= with additional packs (redirected here from Merge modal)
 *
 * Clone is handled inline in forge/page.tsx via the clone mutation.
 * This page covers slice (item selection) and acts as a review surface
 * for the produced working copy before saving.
 */

import { Suspense, useState, useMemo } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  BookOpen,
  Check,
  FlaskConical,
  GitBranch,
  Globe2,
  Loader2,
  MapPin,
  Package,
  Save,
  Scissors,
  Scroll,
  Search,
  Sparkles,
  Users,
  X,
} from "lucide-react";
import { DialogFooter, DialogShell } from "@/components/DialogShell";
import { ingestApi } from "@/lib/api";
import { ENTITY_TYPE_CONFIG, FORGE_TABS } from "@/lib/forge";
import type { ExtractedAxiom, ExtractedEntity, ExtractedLoreFact, KnowledgePack } from "@/lib/types";
import { cn } from "@/lib/utils";

// ─── Selectable item row ──────────────────────────────────────

function SelectableEntityRow({
  entity,
  index,
  selected,
  onToggle,
}: {
  entity: ExtractedEntity;
  index: number;
  selected: boolean;
  onToggle: (i: number) => void;
}) {
  const cfg = ENTITY_TYPE_CONFIG[entity.entity_type] ?? ENTITY_TYPE_CONFIG.concept;
  const Icon = cfg.icon;

  return (
    <label className={cn(
      "flex gap-3 px-4 py-3 border-b border-border cursor-pointer transition-colors",
      selected ? "bg-accent-primary/5" : "hover:bg-bg-hover",
    )}>
      <div className={cn(
        "h-4 w-4 mt-0.5 shrink-0 rounded border flex items-center justify-center",
        selected ? "bg-accent-primary border-accent-primary" : "border-border",
      )}>
        {selected && <Check className="h-3 w-3 text-white" />}
      </div>
      <input type="checkbox" className="sr-only" checked={selected} onChange={() => onToggle(index)} />
      <Icon className={cn("h-4 w-4 mt-0.5 shrink-0", cfg.color)} />
      <div className="flex-1 min-w-0 space-y-0.5">
        <div className="flex items-center gap-2">
          <span className={cn("text-[10px] px-1.5 py-0.5 rounded border", cfg.tag)}>{entity.entity_type}</span>
          <span className="font-semibold text-fg-primary text-sm">{entity.name}</span>
        </div>
        {entity.description && (
          <p className="text-xs text-fg-secondary truncate">{entity.description}</p>
        )}
      </div>
    </label>
  );
}

function SelectableAxiomRow({
  axiom,
  index,
  selected,
  onToggle,
}: {
  axiom: ExtractedAxiom;
  index: number;
  selected: boolean;
  onToggle: (i: number) => void;
}) {
  return (
    <label className={cn(
      "flex gap-3 px-4 py-3 border-b border-border cursor-pointer transition-colors",
      selected ? "bg-accent-primary/5" : "hover:bg-bg-hover",
    )}>
      <div className={cn(
        "h-4 w-4 mt-0.5 shrink-0 rounded border flex items-center justify-center",
        selected ? "bg-accent-primary border-accent-primary" : "border-border",
      )}>
        {selected && <Check className="h-3 w-3 text-white" />}
      </div>
      <input type="checkbox" className="sr-only" checked={selected} onChange={() => onToggle(index)} />
      <Sparkles className="h-4 w-4 mt-0.5 shrink-0 text-purple-400" />
      <div className="flex-1 min-w-0 space-y-0.5">
        {axiom.domain && <span className="text-[10px] tag-purple px-1.5 py-0.5 rounded border">{axiom.domain}</span>}
        <p className="text-sm text-fg-primary">{axiom.statement}</p>
      </div>
    </label>
  );
}

function SelectableLoreRow({
  fact,
  index,
  selected,
  onToggle,
}: {
  fact: ExtractedLoreFact;
  index: number;
  selected: boolean;
  onToggle: (i: number) => void;
}) {
  return (
    <label className={cn(
      "flex gap-3 px-4 py-3 border-b border-border cursor-pointer transition-colors",
      selected ? "bg-accent-primary/5" : "hover:bg-bg-hover",
    )}>
      <div className={cn(
        "h-4 w-4 mt-0.5 shrink-0 rounded border flex items-center justify-center",
        selected ? "bg-accent-primary border-accent-primary" : "border-border",
      )}>
        {selected && <Check className="h-3 w-3 text-white" />}
      </div>
      <input type="checkbox" className="sr-only" checked={selected} onChange={() => onToggle(index)} />
      <BookOpen className="h-4 w-4 mt-0.5 shrink-0 text-amber-400" />
      <p className="flex-1 text-sm text-fg-primary">{fact.statement}</p>
    </label>
  );
}

// ─── Save modal ───────────────────────────────────────────────

function SaveModal({
  mode,
  onSave,
  onClose,
  saving,
}: {
  mode: string;
  onSave: (name: string, withLineage: boolean) => void;
  onClose: () => void;
  saving: boolean;
}) {
  const [name, setName] = useState("");
  const [withLineage, setWithLineage] = useState(true);

  return (
    <DialogShell
      title="Save Pack"
      icon={Save}
      onClose={onClose}
      footer={
        <DialogFooter>
          <button className="btn-ghost" onClick={onClose}>Cancel</button>
          <button
            className="btn-primary"
            disabled={!name.trim() || saving}
            onClick={() => onSave(name, withLineage)}
          >
            {saving
              ? <Loader2 className="h-4 w-4 animate-spin" />
              : <><Save className="h-4 w-4" /> Save Pack</>}
          </button>
        </DialogFooter>
      }
    >
      <div className="p-4 space-y-3">
        <div className="space-y-1">
          <label className="text-xs text-fg-muted">Pack name *</label>
          <input
            autoFocus
            className="input-base w-full text-sm"
            value={name}
            onChange={e => setName(e.target.value)}
            placeholder="My sliced pack"
            onKeyDown={e => { if (e.key === "Enter" && name.trim()) onSave(name, withLineage); }}
          />
        </div>
        <label className="flex items-center gap-2 cursor-pointer">
          <div
            className={cn(
              "h-4 w-4 rounded border flex items-center justify-center shrink-0",
              withLineage ? "bg-accent-primary border-accent-primary" : "border-border",
            )}
            onClick={() => setWithLineage(v => !v)}
          >
            {withLineage && <Check className="h-3 w-3 text-white" />}
          </div>
          <input type="checkbox" className="sr-only" checked={withLineage} onChange={() => setWithLineage(v => !v)} />
          <div>
            <p className="text-xs text-fg-primary">Save with lineage</p>
            <p className="text-[10px] text-fg-muted">Records the source pack ID in parent_pack_ids</p>
          </div>
        </label>
      </div>
    </DialogShell>
  );
}

// ─── Editor page ──────────────────────────────────────────────

type TabId = "entities" | "axioms" | "lore" | "templates" | "tables";

const TABS = FORGE_TABS.filter((tab) => tab.id !== "rules" && tab.id !== "profile");

function PackEditorPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const qc = useQueryClient();

  const packId = searchParams.get("pack") ?? "";
  const mode = (searchParams.get("mode") ?? "slice") as "slice";

  const [activeTab, setActiveTab] = useState<TabId>("entities");
  const [search, setSearch] = useState("");
  const [selectedEntities, setSelectedEntities] = useState<Set<number>>(new Set());
  const [selectedAxioms, setSelectedAxioms]     = useState<Set<number>>(new Set());
  const [selectedLore, setSelectedLore]         = useState<Set<number>>(new Set());
  const [showSave, setShowSave] = useState(false);

  const { data: pack, isLoading } = useQuery({
    queryKey: ["pack", packId],
    queryFn: () => ingestApi.getPack(packId),
    enabled: !!packId,
    staleTime: 60_000,
  });

  const sliceMutation = useMutation({
    mutationFn: ({ name, withLineage }: { name: string; withLineage: boolean }) =>
      ingestApi.slicePack(packId, {
        name,
        entity_indices: Array.from(selectedEntities),
        axiom_indices: Array.from(selectedAxioms),
        lore_indices: Array.from(selectedLore),
        with_lineage: withLineage,
      }),
    onSuccess: (saved) => {
      qc.invalidateQueries({ queryKey: ["forge-packs"] });
      router.push(`/forge?pack=${saved.id}`);
    },
  });

  const selectAllEntities = () =>
    setSelectedEntities(new Set(pack?.entity_archetypes.map((_, i) => i) ?? []));
  const selectAllAxioms = () =>
    setSelectedAxioms(new Set(pack?.axioms.map((_, i) => i) ?? []));
  const selectAllLore = () =>
    setSelectedLore(new Set(pack?.lore_facts.map((_, i) => i) ?? []));
  const clearAllEntities = () => setSelectedEntities(new Set());
  const clearAllAxioms   = () => setSelectedAxioms(new Set());
  const clearAllLore     = () => setSelectedLore(new Set());

  const q = search.toLowerCase();

  const filteredEntities = useMemo(
    () => (pack?.entity_archetypes ?? [])
      .map((e, i) => [e, i] as [ExtractedEntity, number])
      .filter(([e]) => !q || e.name.toLowerCase().includes(q) || e.description.toLowerCase().includes(q)),
    [pack, q],
  );

  const filteredAxioms = useMemo(
    () => (pack?.axioms ?? [])
      .map((a, i) => [a, i] as [ExtractedAxiom, number])
      .filter(([a]) => !q || a.statement.toLowerCase().includes(q)),
    [pack, q],
  );

  const filteredLore = useMemo(
    () => (pack?.lore_facts ?? [])
      .map((f, i) => [f, i] as [ExtractedLoreFact, number])
      .filter(([f]) => !q || f.statement.toLowerCase().includes(q)),
    [pack, q],
  );

  const totalSelected = selectedEntities.size + selectedAxioms.size + selectedLore.size;

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="h-6 w-6 animate-spin text-fg-muted" />
      </div>
    );
  }

  if (!pack) {
    return (
      <div className="flex items-center justify-center h-full">
        <p className="text-sm text-fg-muted">Pack not found.</p>
      </div>
    );
  }

  if (pack.status === "draft") {
    return (
      <div className="flex items-center justify-center h-full px-6">
        <div className="max-w-lg rounded-2xl border border-amber-500/20 bg-amber-500/5 p-6 text-center space-y-3">
          <Loader2 className="h-6 w-6 animate-spin text-amber-300 mx-auto" />
          <h2 className="text-sm font-semibold text-fg-primary">Pack is still being built</h2>
          <p className="text-sm text-fg-secondary">
            `pack.status` is still `draft`, so this source remains read-only until the ingestion job finishes.
            Return to the Forge Jobs tab to watch progress.
          </p>
          <button className="btn-ghost mx-auto" onClick={() => router.push("/forge")}>Back to Forge</button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div className="border-b border-border px-5 py-3 flex items-center gap-3">
        <button className="btn-ghost p-1.5" onClick={() => router.back()} title="Back">
          <ArrowLeft className="h-4 w-4" />
        </button>
        <Scissors className="h-4 w-4 text-amber-400" />
        <div className="flex-1 min-w-0">
          <h1 className="text-sm font-bold text-fg-primary">
            {mode === "slice" ? "Slice Pack" : "Pack Editor"}
          </h1>
          <p className="text-xs text-fg-muted truncate">
            Source: <span className="text-fg-secondary">{pack.name}</span>
            {" · "}{pack.entity_count}E · {pack.axiom_count}A · {pack.lore_fact_count}L
          </p>
        </div>
        {mode === "slice" && (
          <p className="text-xs text-fg-muted">
            <span className={cn("font-semibold", totalSelected > 0 ? "text-accent-primary" : "")}>
              {totalSelected}
            </span>{" "}
            items selected
          </p>
        )}
        <button
          className="btn-primary text-xs gap-1.5"
          disabled={totalSelected === 0}
          onClick={() => setShowSave(true)}
        >
          <Save className="h-3.5 w-3.5" /> Save as New Pack
        </button>
      </div>

      {/* Tabs + search */}
      <div className="border-b border-border flex items-center gap-1 px-4 pt-2 bg-bg-base">
        {TABS.map(tab => {
          const count =
            tab.id === "entities" ? (pack.entity_count) :
            tab.id === "axioms"   ? (pack.axiom_count)  :
            pack.lore_fact_count;
          const sel =
            tab.id === "entities" ? selectedEntities.size :
            tab.id === "axioms"   ? selectedAxioms.size   :
            selectedLore.size;
          return (
            <button
              key={tab.id}
              onClick={() => { setActiveTab(tab.id); setSearch(""); }}
              className={cn(
                "flex items-center gap-1.5 px-3 py-2 text-xs font-medium border-b-2 -mb-px transition-colors",
                activeTab === tab.id
                  ? "border-accent-primary text-accent-primary"
                  : "border-transparent text-fg-muted hover:text-fg-secondary",
              )}
            >
              <tab.icon className="h-3.5 w-3.5" />
              {tab.label}
              <span className="text-[10px] bg-bg-hover rounded px-1">{count}</span>
              {sel > 0 && (
                <span className="text-[10px] bg-accent-primary/20 text-accent-primary rounded px-1">
                  {sel} ✓
                </span>
              )}
            </button>
          );
        })}

        {/* Quick select/clear */}
        <div className="ml-auto flex items-center gap-1 pb-1">
          <button
            className="text-[10px] text-fg-muted hover:text-fg-secondary px-2 py-0.5 rounded border border-border"
            onClick={() => {
              if (activeTab === "entities") selectAllEntities();
              else if (activeTab === "axioms") selectAllAxioms();
              else selectAllLore();
            }}
          >Select all</button>
          <button
            className="text-[10px] text-fg-muted hover:text-fg-secondary px-2 py-0.5 rounded border border-border"
            onClick={() => {
              if (activeTab === "entities") clearAllEntities();
              else if (activeTab === "axioms") clearAllAxioms();
              else clearAllLore();
            }}
          >Clear</button>
        </div>
      </div>

      {/* Search */}
      <div className="px-4 py-2 border-b border-border bg-bg-base">
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-fg-muted" />
          <input
            className="input-base pl-8 w-full text-xs h-7"
            placeholder={`Search ${activeTab}…`}
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
          {search && (
            <button className="absolute right-2 top-1/2 -translate-y-1/2" onClick={() => setSearch("")}>
              <X className="h-3 w-3 text-fg-muted" />
            </button>
          )}
        </div>
      </div>

      {/* Item list */}
      <div className="flex-1 overflow-y-auto">
        {activeTab === "entities" && (
          filteredEntities.length === 0
            ? <p className="text-xs text-fg-muted text-center py-10">No entities match.</p>
            : filteredEntities.map(([e, i]) => (
              <SelectableEntityRow
                key={i}
                entity={e}
                index={i}
                selected={selectedEntities.has(i)}
                onToggle={idx => setSelectedEntities(prev => {
                  const n = new Set(prev);
                  n.has(idx) ? n.delete(idx) : n.add(idx);
                  return n;
                })}
              />
            ))
        )}
        {activeTab === "axioms" && (
          filteredAxioms.length === 0
            ? <p className="text-xs text-fg-muted text-center py-10">No axioms match.</p>
            : filteredAxioms.map(([a, i]) => (
              <SelectableAxiomRow
                key={i}
                axiom={a}
                index={i}
                selected={selectedAxioms.has(i)}
                onToggle={idx => setSelectedAxioms(prev => {
                  const n = new Set(prev);
                  n.has(idx) ? n.delete(idx) : n.add(idx);
                  return n;
                })}
              />
            ))
        )}
        {activeTab === "lore" && (
          filteredLore.length === 0
            ? <p className="text-xs text-fg-muted text-center py-10">No lore facts match.</p>
            : filteredLore.map(([f, i]) => (
              <SelectableLoreRow
                key={i}
                fact={f}
                index={i}
                selected={selectedLore.has(i)}
                onToggle={idx => setSelectedLore(prev => {
                  const n = new Set(prev);
                  n.has(idx) ? n.delete(idx) : n.add(idx);
                  return n;
                })}
              />
            ))
        )}
      </div>

      {/* Save modal */}
      <AnimatePresence>
        {showSave && (
          <SaveModal
            mode={mode}
            onClose={() => setShowSave(false)}
            saving={sliceMutation.isPending}
            onSave={(name, withLineage) => sliceMutation.mutate({ name, withLineage })}
          />
        )}
      </AnimatePresence>
    </div>
  );
}

export default function PackEditorPage() {
  return (
    <Suspense fallback={<div className="p-6 text-sm text-fg-secondary">Loading pack editor…</div>}>
      <PackEditorPageContent />
    </Suspense>
  );
}
