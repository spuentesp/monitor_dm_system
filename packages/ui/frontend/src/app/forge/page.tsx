"use client";

import { useRef, useState, useMemo, useCallback, Suspense, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  Archive,
  BookOpen,
  Check,
  Copy,
  Download,
  FlaskConical,
  Gamepad2,
  GitMerge,
  Globe2,
  Layers,
  Link,
  Loader2,
  Plus,
  RefreshCw,
  Save,
  Scissors,
  Search,
  Sparkles,
  Trash2,
  Upload,
  X,
  XCircle,
  FileImage,
} from "lucide-react";
import { DialogFooter, DialogShell } from "@/components/DialogShell";
import {
  AxiomRow,
  EntityRow,
  LoreRow,
  PackListItem,
  RuleRow,
} from "@/components/forge/ForgeRows";
import { entitiesApi, ingestApi } from "@/lib/api";
import { SourcesPanel } from "@/components/forge/SourcesPanel";
import { AssetsPanel } from "@/components/forge/AssetsPanel";
import { TemplateBrowser } from "@/components/forge/TemplateBrowser";
import { TemplateInstantiator } from "@/components/forge/TemplateInstantiator";
import { RandomTableBrowser } from "@/components/forge/RandomTableEditor";
import {
  AXIOM_DOMAIN_OPTIONS,
  ENTITY_TYPE_CONFIG,
  FACT_TYPE_OPTIONS,
  FORGE_TABS as TABS,
  RULE_TYPE_OPTIONS,
  type ForgeTabId as TabId,
} from "@/lib/forge";
import type {
  ExtractedAxiom,
  ExtractedEntity,
  ExtractedLoreFact,
  KnowledgePack,
  RPGSystem,
  RuleInfo,
  EntityTemplate,
} from "@/lib/types";
import { cn, truncate } from "@/lib/utils";
import type { SourceProfile } from "@/lib/types";
import { FORGE_KEYS, ENTITY_KEYS } from "@/lib/query-keys";
import { useSystems, useSystem } from "@/hooks/use-systems";

function suggestRuleName(statement: string): string {
  const firstClause = statement.split(/[.!?]/)[0]?.trim() ?? "";
  if (!firstClause) return "Untitled Rule";
  return firstClause.length > 60 ? `${firstClause.slice(0, 57)}…` : firstClause;
}

// ─── Source Profile Tab ───────────────────────────────────────

function ProfileTagList({ label, items, color = "tag-dim" }: { label: string; items: string[]; color?: string }) {
  if (!items.length) return null;
  return (
    <div className="space-y-1">
      <p className="text-[10px] font-bold tracking-widest uppercase text-fg-muted">{label}</p>
      <div className="flex flex-wrap gap-1">
        {items.map(item => (
          <span key={item} className={cn("rounded border px-1.5 py-0.5 text-[10px]", color)}>{item}</span>
        ))}
      </div>
    </div>
  );
}

function ConfidenceBar({ label, value }: { label: string; value: number }) {
  const pct = Math.round(value * 100);
  const color = value >= 0.8 ? "bg-emerald-500" : value >= 0.65 ? "bg-amber-500" : "bg-red-500";
  return (
    <div className="flex items-center gap-2">
      <span className="w-28 shrink-0 text-[10px] text-fg-secondary capitalize">{label.replace(/_/g, " ")}</span>
      <div className="flex-1 h-1.5 rounded-full bg-bg-hover">
        <div className={cn("h-full rounded-full", color)} style={{ width: `${pct}%` }} />
      </div>
      <span className="w-8 text-right text-[10px] text-fg-muted">{pct}%</span>
    </div>
  );
}

function SourceProfileTab({
  pack,
  onPatchPack,
  onToggleApproval,
}: {
  pack: KnowledgePack | null;
  onPatchPack?: (patch: Partial<KnowledgePack>) => void;
  onToggleApproval?: (tag: string) => void;
}) {
  const profile: SourceProfile | null = pack?.source_profile_data ?? null;
  const mindscape = pack?.source_mindscape ?? null;
  const sectionSummaries = pack?.section_summaries ?? [];
  const chunkSummaries = pack?.chunk_summaries ?? [];
  const reviewedProfile = Boolean(pack?.tags?.includes("reviewed:profile"));
  const reviewedArtifacts = Boolean(pack?.tags?.includes("reviewed:artifacts"));

  const ensureProfile = (): SourceProfile => ({
    profile_type: "source",
    source_kind: pack?.pack_type ?? "custom",
    world_kind: null,
    system_name: pack?.system_name ?? mindscape?.system_name ?? null,
    edition: null,
    family: null,
    genre_tone: mindscape?.themes ?? [],
    narrative_frame: [],
    lore_domains: [],
    taxonomy_containers: mindscape?.taxonomy_hints ?? [],
    institution_model: [],
    relationship_patterns: [],
    term_lexicon: {},
    aliases: {},
    canon_signal_terms: [],
    important_named_sets: [],
    coverage_summary: mindscape?.summary ?? null,
    known_open_questions: [],
    confidence_by_field: {},
    evidence_refs: [],
    profile_version: "1.0",
    prompt_version: null,
    model_used: null,
    ...(profile ?? {}),
  });

  const setProfile = (partial: Partial<SourceProfile>) => {
    if (!onPatchPack) return;
    onPatchPack({ source_profile_data: { ...ensureProfile(), ...partial } });
  };

  const setMindscape = (partial: Partial<NonNullable<KnowledgePack["source_mindscape"]>>) => {
    if (!onPatchPack || !pack) return;
    onPatchPack({
      source_mindscape: {
        source_name: pack.name,
        summary: "",
        themes: [],
        taxonomy_hints: [],
        system_name: pack.system_name,
        confidence: 0,
        ...(mindscape ?? {}),
        ...partial,
      },
    });
  };

  const setSectionSummary = (index: number, patch: Partial<(typeof sectionSummaries)[number]>) => {
    if (!onPatchPack) return;
    const next = sectionSummaries.map((section, idx) => (idx === index ? { ...section, ...patch } : section));
    onPatchPack({ section_summaries: next });
  };

  const parseCsv = (value: string) => value.split(",").map(item => item.trim()).filter(Boolean);

  if (!profile && !mindscape && sectionSummaries.length === 0 && chunkSummaries.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 px-6 text-center space-y-2">
        <Sparkles className="h-8 w-8 text-fg-muted/30" />
        <p className="text-sm text-fg-secondary">No ingest insight artifacts are available for this pack.</p>
        <p className="text-xs text-fg-muted">Profiles, mindscapes, and section summaries appear automatically after source ingestion completes.</p>
      </div>
    );
  }

  const hasIdentity = profile?.world_kind || profile?.source_kind || profile?.system_name || mindscape?.system_name;
  const hasConfidence = Object.keys(profile?.confidence_by_field ?? {}).length > 0;

  return (
    <div className="p-5 space-y-5 max-w-4xl">
      <div className="rounded-xl border border-border bg-bg-base px-3 py-2 flex flex-wrap items-center justify-between gap-2">
        <p className="text-[11px] text-fg-muted">Review, edit, then save these ingestion artifacts.</p>
        <div className="flex flex-wrap gap-2">
          <button
            className={cn("btn-ghost text-xs", reviewedProfile ? "text-emerald-300" : "text-fg-muted")}
            onClick={() => onToggleApproval?.("reviewed:profile")}
          >
            {reviewedProfile ? "✓ Profile approved" : "Approve profile"}
          </button>
          <button
            className={cn("btn-ghost text-xs", reviewedArtifacts ? "text-emerald-300" : "text-fg-muted")}
            onClick={() => onToggleApproval?.("reviewed:artifacts")}
          >
            {reviewedArtifacts ? "✓ Artifacts approved" : "Approve artifacts"}
          </button>
        </div>
      </div>

      {hasIdentity && (
        <div className="flex flex-wrap gap-2 items-center">
          {profile?.source_kind && (
            <span className="tag-cyan rounded border px-2 py-0.5 text-xs font-medium">{profile.source_kind.replace(/_/g, " ")}</span>
          )}
          {profile?.world_kind && (
            <span className="tag-purple rounded border px-2 py-0.5 text-xs font-medium">{profile.world_kind}</span>
          )}
          {(profile?.system_name || mindscape?.system_name) && (
            <span className="tag-emerald rounded border px-2 py-0.5 text-xs font-medium">
              {profile?.system_name || mindscape?.system_name}{profile?.edition ? ` (${profile.edition})` : ""}
            </span>
          )}
          {mindscape && (
            <span className="tag-dim rounded border px-2 py-0.5 text-xs font-medium">
              {sectionSummaries.length} sections · {chunkSummaries.length} chunks
            </span>
          )}
        </div>
      )}

      {mindscape && (
        <div className="rounded-xl border border-purple-500/20 bg-purple-500/5 p-3 space-y-3">
          <div className="flex items-center gap-2 text-xs font-semibold text-purple-300">
            <Sparkles className="h-3.5 w-3.5" /> Source Mindscape
          </div>
          <div className="space-y-1">
            <label className="text-[10px] font-bold tracking-widest uppercase text-fg-muted">Summary</label>
            <textarea
              className="input-base w-full text-xs min-h-[84px] resize-y"
              value={mindscape.summary ?? ""}
              onChange={e => setMindscape({ summary: e.target.value })}
            />
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div className="space-y-1">
              <label className="text-[10px] font-bold tracking-widest uppercase text-fg-muted">Themes</label>
              <input
                className="input-base w-full text-xs"
                value={(mindscape.themes ?? []).join(", ")}
                onChange={e => setMindscape({ themes: parseCsv(e.target.value) })}
              />
            </div>
            <div className="space-y-1">
              <label className="text-[10px] font-bold tracking-widest uppercase text-fg-muted">Taxonomy hints</label>
              <input
                className="input-base w-full text-xs"
                value={(mindscape.taxonomy_hints ?? []).join(", ")}
                onChange={e => setMindscape({ taxonomy_hints: parseCsv(e.target.value) })}
              />
            </div>
          </div>
        </div>
      )}

      {profile && (
        <>
          <div className="space-y-1">
            <label className="text-[10px] font-bold tracking-widest uppercase text-fg-muted">Coverage summary</label>
            <textarea
              className="input-base w-full text-xs min-h-[72px] resize-y"
              value={profile.coverage_summary ?? ""}
              onChange={e => setProfile({ coverage_summary: e.target.value })}
            />
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <ProfileTagList label="Genre / Tone" items={profile.genre_tone} color="tag-purple" />
            <ProfileTagList label="Narrative Frame" items={profile.narrative_frame} color="tag-cyan" />
            <ProfileTagList label="Lore Domains" items={profile.lore_domains} color="tag-amber" />
            <ProfileTagList label="Taxonomy Containers" items={profile.taxonomy_containers} color="tag-emerald" />
            <ProfileTagList label="Power Structures" items={profile.institution_model} color="tag-red" />
            <ProfileTagList label="Named Anchors" items={profile.important_named_sets} color="tag-dim" />
            <ProfileTagList label="Signal Terms" items={profile.canon_signal_terms.slice(0, 8)} color="tag-dim" />
          </div>

          {hasConfidence && (
            <div className="space-y-2">
              <p className="text-[10px] font-bold tracking-widest uppercase text-fg-muted">Field Confidence</p>
              <div className="space-y-1.5">
                {Object.entries(profile.confidence_by_field).map(([field, val]) => (
                  <ConfidenceBar key={field} label={field} value={val} />
                ))}
              </div>
            </div>
          )}

          {profile.evidence_refs.length > 0 && (
            <div className="space-y-1.5">
              <p className="text-[10px] font-bold tracking-widest uppercase text-fg-muted">Evidence</p>
              <div className="space-y-1">
                {profile.evidence_refs.slice(0, 5).map((ref, i) => (
                  <div key={i} className="flex gap-2 text-[10px] text-fg-muted">
                    <span className="shrink-0 text-fg-muted/40">•</span>
                    <span className="truncate">{ref.ref}</span>
                    {ref.note && <span className="shrink-0 text-fg-muted/40 italic">{ref.note}</span>}
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="flex flex-wrap gap-3 text-[10px] text-fg-muted border-t border-border pt-3">
            {profile.prompt_version && <span>prompt: {profile.prompt_version}</span>}
            {profile.model_used && <span>model: {profile.model_used}</span>}
            {profile.profile_version && <span>v{profile.profile_version}</span>}
          </div>
        </>
      )}

      {sectionSummaries.length > 0 && (
        <div className="space-y-2">
          <div className="flex items-center gap-2 text-[10px] font-bold tracking-widest uppercase text-fg-muted">
            <Layers className="h-3.5 w-3.5" /> Section Summaries
          </div>
          <div className="space-y-2">
            {sectionSummaries.slice(0, 8).map((section, index) => (
              <div key={section.section_key} className="rounded-lg border border-border bg-bg-base px-3 py-2 space-y-2">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-[11px] font-medium text-fg-secondary">{section.heading_path.join(" › ") || section.section_key}</span>
                  <input
                    className="input-base h-7 text-[10px] px-2 w-40"
                    value={section.semantic_category ?? ""}
                    placeholder="category"
                    onChange={e => setSectionSummary(index, { semantic_category: e.target.value || null })}
                  />
                </div>
                <textarea
                  className="input-base w-full text-xs min-h-[64px] resize-y"
                  value={section.summary}
                  onChange={e => setSectionSummary(index, { summary: e.target.value })}
                />
              </div>
            ))}
          </div>
        </div>
      )}

      {chunkSummaries.length > 0 && (
        <div className="space-y-2">
          <div className="flex items-center gap-2 text-[10px] font-bold tracking-widest uppercase text-fg-muted">
            <BookOpen className="h-3.5 w-3.5" /> Chunk Highlights
          </div>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {chunkSummaries.slice(0, 6).map((chunk) => (
              <div key={chunk.chunk_id} className="rounded-lg border border-border bg-bg-base px-3 py-2">
                <div className="flex items-center justify-between gap-2 mb-1">
                  <span className="text-[10px] text-fg-muted">Chunk {chunk.chunk_index + 1}</span>
                  {chunk.source_ref && <span className="text-[10px] text-fg-muted">{chunk.source_ref}</span>}
                </div>
                <p className="text-xs text-fg-muted leading-relaxed">{chunk.summary}</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Merge modal ──────────────────────────────────────────────

function MergeModal({
  packs,
  onClose,
  onMerged,
}: {
  packs: KnowledgePack[];
  onClose: () => void;
  onMerged: (merged: KnowledgePack) => void;
}) {
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [mergeName, setMergeName] = useState("");
  const [strategy, setStrategy] = useState<"first_wins" | "longest_description">("first_wins");

  const mut = useMutation({
    mutationFn: () =>
      ingestApi.mergePacks({
        pack_ids: Array.from(selected),
        name: mergeName || undefined,
        strategy,
      }),
    onSuccess: onMerged,
  });

  const toggle = (id: string) => {
    setSelected(prev => {
      const n = new Set(prev);
      n.has(id) ? n.delete(id) : n.add(id);
      return n;
    });
  };

  return (
    <DialogShell
      title="Merge Packs"
      icon={GitMerge}
      iconClassName="h-5 w-5 text-purple-400"
      maxWidthClassName="max-w-lg"
      onClose={onClose}
      footer={
        <DialogFooter>
          <button className="btn-ghost" onClick={onClose}>Cancel</button>
          <button
            className="btn-primary"
            disabled={selected.size < 2 || mut.isPending}
            onClick={() => mut.mutate()}
          >
            {mut.isPending ? (
              <><Loader2 className="h-4 w-4 animate-spin" /> Merging…</>
            ) : (
              <><GitMerge className="h-4 w-4" /> Merge {selected.size} Packs</>
            )}
          </button>
        </DialogFooter>
      }
    >
      <div className="p-4 space-y-4">
        <p className="text-xs text-fg-muted">
          Select two or more packs to merge. Duplicate entities (by name) and axioms
          (by statement) will be deduplicated automatically.
        </p>

        <div className="space-y-1 max-h-52 overflow-y-auto">
          {packs.map(p => (
            <label
              key={p.id}
              className={cn(
                "flex items-center gap-3 px-3 py-2 rounded-lg cursor-pointer border transition-colors",
                selected.has(p.id)
                  ? "border-accent-primary bg-accent-primary/10"
                  : "border-border hover:bg-bg-hover",
              )}
            >
              <input
                type="checkbox"
                className="sr-only"
                checked={selected.has(p.id)}
                onChange={() => toggle(p.id)}
              />
              <div
                className={cn(
                  "h-4 w-4 rounded border flex items-center justify-center shrink-0",
                  selected.has(p.id) ? "bg-accent-primary border-accent-primary" : "border-border",
                )}
              >
                {selected.has(p.id) && <Check className="h-3 w-3 text-white" />}
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-fg-primary truncate">{p.name}</p>
                <p className="text-[10px] text-fg-muted">
                  {p.entity_count} entities · {p.axiom_count} axioms · {p.lore_fact_count} lore
                </p>
              </div>
            </label>
          ))}
        </div>

        <div className="space-y-1">
          <label className="text-xs text-fg-muted">Merged pack name (optional)</label>
          <input
            className="input-base w-full text-sm"
            placeholder="Auto-generated if empty"
            value={mergeName}
            onChange={e => setMergeName(e.target.value)}
          />
        </div>

        <div className="space-y-1">
          <label className="text-xs text-fg-muted">When duplicate names conflict…</label>
          <select
            className="input-base w-full text-sm"
            value={strategy}
            onChange={e => setStrategy(e.target.value as typeof strategy)}
          >
            <option value="first_wins">Keep first occurrence</option>
            <option value="longest_description">Keep longest description</option>
          </select>
        </div>

        {mut.isError && (
          <p className="text-xs text-red-400">
            {(mut.error as Error)?.message ?? "Merge failed"}
          </p>
        )}
      </div>
    </DialogShell>
  );
}

// ─── Create pack modal ────────────────────────────────────────

function CreatePackModal({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: (pack: KnowledgePack) => void;
}) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [packType, setPackType] = useState("custom");
  const [systemName, setSystemName] = useState("");

  const mut = useMutation({
    mutationFn: () =>
      ingestApi.createPack({ name, description, pack_type: packType, system_name: systemName || undefined }),
    onSuccess: onCreated,
  });

  return (
    <DialogShell
      title="New Pack"
      icon={FlaskConical}
      onClose={onClose}
      footer={
        <DialogFooter>
          <button className="btn-ghost" onClick={onClose}>Cancel</button>
          <button
            className="btn-primary"
            disabled={!name.trim() || mut.isPending}
            onClick={() => mut.mutate()}
          >
            {mut.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <><FlaskConical className="h-4 w-4" /> Create Pack</>}
          </button>
        </DialogFooter>
      }
    >
      <div className="p-4 space-y-3">
        <div className="space-y-1">
          <label className="text-xs text-fg-muted">Name *</label>
          <input
            autoFocus
            className="input-base w-full text-sm"
            value={name}
            onChange={e => setName(e.target.value)}
            placeholder="My World Pack"
            onKeyDown={e => { if (e.key === "Enter" && name.trim()) mut.mutate(); }}
          />
        </div>
        <div className="space-y-1">
          <label className="text-xs text-fg-muted">Description</label>
          <textarea
            className="input-base w-full text-sm min-h-[60px] resize-y"
            value={description}
            onChange={e => setDescription(e.target.value)}
            placeholder="What is this pack about?"
          />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1">
            <label className="text-xs text-fg-muted">Type</label>
            <select className="input-base w-full text-sm" value={packType} onChange={e => setPackType(e.target.value)}>
              <option value="custom">Custom</option>
              <option value="rulebook">Rulebook</option>
              <option value="setting_supplement">Setting</option>
              <option value="adventure_module">Adventure</option>
              <option value="homebrew">Homebrew</option>
            </select>
          </div>
          <div className="space-y-1">
            <label className="text-xs text-fg-muted">Game System</label>
            <input
              className="input-base w-full text-sm"
              value={systemName}
              onChange={e => setSystemName(e.target.value)}
              placeholder="e.g. D&D 5e"
            />
          </div>
        </div>
        {mut.isError && (
          <p className="text-xs text-red-400">{(mut.error as Error)?.message ?? "Failed to create pack"}</p>
        )}
      </div>
    </DialogShell>
  );
}

// ─── Add item modals ──────────────────────────────────────────

function AddEntityModal({ onAdd, onClose }: { onAdd: (e: ExtractedEntity) => void; onClose: () => void }) {
  const [name, setName] = useState("");
  const [type, setType] = useState<ExtractedEntity["entity_type"]>("character");
  const [desc, setDesc] = useState("");

  return (
    <DialogShell
      title="Add Entity"
      icon={Plus}
      iconClassName="text-cyan-400"
      onClose={onClose}
      footer={
        <DialogFooter>
          <button className="btn-ghost" onClick={onClose}>Cancel</button>
          <button
            className="btn-primary"
            disabled={!name.trim()}
            onClick={() => {
              onAdd({ name, entity_type: type, description: desc, properties: {}, source_ref: null, confidence: 1.0, tags: [] });
              onClose();
            }}
          >
            <Plus className="h-4 w-4" /> Add
          </button>
        </DialogFooter>
      }
    >
      <div className="p-4 space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1">
            <label className="text-xs text-fg-muted">Name *</label>
            <input className="input-base w-full text-sm" value={name} onChange={e => setName(e.target.value)} placeholder="Entity name" />
          </div>
          <div className="space-y-1">
            <label className="text-xs text-fg-muted">Type</label>
            <select className="input-base w-full text-sm" value={type} onChange={e => setType(e.target.value as ExtractedEntity["entity_type"])}>
              {Object.keys(ENTITY_TYPE_CONFIG).map(t => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
        </div>
        <div className="space-y-1">
          <label className="text-xs text-fg-muted">Description</label>
          <textarea className="input-base w-full text-sm min-h-[80px] resize-y" value={desc} onChange={e => setDesc(e.target.value)} placeholder="Describe this entity…" />
        </div>
      </div>
    </DialogShell>
  );
}

function AddAxiomModal({ onAdd, onClose }: { onAdd: (a: ExtractedAxiom) => void; onClose: () => void }) {
  const [statement, setStatement] = useState("");
  const [domain, setDomain] = useState<(typeof AXIOM_DOMAIN_OPTIONS)[number]>("world");

  return (
    <DialogShell
      title="Add Axiom"
      icon={Sparkles}
      iconClassName="text-purple-400"
      onClose={onClose}
      footer={
        <DialogFooter>
          <button className="btn-ghost" onClick={onClose}>Cancel</button>
          <button
            className="btn-primary"
            disabled={!statement.trim()}
            onClick={() => {
              onAdd({ statement: statement.trim(), domain, confidence: 1.0, source_ref: null, tags: [] });
              onClose();
            }}
          >
            <Plus className="h-4 w-4" /> Add
          </button>
        </DialogFooter>
      }
    >
      <div className="p-4 space-y-3">
        <div className="space-y-1">
          <label className="text-xs text-fg-muted">Domain</label>
          <select className="input-base w-full text-sm" value={domain} onChange={e => setDomain(e.target.value as (typeof AXIOM_DOMAIN_OPTIONS)[number])}>
            {AXIOM_DOMAIN_OPTIONS.map((option) => <option key={option} value={option}>{option}</option>)}
          </select>
        </div>
        <div className="space-y-1">
          <label className="text-xs text-fg-muted">Statement *</label>
          <textarea className="input-base w-full text-sm min-h-[90px] resize-y" value={statement} onChange={e => setStatement(e.target.value)} placeholder="Magic exists but exact spells vary by culture." />
        </div>
      </div>
    </DialogShell>
  );
}

function AddLoreModal({ onAdd, onClose }: { onAdd: (f: ExtractedLoreFact) => void; onClose: () => void }) {
  const [statement, setStatement] = useState("");
  const [factType, setFactType] = useState<(typeof FACT_TYPE_OPTIONS)[number]>("state");

  return (
    <DialogShell
      title="Add Lore Fact"
      icon={BookOpen}
      iconClassName="text-amber-400"
      onClose={onClose}
      footer={
        <DialogFooter>
          <button className="btn-ghost" onClick={onClose}>Cancel</button>
          <button
            className="btn-primary"
            disabled={!statement.trim()}
            onClick={() => {
              onAdd({ statement: statement.trim(), fact_type: factType, entity_names: [], source_ref: null, confidence: 1.0, tags: [] });
              onClose();
            }}
          >
            <Plus className="h-4 w-4" /> Add
          </button>
        </DialogFooter>
      }
    >
      <div className="p-4 space-y-3">
        <div className="space-y-1">
          <label className="text-xs text-fg-muted">Classification</label>
          <select className="input-base w-full text-sm" value={factType} onChange={e => setFactType(e.target.value as (typeof FACT_TYPE_OPTIONS)[number])}>
            {FACT_TYPE_OPTIONS.map((option) => <option key={option} value={option}>{option}</option>)}
          </select>
        </div>
        <div className="space-y-1">
          <label className="text-xs text-fg-muted">Statement *</label>
          <textarea className="input-base w-full text-sm min-h-[90px] resize-y" value={statement} onChange={e => setStatement(e.target.value)} placeholder="Spell slots recover on a long rest." />
        </div>
      </div>
    </DialogShell>
  );
}

function AddRuleModal({ onAdd, onClose }: { onAdd: (r: RuleInfo) => void; onClose: () => void }) {
  const [name, setName] = useState("");
  const [ruleType, setRuleType] = useState<(typeof RULE_TYPE_OPTIONS)[number]>("custom");
  const [description, setDescription] = useState("");
  const [formula, setFormula] = useState("");

  return (
    <DialogShell
      title="Add Rule"
      icon={Layers}
      iconClassName="text-emerald-400"
      onClose={onClose}
      footer={
        <DialogFooter>
          <button className="btn-ghost" onClick={onClose}>Cancel</button>
          <button
            className="btn-primary"
            disabled={!name.trim() || !description.trim()}
            onClick={() => {
              onAdd({ name: name.trim(), rule_type: ruleType, description: description.trim(), formula: formula.trim() || null, examples: [], exceptions: [] });
              onClose();
            }}
          >
            <Plus className="h-4 w-4" /> Add
          </button>
        </DialogFooter>
      }
    >
      <div className="p-4 space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1">
            <label className="text-xs text-fg-muted">Rule name *</label>
            <input className="input-base w-full text-sm" value={name} onChange={e => setName(e.target.value)} placeholder="Spell Slots" />
          </div>
          <div className="space-y-1">
            <label className="text-xs text-fg-muted">Rule type</label>
            <select className="input-base w-full text-sm" value={ruleType} onChange={e => setRuleType(e.target.value as (typeof RULE_TYPE_OPTIONS)[number])}>
              {RULE_TYPE_OPTIONS.map((option) => <option key={option} value={option}>{option}</option>)}
            </select>
          </div>
        </div>
        <div className="space-y-1">
          <label className="text-xs text-fg-muted">Description *</label>
          <textarea className="input-base w-full text-sm min-h-[90px] resize-y" value={description} onChange={e => setDescription(e.target.value)} placeholder="Describe how the rule works…" />
        </div>
        <div className="space-y-1">
          <label className="text-xs text-fg-muted">Formula (optional)</label>
          <input className="input-base w-full text-sm" value={formula} onChange={e => setFormula(e.target.value)} placeholder="AC = 10 + DEX mod" />
        </div>
      </div>
    </DialogShell>
  );
}

// ─── Pack metadata chips (I-10, I-11) ──────────────────────────

function GameSystemChip({
  pack,
  onUpdate,
}: {
  pack: KnowledgePack;
  onUpdate: (gsId: string | null) => void;
}) {
  const [editing, setEditing] = useState(false);

  const { data: systems = [] } = useSystems();

  if (!editing) {
    return (
      <button
        onClick={() => setEditing(true)}
        className="text-[10px] px-1.5 py-0.5 rounded border tag-dim hover:border-accent-primary/40 transition-colors flex items-center gap-1"
        title="Click to change linked game system"
      >
        <Gamepad2 className="h-2.5 w-2.5" />
        {pack.game_system_id ? pack.system_name || "System linked" : "No system"}
      </button>
    );
  }

  return (
    <select
      autoFocus
      className="text-[10px] px-1.5 py-0.5 rounded border border-accent-primary/40 bg-bg-card text-fg-primary focus:outline-none"
      value={pack.game_system_id ?? ""}
      onChange={(e) => {
        onUpdate(e.target.value || null);
        setEditing(false);
      }}
      onBlur={() => setEditing(false)}
    >
      <option value="">— no system —</option>
      {systems.map((s: RPGSystem) => (
        <option key={s.id} value={s.id}>{s.name}</option>
      ))}
    </select>
  );
}

function SourceLinksChip({
  pack,
  onUpdate,
}: {
  pack: KnowledgePack;
  onUpdate: (ids: string[]) => void;
}) {
  const [editing, setEditing] = useState(false);
  const sourceIds = pack.source_document_ids ?? [];

  const { data: sources = [] } = useQuery({
    queryKey: FORGE_KEYS.sources,
    queryFn: () => ingestApi.listSources(),
    staleTime: 30_000,
  });

  if (!editing) {
    return (
      <button
        onClick={() => setEditing(true)}
        className="text-[10px] px-1.5 py-0.5 rounded border tag-dim hover:border-accent-primary/40 transition-colors flex items-center gap-1"
        title="Click to link source documents"
      >
        <Link className="h-2.5 w-2.5" />
        {sourceIds.length > 0 ? `${sourceIds.length} source${sourceIds.length > 1 ? "s" : ""}` : "No sources"}
      </button>
    );
  }

  return (
    <select
      autoFocus
      multiple
      className="text-[10px] px-1.5 py-0.5 rounded border border-accent-primary/40 bg-bg-card text-fg-primary focus:outline-none max-w-[200px]"
      value={sourceIds}
      onChange={(e) => {
        const selected = Array.from(e.target.selectedOptions, (o) => o.value);
        onUpdate(selected);
      }}
      onBlur={() => setEditing(false)}
      size={Math.min(sources.length + 1, 6)}
    >
      {sources.map((s) => (
        <option key={s.id} value={s.id} className="text-[10px]">
          {s.title || s.filename}
        </option>
      ))}
    </select>
  );
}

// ─── Main World Forge page ────────────────────────────────────

function ForgePageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const qc = useQueryClient();
  const importFileRef = useRef<HTMLInputElement>(null);

  // Land on "sources" so the Quick Start (seed → playable world) and ingestion
  // entry points are the first thing you see in the Forge; pack management is
  // one click away on the Packs tab.
  const [forgeMode, setForgeMode] = useState<"packs" | "sources" | "assets">("sources");
  const [selectedPackId, setSelectedPackId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<TabId>("entities");
  const [searchQuery, setSearchQuery] = useState("");
  const [typeFilter, setTypeFilter] = useState<string>("all");
  const [showMerge, setShowMerge] = useState(false);
  const [showAddEntity, setShowAddEntity] = useState(false);
  const [showAddAxiom, setShowAddAxiom] = useState(false);
  const [showAddLore, setShowAddLore] = useState(false);
  const [showAddRule, setShowAddRule] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [showArchived, setShowArchived] = useState(false);
  const [instantiatingTemplate, setInstantiatingTemplate] = useState<EntityTemplate | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<{ pack: KnowledgePack; hard: boolean } | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [dirtyPack, setDirtyPack] = useState<KnowledgePack | null>(null);
  const [dirtySystem, setDirtySystem] = useState<RPGSystem | null>(null);
  const [saving, setSaving] = useState(false);
  const [savingSystem, setSavingSystem] = useState(false);

  // Load all packs
  const { data: allPacks = [], isLoading: packsLoading } = useQuery({
    queryKey: FORGE_KEYS.packs,
    queryFn: () => ingestApi.listPacks(),
    staleTime: 30_000,
  });

  const packs = useMemo(
    () => showArchived ? allPacks : allPacks.filter(p => p.status !== "archived"),
    [allPacks, showArchived],
  );

  const reviewPendingCount = useMemo(
    () => allPacks.filter(p => p.status === "review_pending").length,
    [allPacks],
  );

  const basePack = useMemo(
    () => allPacks.find(p => p.id === selectedPackId) ?? null,
    [allPacks, selectedPackId],
  );
  const pack = dirtyPack ?? basePack;

  const { data: linkedSystem = null } = useSystem(pack?.game_system_id);

  const system = dirtySystem ?? linkedSystem ?? null;

  const selectPack = useCallback((id: string) => {
    setSelectedPackId(id);
    setDirtyPack(null);
    setDirtySystem(null);
    setSearchQuery("");
    setTypeFilter("all");
    setActiveTab("entities");
  }, []);

  // Deep-link: auto-select pack from ?pack=<id> query param
  useEffect(() => {
    const packParam = searchParams.get("pack");
    if (packParam && allPacks.some(p => p.id === packParam)) {
      setSelectedPackId(packParam);
    }
  }, [searchParams, allPacks]);

  // ── Mutation: save edited pack ───────────────────────────────
  const saveMutation = useMutation({
    mutationFn: async (p: KnowledgePack) => {
      setSaving(true);
      return ingestApi.updatePack(p.id, {
        name: p.name,
        axioms: p.axioms,
        entity_archetypes: p.entity_archetypes,
        lore_facts: p.lore_facts,
        entity_relationships: p.entity_relationships,
        source_profile_data: p.source_profile_data,
        chunk_summaries: p.chunk_summaries,
        section_summaries: p.section_summaries,
        source_mindscape: p.source_mindscape,
        tags: p.tags,
        game_system_id: p.game_system_id,
        source_document_ids: p.source_document_ids,
      });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: FORGE_KEYS.packs });
      setDirtyPack(null);
      setSaving(false);
    },
    onError: () => setSaving(false),
  });

  const saveSystemMutation = useMutation({
    mutationFn: async (s: RPGSystem) => {
      setSavingSystem(true);
      return entitiesApi.updateSystem(s.id, {
        name: s.name,
        description: s.description,
        version: s.version,
        rules: s.rules,
      });
    },
    onSuccess: (updated) => {
      qc.invalidateQueries({ queryKey: FORGE_KEYS.system(updated.id) });
      qc.invalidateQueries({ queryKey: ENTITY_KEYS.systems });
      setDirtySystem(null);
      setSavingSystem(false);
    },
    onError: () => setSavingSystem(false),
  });

  const handleSaveAll = async () => {
    try {
      if (dirtyPack) {
        await saveMutation.mutateAsync(dirtyPack);
      }
      if (dirtySystem) {
        await saveSystemMutation.mutateAsync(dirtySystem);
      }
    } catch {
      // mutation state already captures the error
    }
  };

  // ── Mutation: delete/archive pack ────────────────────────────
  const deleteMutation = useMutation({
    mutationFn: ({ id, hard }: { id: string; hard: boolean }) =>
      ingestApi.deletePack(id, hard),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: FORGE_KEYS.packs });
      if (confirmDelete && confirmDelete.pack.id === selectedPackId) {
        setSelectedPackId(null);
        setDirtyPack(null);
      }
      setConfirmDelete(null);
      setDeleteError(null);
    },
    onError: (err: Error) => {
      setDeleteError(err.message);
    },
  });

  // ── Mutation: clone pack ─────────────────────────────────────
  const cloneMutation = useMutation({
    mutationFn: (id: string) => ingestApi.clonePack(id, { with_lineage: true }),
    onSuccess: (cloned) => {
      qc.invalidateQueries({ queryKey: FORGE_KEYS.packs });
      selectPack(cloned.id);
    },
  });

  // ── Export pack ──────────────────────────────────────────────
  const handleExport = async (id: string, name: string) => {
    try {
      setActionError(null);
      const blob = await ingestApi.exportPack(id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${name.replace(/\s+/g, "_")}.monitorpack`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Could not export pack.");
    }
  };

  // ── Import pack from file ────────────────────────────────────
  const handleImportFile = async (file: File) => {
    try {
      setActionError(null);
      const text = await file.text();
      const envelope = JSON.parse(text);
      const imported = await ingestApi.importPack(envelope);
      qc.invalidateQueries({ queryKey: FORGE_KEYS.packs });
      selectPack(imported.id);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Could not import pack.");
    }
  };

  const isDirty = dirtyPack !== null || dirtySystem !== null;

  // ── Patch helpers ────────────────────────────────────────────
  const patchEntity = (i: number, partial: Partial<ExtractedEntity>) => {
    if (!pack) return;
    const updated = pack.entity_archetypes.map((e, idx) =>
      idx === i ? { ...e, ...partial } : e,
    );
    setDirtyPack({ ...pack, entity_archetypes: updated, entity_count: updated.length });
  };

  const deleteEntity = (i: number) => {
    if (!pack) return;
    const updated = pack.entity_archetypes.filter((_, idx) => idx !== i);
    setDirtyPack({ ...pack, entity_archetypes: updated, entity_count: updated.length });
  };

  const addEntity = (e: ExtractedEntity) => {
    if (!pack) return;
    const updated = [...pack.entity_archetypes, e];
    setDirtyPack({ ...pack, entity_archetypes: updated, entity_count: updated.length });
  };

  const addAxiom = (a: ExtractedAxiom) => {
    if (!pack) return;
    const updated = [...pack.axioms, a];
    setDirtyPack({ ...pack, axioms: updated, axiom_count: updated.length });
  };

  const addLore = (f: ExtractedLoreFact) => {
    if (!pack) return;
    const updated = [...pack.lore_facts, f];
    setDirtyPack({ ...pack, lore_facts: updated, lore_fact_count: updated.length });
  };

  const patchArtifactPack = (partial: Partial<KnowledgePack>) => {
    if (!pack) return;
    setDirtyPack({ ...pack, ...partial });
  };

  const toggleReviewTag = (tag: string) => {
    if (!pack) return;
    const current = new Set(pack.tags ?? []);
    if (current.has(tag)) current.delete(tag);
    else current.add(tag);
    setDirtyPack({ ...pack, tags: Array.from(current) });
  };

  const patchAxiom = (i: number, partial: Partial<ExtractedAxiom>) => {
    if (!pack) return;
    const updated = pack.axioms.map((a, idx) => idx === i ? { ...a, ...partial } : a);
    setDirtyPack({ ...pack, axioms: updated, axiom_count: updated.length });
  };

  const deleteAxiom = (i: number) => {
    if (!pack) return;
    const updated = pack.axioms.filter((_, idx) => idx !== i);
    setDirtyPack({ ...pack, axioms: updated, axiom_count: updated.length });
  };

  const convertAxiomToLore = (i: number) => {
    if (!pack) return;
    const axiom = pack.axioms[i];
    if (!axiom) return;
    const nextAxioms = pack.axioms.filter((_, idx) => idx !== i);
    const nextLore = [
      ...pack.lore_facts,
      {
        statement: axiom.statement,
        fact_type: axiom.domain === "rules" || axiom.domain === "game_system" ? "rule" : "state",
        entity_names: [],
        source_ref: axiom.source_ref,
        confidence: axiom.confidence,
        tags: axiom.tags,
      },
    ];
    setDirtyPack({
      ...pack,
      axioms: nextAxioms,
      axiom_count: nextAxioms.length,
      lore_facts: nextLore,
      lore_fact_count: nextLore.length,
    });
  };

  const patchLore = (i: number, partial: Partial<ExtractedLoreFact>) => {
    if (!pack) return;
    const updated = pack.lore_facts.map((f, idx) => idx === i ? { ...f, ...partial } : f);
    setDirtyPack({ ...pack, lore_facts: updated, lore_fact_count: updated.length });
  };

  const deleteLore = (i: number) => {
    if (!pack) return;
    const updated = pack.lore_facts.filter((_, idx) => idx !== i);
    setDirtyPack({ ...pack, lore_facts: updated, lore_fact_count: updated.length });
  };

  const promoteLoreToAxiom = (i: number) => {
    if (!pack) return;
    const fact = pack.lore_facts[i];
    if (!fact) return;
    const nextLore = pack.lore_facts.filter((_, idx) => idx !== i);
    const nextAxioms = [
      ...pack.axioms,
      {
        statement: fact.statement,
        domain: fact.fact_type === "rule" || fact.fact_type === "mechanic" ? "rules" : "world",
        source_ref: fact.source_ref,
        confidence: fact.confidence,
        tags: fact.tags,
      },
    ];
    setDirtyPack({
      ...pack,
      lore_facts: nextLore,
      lore_fact_count: nextLore.length,
      axioms: nextAxioms,
      axiom_count: nextAxioms.length,
    });
  };

  const patchRule = (i: number, partial: Partial<RuleInfo>) => {
    if (!system) return;
    const updated = system.rules.map((rule, idx) => idx === i ? { ...rule, ...partial } : rule);
    setDirtySystem({ ...system, rules: updated });
  };

  const deleteRule = (i: number) => {
    if (!system) return;
    const updated = system.rules.filter((_, idx) => idx !== i);
    setDirtySystem({ ...system, rules: updated });
  };

  const addRule = (rule: RuleInfo) => {
    if (!system) return;
    const updated = [...system.rules, rule];
    setDirtySystem({ ...system, rules: updated });
  };

  const promoteLoreToRule = (i: number) => {
    if (!pack || !system) return;
    const fact = pack.lore_facts[i];
    if (!fact) return;

    addRule({
      name: suggestRuleName(fact.statement),
      rule_type: fact.fact_type === "mechanic" ? "mechanic" : "custom",
      description: fact.statement,
      formula: null,
      examples: [],
      exceptions: [],
    });

    const nextLore = pack.lore_facts.filter((_, idx) => idx !== i);
    setDirtyPack({ ...pack, lore_facts: nextLore, lore_fact_count: nextLore.length });
  };

  const q = searchQuery.toLowerCase();

  const filteredEntities = useMemo(() => {
    if (!pack) return [] as [ExtractedEntity, number][];
    return pack.entity_archetypes
      .map((e, i) => [e, i] as [ExtractedEntity, number])
      .filter(([e]) => {
        const matchesType = typeFilter === "all" || e.entity_type === typeFilter;
        const matchesSearch = !q || e.name.toLowerCase().includes(q) || e.description.toLowerCase().includes(q);
        return matchesType && matchesSearch;
      });
  }, [pack, typeFilter, q]);

  const filteredAxioms = useMemo(() => {
    if (!pack) return [] as [ExtractedAxiom, number][];
    return pack.axioms
      .map((a, i) => [a, i] as [ExtractedAxiom, number])
      .filter(([a]) => !q || a.statement.toLowerCase().includes(q) || a.domain.toLowerCase().includes(q));
  }, [pack, q]);

  const filteredLore = useMemo(() => {
    if (!pack) return [] as [ExtractedLoreFact, number][];
    return pack.lore_facts
      .map((f, i) => [f, i] as [ExtractedLoreFact, number])
      .filter(([f]) => !q || f.statement.toLowerCase().includes(q) || f.fact_type.toLowerCase().includes(q));
  }, [pack, q]);

  const filteredRules = useMemo(() => {
    if (!system) return [] as [RuleInfo, number][];
    return system.rules
      .map((rule, i) => [rule, i] as [RuleInfo, number])
      .filter(([rule]) =>
        !q ||
        rule.name.toLowerCase().includes(q) ||
        (rule.description ?? "").toLowerCase().includes(q) ||
        (rule.rule_type ?? "").toLowerCase().includes(q),
      );
  }, [system, q]);

  const typeCounts = useMemo(() => {
    if (!pack) return {};
    return pack.entity_archetypes.reduce<Record<string, number>>((acc, e) => {
      acc[e.entity_type] = (acc[e.entity_type] ?? 0) + 1;
      return acc;
    }, {});
  }, [pack]);

  // ── UI ───────────────────────────────────────────────────────
  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* ── Top mode bar ── */}
      <div className="flex items-center gap-1 px-4 h-10 border-b border-border flex-shrink-0 bg-bg-primary">
        <FlaskConical className="h-4 w-4 text-accent-primary mr-1" />
        <button
          onClick={() => setForgeMode("packs")}
          className={cn(
            "px-3 py-1.5 text-xs font-medium rounded-lg transition-colors",
            forgeMode === "packs"
              ? "bg-accent-primary/10 text-accent-primary"
              : "text-fg-muted hover:text-fg-secondary",
          )}
        >
          <Layers className="h-3.5 w-3.5 inline mr-1.5 -mt-px" />
          Packs
          {reviewPendingCount > 0 && (
            <span className="ml-1.5 text-[10px] px-1.5 py-0.5 rounded-full bg-amber-500/20 text-amber-400">
              {reviewPendingCount} to review
            </span>
          )}
        </button>
        <button
          onClick={() => setForgeMode("sources")}
          className={cn(
            "px-3 py-1.5 text-xs font-medium rounded-lg transition-colors",
            forgeMode === "sources"
              ? "bg-accent-primary/10 text-accent-primary"
              : "text-fg-muted hover:text-fg-secondary",
          )}
        >
          <Upload className="h-3.5 w-3.5 inline mr-1.5 -mt-px" />
          Sources
        </button>
        <button
          onClick={() => setForgeMode("assets")}
          className={cn(
            "px-3 py-1.5 text-xs font-medium rounded-lg transition-colors",
            forgeMode === "assets"
              ? "bg-accent-primary/10 text-accent-primary"
              : "text-fg-muted hover:text-fg-secondary",
          )}
        >
          <FileImage className="h-3.5 w-3.5 inline mr-1.5 -mt-px" />
          Assets
        </button>
      </div>

      {forgeMode === "sources" ? (
        <SourcesPanel
          onOpenPack={(packId) => {
            // Route to the dedicated editor route instead of swapping
            // forgeMode to "packs" (which jumps to a totally different
            // sidebar+detail layout and was jarring for the player).
            router.push(`/forge/editor?pack=${packId}`);
          }}
        />
      ) : forgeMode === "assets" ? (
        <div className="flex-1 overflow-auto p-4">
          <AssetsPanel />
        </div>
      ) : (
    <div className="flex flex-1 overflow-hidden">
      {/* ── Sidebar ── */}
      <aside className="w-64 shrink-0 border-r border-border flex flex-col overflow-hidden">
        <div className="p-3 border-b border-border">
          <div className="flex items-center gap-2 mb-2">
            <FlaskConical className="h-5 w-5 text-accent-primary" />
            <h1 className="text-sm font-bold text-fg-primary">World Forge</h1>
          </div>
          <p className="text-[10px] text-fg-muted">
            Create, edit, and compose knowledge packs. Double-click text to edit inline, or reclassify lore into axioms and rules.
          </p>
        </div>

        {/* Pack list */}
        <div className="flex-1 overflow-y-auto p-2 space-y-1">
          {packsLoading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-5 w-5 animate-spin text-fg-muted" />
            </div>
          ) : packs.length === 0 ? (
            <p className="text-xs text-fg-muted text-center py-6 px-2">
              No packs yet. Create one or upload a PDF source.
            </p>
          ) : (
            packs.map(p => (
              <PackListItem
                key={p.id}
                pack={p}
                selected={p.id === selectedPackId}
                onClick={() => selectPack(p.id)}
                onDelete={() => {
                  setDeleteError(null);
                  setConfirmDelete({ pack: p, hard: p.status === "archived" });
                }}
              />
            ))
          )}
        </div>

        {/* Sidebar actions */}
        <div className="p-2 border-t border-border space-y-1">
          <button
            className="btn-ghost w-full justify-start gap-2 text-xs text-accent-primary hover:text-accent-primary/80"
            onClick={() => setShowCreate(true)}
          >
            <Plus className="h-3.5 w-3.5" /> New pack…
          </button>

          {/* Hidden file input for import */}
          <input
            ref={importFileRef}
            type="file" aria-label="Choose pack file to import"
            accept=".monitorpack,application/json"
            className="sr-only"
            onChange={e => {
              const f = e.target.files?.[0];
              if (f) handleImportFile(f);
              e.target.value = "";
            }}
          />
          <button
            className="btn-ghost w-full justify-start gap-2 text-xs text-fg-muted"
            onClick={() => importFileRef.current?.click()}
          >
            <Upload className="h-3.5 w-3.5" /> Import .monitorpack…
          </button>
          {actionError && (
            <p className="text-xs text-red-400 flex items-start gap-1.5 px-1">
              <XCircle className="w-3 h-3 flex-shrink-0 mt-0.5" /> {actionError}
            </p>
          )}
          <button
            className="btn-ghost w-full justify-start gap-2 text-xs text-purple-400 hover:text-purple-300"
            onClick={() => setShowMerge(true)}
            disabled={packs.length < 2}
          >
            <GitMerge className="h-3.5 w-3.5" /> Merge packs…
          </button>

          <div className="border-t border-border pt-1 mt-1 flex items-center justify-between">
            <button
              className="btn-ghost justify-start gap-2 text-xs text-fg-muted"
              onClick={() => qc.invalidateQueries({ queryKey: FORGE_KEYS.packs })}
            >
              <RefreshCw className="h-3.5 w-3.5" /> Refresh
            </button>
            <button
              className={cn("text-[10px] px-2 py-1 rounded border transition-colors", showArchived ? "tag-dim" : "border-transparent text-fg-muted")}
              onClick={() => setShowArchived(v => !v)}
              title="Toggle archived packs"
            >
              <Archive className="h-3 w-3 inline mr-1" />
              Archived
            </button>
          </div>
        </div>
      </aside>

      {/* ── Main content ── */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {!pack ? (
          <div className="flex flex-col items-center justify-center h-full text-center p-8">
            <FlaskConical className="h-12 w-12 text-fg-muted/30 mb-4" />
            <h2 className="text-lg font-semibold text-fg-primary mb-2">Select a Pack</h2>
            <p className="text-sm text-fg-muted max-w-xs">
              Choose a knowledge pack from the sidebar to browse and edit its extracted world data.
            </p>
          </div>
        ) : (
          <>
            {/* Header */}
            <div className="border-b border-border px-5 py-3 flex items-center gap-3 flex-wrap">
              <div className="flex-1 min-w-0">
                <h2 className="text-base font-bold text-fg-primary truncate">{pack.name}</h2>
                <p className="text-xs text-fg-muted">
                  {pack.entity_count} entities · {pack.axiom_count} axioms · {pack.lore_fact_count} lore facts
                  {system && <> · {system.rules.length} rules</>}
                  {pack.system_name && <> · <span className="text-accent-primary">{pack.system_name}</span></>}
                  {pack.parent_pack_ids?.length > 0 && (
                    <span className="ml-2 text-[10px] tag-purple px-1 py-0.5 rounded border">
                      lineage
                    </span>
                  )}
                  {pack.applied_to?.length > 0 && (
                    <span className="ml-2 text-[10px] tag-cyan px-1 py-0.5 rounded border flex items-center gap-1">
                      <Globe2 className="h-2.5 w-2.5" />
                      Applied to {pack.applied_to.length} world{pack.applied_to.length > 1 ? "s" : ""}
                    </span>
                  )}
                </p>
                {/* Source & Game System links */}
                <div className="flex flex-wrap items-center gap-1.5 mt-1">
                  {/* Game System chip (I-11) */}
                  <GameSystemChip
                    pack={pack}
                    onUpdate={(gsId) => patchArtifactPack({ game_system_id: gsId })}
                  />
                  {/* Source links (I-10) */}
                  <SourceLinksChip
                    pack={pack}
                    onUpdate={(ids) => patchArtifactPack({ source_document_ids: ids })}
                  />
                </div>
              </div>

              {/* Pack actions */}
              <div className="flex items-center gap-1.5 flex-wrap">
                {/* Review proposals (when pack is in review_pending state) */}
                {pack.status === "review_pending" && (
                  <button
                    className="btn-cyber text-xs gap-1"
                    onClick={() => router.push(`/forge/review?pack=${pack.id}`)}
                    title="Review proposals before committing to canon"
                  >
                    <Sparkles className="h-3.5 w-3.5" /> Review Proposals
                  </button>
                )}
                {/* Apply */}
                <button
                  className="btn-ghost text-xs gap-1 text-emerald-400 hover:text-emerald-300"
                  onClick={() => router.push(`/forge/apply?pack=${pack.id}`)}
                  title="Apply pack to a world"
                >
                  <Globe2 className="h-3.5 w-3.5" /> Apply
                </button>

                {/* Clone → Editor */}
                <button
                  className="btn-ghost text-xs gap-1 text-cyan-400 hover:text-cyan-300"
                  onClick={() => cloneMutation.mutate(pack.id)}
                  disabled={cloneMutation.isPending}
                  title="Clone this pack"
                >
                  {cloneMutation.isPending
                    ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    : <Copy className="h-3.5 w-3.5" />}
                  Clone
                </button>

                {/* Slice → Editor */}
                <button
                  className="btn-ghost text-xs gap-1 text-amber-400 hover:text-amber-300"
                  onClick={() => router.push(`/forge/editor?pack=${pack.id}&mode=slice`)}
                  title="Slice — select a subset of items"
                >
                  <Scissors className="h-3.5 w-3.5" /> Slice
                </button>

                {/* Export */}
                <button
                  className="btn-ghost text-xs gap-1 text-fg-muted"
                  onClick={() => handleExport(pack.id, pack.name)}
                  title="Export as .monitorpack file"
                >
                  <Download className="h-3.5 w-3.5" /> Export
                </button>

                {/* Archive / delete */}
                {pack.status === "archived" ? (
                  <button
                    className="btn-ghost text-xs gap-1 text-red-400 hover:text-red-300"
                    onClick={() => { setDeleteError(null); setConfirmDelete({ pack, hard: true }); }}
                    title="Permanently delete this pack"
                  >
                    <Trash2 className="h-3.5 w-3.5" /> Delete
                  </button>
                ) : (
                  <button
                    className="btn-ghost text-xs gap-1 text-red-400 hover:text-red-300"
                    onClick={() => { setDeleteError(null); setConfirmDelete({ pack, hard: false }); }}
                    onContextMenu={(e) => { e.preventDefault(); setDeleteError(null); setConfirmDelete({ pack, hard: true }); }}
                    title="Archive this pack (right-click to permanently delete)"
                  >
                    <Archive className="h-3.5 w-3.5" /> Archive
                  </button>
                )}
              </div>

              {/* Save / discard dirty state */}
              <AnimatePresence>
                {isDirty && (
                  <motion.button
                    initial={{ opacity: 0, scale: 0.9 }}
                    animate={{ opacity: 1, scale: 1 }}
                    exit={{ opacity: 0, scale: 0.9 }}
                    className="btn-primary text-xs gap-1.5"
                    onClick={handleSaveAll}
                    disabled={saving || savingSystem}
                    title="Save pack edits and any linked rules changes"
                  >
                    {saving || savingSystem ? (
                      <><Loader2 className="h-3.5 w-3.5 animate-spin" /> Saving…</>
                    ) : (
                      <><Save className="h-3.5 w-3.5" /> Save changes</>
                    )}
                  </motion.button>
                )}
              </AnimatePresence>

              {isDirty && (
                <button
                  className="btn-ghost text-xs text-fg-muted"
                  onClick={() => { setDirtyPack(null); setDirtySystem(null); }}
                  title="Discard changes"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              )}
            </div>

            {/* Tabs */}
            <div className="border-b border-border px-4 pt-2">
              <div className="flex items-center gap-1">
                {TABS.map(tab => {
                  const count =
                    tab.id === "entities" ? pack.entity_count
                    : tab.id === "axioms"  ? pack.axiom_count
                    : tab.id === "lore"    ? pack.lore_fact_count
                    : tab.id === "rules"   ? (system?.rules.length ?? 0)
                    : null;
                  return (
                    <button
                      key={tab.id}
                      title={tab.hint}
                      onClick={() => { setActiveTab(tab.id); setSearchQuery(""); setTypeFilter("all"); }}
                      className={cn(
                        "flex items-center gap-1.5 px-3 py-2 text-xs font-medium border-b-2 -mb-px transition-colors",
                        activeTab === tab.id
                          ? "border-accent-primary text-accent-primary"
                          : "border-transparent text-fg-muted hover:text-fg-secondary",
                        tab.id === "profile" && (pack.source_profile_data || pack.source_mindscape || pack.section_summaries?.length || pack.chunk_summaries?.length) && activeTab !== "profile"
                          ? "text-purple-400/70"
                          : "",
                      )}
                    >
                      <tab.icon className="h-3.5 w-3.5" />
                      {tab.label}
                      {count !== null && (
                        <span className="text-[10px] bg-bg-hover rounded px-1">{count}</span>
                      )}
                    </button>
                  );
                })}
              </div>
              <div className="pb-2 text-[11px] text-fg-muted">
                <span className="text-cyan-300 font-medium">Lore</span> holds setting-specific consequences and world rules. <span className="text-purple-300 font-medium">Core System</span> holds dice math and procedures.
              </div>
            </div>

            {/* Search + filter toolbar (hidden for profile tab) */}
            {activeTab !== "profile" && <div className="flex items-center gap-2 px-4 py-2 border-b border-border bg-bg-base">
              <div className="relative flex-1">
                <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-fg-muted" />
                <input
                  className="input-base pl-8 w-full text-xs h-7"
                  placeholder={`Search ${activeTab}…`}
                  value={searchQuery}
                  onChange={e => setSearchQuery(e.target.value)}
                />
                {searchQuery && (
                  <button className="absolute right-2 top-1/2 -translate-y-1/2" onClick={() => setSearchQuery("")}>
                    <X className="h-3 w-3 text-fg-muted" />
                  </button>
                )}
              </div>

              {/* Entity type filter chips */}
              {activeTab === "entities" && (
                <div className="flex items-center gap-1 flex-wrap">
                  <button
                    onClick={() => setTypeFilter("all")}
                    className={cn("text-[10px] px-2 py-0.5 rounded border transition-colors", typeFilter === "all" ? "tag-cyan" : "tag-dim")}
                  >
                    All ({pack.entity_count})
                  </button>
                  {Object.entries(typeCounts).map(([t, n]) => (
                    <button
                      key={t}
                      onClick={() => setTypeFilter(t === typeFilter ? "all" : t)}
                      className={cn(
                        "text-[10px] px-2 py-0.5 rounded border transition-colors",
                        typeFilter === t
                          ? (ENTITY_TYPE_CONFIG[t]?.tag ?? "tag-dim")
                          : "tag-dim",
                      )}
                    >
                      {t} ({n})
                    </button>
                  ))}
                </div>
              )}

              {/* Add button */}
              {activeTab === "entities" && (
                <button
                  className="btn-ghost text-xs gap-1 text-cyan-400"
                  onClick={() => setShowAddEntity(true)}
                >
                  <Plus className="h-3.5 w-3.5" /> Add entity
                </button>
              )}
              {activeTab === "axioms" && (
                <button
                  className="btn-ghost text-xs gap-1 text-purple-400"
                  onClick={() => setShowAddAxiom(true)}
                >
                  <Plus className="h-3.5 w-3.5" /> Add axiom
                </button>
              )}
              {activeTab === "lore" && (
                <button
                  className="btn-ghost text-xs gap-1 text-amber-400"
                  onClick={() => setShowAddLore(true)}
                >
                  <Plus className="h-3.5 w-3.5" /> Add lore
                </button>
              )}
              {activeTab === "rules" && (
                <button
                  className="btn-ghost text-xs gap-1 text-emerald-400 disabled:opacity-40"
                  onClick={() => setShowAddRule(true)}
                  disabled={!system}
                  title={system ? "Add a system rule" : "This pack does not have a linked game system yet"}
                >
                  <Plus className="h-3.5 w-3.5" /> Add rule
                </button>
              )}
            </div>}

            {/* Content list */}
            <div className="flex-1 overflow-y-auto">
              <AnimatePresence mode="wait">
                {activeTab === "entities" && (
                  <motion.div key="entities" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
                    {filteredEntities.length === 0 ? (
                      <p className="text-xs text-fg-muted text-center py-10">No entities match.</p>
                    ) : (
                      <AnimatePresence>
                        {filteredEntities.map(([e, origIdx]) => (
                          <EntityRow
                            key={`${origIdx}`}
                            entity={e}
                            index={origIdx}
                            onUpdate={patchEntity}
                            onDelete={deleteEntity}
                          />
                        ))}
                      </AnimatePresence>
                    )}
                  </motion.div>
                )}

                {activeTab === "axioms" && (
                  <motion.div key="axioms" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
                    {filteredAxioms.length === 0 ? (
                      <p className="text-xs text-fg-muted text-center py-10">No axioms match.</p>
                    ) : (
                      filteredAxioms.map(([a, origIdx]) => (
                        <AxiomRow
                          key={`${origIdx}`}
                          axiom={a}
                          index={origIdx}
                          onUpdate={patchAxiom}
                          onDelete={deleteAxiom}
                          onConvertToLore={convertAxiomToLore}
                        />
                      ))
                    )}
                  </motion.div>
                )}

                {activeTab === "lore" && (
                  <motion.div key="lore" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
                    {filteredLore.length === 0 ? (
                      <p className="text-xs text-fg-muted text-center py-10">No lore facts match.</p>
                    ) : (
                      filteredLore.map(([f, origIdx]) => (
                        <LoreRow
                          key={`${origIdx}`}
                          fact={f}
                          index={origIdx}
                          onUpdate={patchLore}
                          onDelete={deleteLore}
                          onConvertToAxiom={promoteLoreToAxiom}
                          onPromoteToRule={promoteLoreToRule}
                          canPromoteToRule={Boolean(system)}
                        />
                      ))
                    )}
                  </motion.div>
                )}

                {activeTab === "profile" && (
                  <motion.div key="profile" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
                    <SourceProfileTab pack={pack} onPatchPack={patchArtifactPack} onToggleApproval={toggleReviewTag} />
                  </motion.div>
                )}

                {activeTab === "rules" && (
                  <motion.div key="rules" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
                    {!system ? (
                      <div className="text-center py-10 px-6 space-y-2">
                        <p className="text-sm text-fg-secondary">No linked game system for this pack yet.</p>
                        <p className="text-xs text-fg-muted">
                          Extracted dice math, procedures, and other system mechanics show here once a game system is linked. Setting-specific consequences should stay in the Lore tab unless they truly belong to the core ruleset.
                        </p>
                      </div>
                    ) : filteredRules.length === 0 ? (
                      <div className="text-center py-10 px-6 space-y-2">
                        <p className="text-sm text-fg-secondary">No rules match.</p>
                        <p className="text-xs text-fg-muted">Add a core rule here or promote a lore fact only when it belongs in the linked ruleset.</p>
                      </div>
                    ) : (
                      filteredRules.map(([rule, origIdx]) => (
                        <RuleRow
                          key={`${origIdx}`}
                          rule={rule}
                          index={origIdx}
                          onUpdate={patchRule}
                          onDelete={deleteRule}
                        />
                      ))
                    )}
                  </motion.div>
                )}

                {activeTab === "templates" && (
                  <motion.div key="templates" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="h-full">
                    <TemplateBrowser universeId={null} onInstantiate={(template) => { setInstantiatingTemplate(template); }} />
                  </motion.div>
                )}

                {activeTab === "tables" && (
                  <motion.div key="tables" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="h-full">
                    <RandomTableBrowser universeId={null} />
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </>
        )}
      </div>

      {/* ── Modals ── */}
      <AnimatePresence>
        {instantiatingTemplate && (
          <TemplateInstantiator
            template={instantiatingTemplate}
            open={!!instantiatingTemplate}
            onClose={() => setInstantiatingTemplate(null)}
            onCreated={() => {
              qc.invalidateQueries({ queryKey: ENTITY_KEYS.npcs() });
              setInstantiatingTemplate(null);
            }}
          />
        )}
        {showCreate && (
          <CreatePackModal
            onClose={() => setShowCreate(false)}
            onCreated={created => {
              qc.invalidateQueries({ queryKey: FORGE_KEYS.packs });
              setShowCreate(false);
              selectPack(created.id);
            }}
          />
        )}
        {showMerge && (
          <MergeModal
            packs={packs}
            onClose={() => setShowMerge(false)}
            onMerged={merged => {
              qc.invalidateQueries({ queryKey: FORGE_KEYS.packs });
              setShowMerge(false);
              selectPack(merged.id);
            }}
          />
        )}
        {showAddEntity && (
          <AddEntityModal
            onAdd={addEntity}
            onClose={() => setShowAddEntity(false)}
          />
        )}
        {showAddAxiom && (
          <AddAxiomModal
            onAdd={addAxiom}
            onClose={() => setShowAddAxiom(false)}
          />
        )}
        {showAddLore && (
          <AddLoreModal
            onAdd={addLore}
            onClose={() => setShowAddLore(false)}
          />
        )}
        {showAddRule && (
          <AddRuleModal
            onAdd={addRule}
            onClose={() => setShowAddRule(false)}
          />
        )}
      </AnimatePresence>

      {/* ── Confirm archive / delete modal ──────────────────── */}
      {confirmDelete && (
        <DialogShell
          title={confirmDelete.hard ? "Permanently Delete Pack" : "Archive Pack"}
          icon={confirmDelete.hard ? Trash2 : Archive}
          iconClassName={confirmDelete.hard ? "text-red-400" : "text-amber-400"}
          onClose={() => { setConfirmDelete(null); setDeleteError(null); }}
          maxWidthClassName="max-w-sm"
          footer={
            <DialogFooter>
              <button
                className="btn-ghost text-xs px-3 py-1.5"
                onClick={() => { setConfirmDelete(null); setDeleteError(null); }}
              >
                Cancel
              </button>
              <button
                disabled={deleteMutation.isPending}
                className={cn(
                  "text-xs px-3 py-1.5 rounded-lg font-medium flex items-center gap-1.5 transition-colors",
                  confirmDelete.hard
                    ? "bg-red-500/20 text-red-300 hover:bg-red-500/30 border border-red-500/25"
                    : "bg-amber-500/20 text-amber-300 hover:bg-amber-500/30 border border-amber-500/25",
                )}
                onClick={() => deleteMutation.mutate({ id: confirmDelete.pack.id, hard: confirmDelete.hard })}
              >
                {deleteMutation.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : confirmDelete.hard ? <Trash2 className="h-3.5 w-3.5" /> : <Archive className="h-3.5 w-3.5" />}
                {confirmDelete.hard ? "Delete permanently" : "Archive"}
              </button>
            </DialogFooter>
          }
        >
          <div className="p-4 space-y-3">
            <p className="text-sm text-fg-secondary">
              {confirmDelete.hard ? (
                <>Are you sure you want to permanently delete <strong className="text-fg-primary">{confirmDelete.pack.name}</strong>? This cannot be undone.</>
              ) : (
                <>Archive <strong className="text-fg-primary">{confirmDelete.pack.name}</strong>? It will be hidden from the list but can still be viewed when the archived filter is on.</>
              )}
            </p>
            {!confirmDelete.hard && (
              <p className="text-xs text-fg-muted flex items-center gap-1.5">
                <AlertTriangle className="w-3 h-3 text-amber-500 flex-shrink-0" />
                Right-click the Archive button to permanently delete instead.
              </p>
            )}
            {deleteError && (
              <p className="text-xs text-red-400 flex items-start gap-1.5">
                <XCircle className="w-3 h-3 flex-shrink-0 mt-0.5" /> {deleteError}
              </p>
            )}
          </div>
        </DialogShell>
      )}
    </div>
      )}
    </div>
  );
}

export default function ForgePage() {
  return (
    <Suspense fallback={<div className="flex items-center justify-center h-full"><Loader2 className="h-8 w-8 animate-spin text-cyan-400" /></div>}>
      <ForgePageInner />
    </Suspense>
  );
}
