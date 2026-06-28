"use client";

import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Archive,
  BookOpen,
  Check,
  Edit3,
  FlaskConical,
  Layers,
  MoreVertical,
  Pencil,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";
import {
  AXIOM_DOMAIN_OPTIONS,
  ENTITY_TYPE_CONFIG,
  FACT_TYPE_OPTIONS,
  RULE_TYPE_OPTIONS,
} from "@/lib/forge";
import type {
  ExtractedAxiom,
  ExtractedEntity,
  ExtractedLoreFact,
  KnowledgePack,
  RuleInfo,
} from "@/lib/types";
import { cn } from "@/lib/utils";

const ROW_CLASSNAME = "group/row flex gap-3 px-4 py-3 border-b border-border hover:bg-bg-hover transition-colors";

function InlineEdit({
  value,
  multiline = false,
  onSave,
}: {
  value: string;
  multiline?: boolean;
  onSave: (v: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);

  if (!editing) {
    return (
      <span
        className="group/ie cursor-text"
        onDoubleClick={() => {
          setDraft(value);
          setEditing(true);
        }}
        title="Double-click to edit"
      >
        {value || <span className="text-fg-muted/50 italic">empty</span>}
        <Pencil className="inline ml-1 h-3 w-3 text-fg-muted/30 opacity-0 transition-opacity group-hover/ie:opacity-100" />
      </span>
    );
  }

  return (
    <span className="flex w-full items-start gap-1">
      {multiline ? (
        <textarea
          autoFocus
          aria-label="Edit value"
          className="min-h-[60px] flex-1 resize-y rounded border border-accent-primary/40 bg-bg-card px-2 py-1 text-sm text-fg-primary focus:border-accent-primary focus:outline-none"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Escape") setEditing(false);
          }}
        />
      ) : (
        <input
          autoFocus
          aria-label="Edit value"
          className="flex-1 rounded border border-accent-primary/40 bg-bg-card px-2 py-1 text-sm text-fg-primary focus:border-accent-primary focus:outline-none"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              onSave(draft);
              setEditing(false);
            }
            if (e.key === "Escape") setEditing(false);
          }}
        />
      )}
      <button
        className="btn-ghost p-1 text-emerald-400 hover:text-emerald-300"
        onClick={() => {
          onSave(draft);
          setEditing(false);
        }}
        title="Save (Enter)"
      >
        <Check className="h-3.5 w-3.5" />
      </button>
      <button
        className="btn-ghost p-1 text-fg-muted hover:text-fg-primary"
        onClick={() => setEditing(false)}
        title="Cancel (Esc)"
      >
        <X className="h-3.5 w-3.5" />
      </button>
    </span>
  );
}

function RowDeleteButton({
  onClick,
  title = "Remove item",
}: {
  onClick: () => void;
  title?: string;
}) {
  return (
    <button
      className="self-start p-1 text-red-400 opacity-0 btn-ghost group-hover/row:opacity-60 hover:!opacity-100"
      onClick={onClick}
      title={title}
    >
      <Trash2 className="h-3.5 w-3.5" />
    </button>
  );
}

function RowKebabMenu({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (!(e.target as Element).closest("[data-kebab]")) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  return (
    <div data-kebab className="relative">
      <button
        onClick={(e) => { e.stopPropagation(); setOpen((o) => !o); }}
        className="self-start p-1 text-fg-muted opacity-0 group-hover/row:opacity-60 hover:text-fg-primary transition-all"
        title="More actions"
        aria-label="More actions"
        aria-expanded={open}
      >
        <MoreVertical className="h-3.5 w-3.5" />
      </button>
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: -2 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: -2 }}
            transition={{ duration: 0.1 }}
            className="absolute right-0 top-full mt-1 w-40 glass rounded-xl border border-white/10 shadow-xl z-50 overflow-hidden"
          >
            {children}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}



export function EntityRow({
  entity,
  index,
  onUpdate,
  onDelete,
}: {
  entity: ExtractedEntity;
  index: number;
  onUpdate: (i: number, partial: Partial<ExtractedEntity>) => void;
  onDelete: (i: number) => void;
}) {
  const cfg = ENTITY_TYPE_CONFIG[entity.entity_type] ?? ENTITY_TYPE_CONFIG.concept;
  const Icon = cfg.icon;

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -4 }}
      className={ROW_CLASSNAME}
    >
      <Icon className={cn("mt-0.5 h-4 w-4 shrink-0", cfg.color)} />
      <div className="min-w-0 flex-1 space-y-1">
        <div className="flex items-center gap-2">
          <span className={cn("rounded border px-1.5 py-0.5 text-xs font-medium", cfg.tag)}>
            {entity.entity_type}
          </span>
          <span className="text-sm font-semibold text-fg-primary">
            <InlineEdit value={entity.name} onSave={(v) => onUpdate(index, { name: v })} />
          </span>
          <span className="ml-auto text-xs text-fg-muted opacity-0 group-hover/row:opacity-60">
            {Math.round(entity.confidence * 100)}%
          </span>
        </div>
        <p className="text-xs leading-relaxed text-fg-secondary">
          <InlineEdit
            value={entity.description}
            multiline
            onSave={(v) => onUpdate(index, { description: v })}
          />
        </p>
        {entity.tags.length > 0 && (
          <div className="flex flex-wrap gap-1 pt-0.5">
            {entity.tags.map((tag) => (
              <span key={tag} className="tag-dim text-[10px]">{tag}</span>
            ))}
          </div>
        )}
      </div>
      <RowKebabMenu>
        <button
          onClick={() => onDelete(index)}
          className="w-full flex items-center gap-2.5 px-3 py-2.5 text-left text-xs text-red-400 hover:bg-red-500/5 transition-colors"
        >
          <Trash2 className="w-3.5 h-3.5" />
          Delete
        </button>
      </RowKebabMenu>
    </motion.div>
  );
}

export function AxiomRow({
  axiom,
  index,
  onUpdate,
  onDelete,
  onConvertToLore,
}: {
  axiom: ExtractedAxiom;
  index: number;
  onUpdate: (i: number, partial: Partial<ExtractedAxiom>) => void;
  onDelete: (i: number) => void;
  onConvertToLore: (i: number) => void;
}) {
  const domainValue = axiom.domain || "world";

  return (
    <motion.div layout initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className={ROW_CLASSNAME}>
      <Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-purple-400" />
      <div className="min-w-0 flex-1 space-y-1.5">
        <div className="flex flex-wrap items-center gap-2">
          <select
            value={domainValue}
            onChange={(e) => onUpdate(index, { domain: e.target.value })}
            className="rounded border border-border bg-bg-card px-2 py-0.5 text-[10px] text-fg-secondary"
          >
            {!AXIOM_DOMAIN_OPTIONS.includes(domainValue as (typeof AXIOM_DOMAIN_OPTIONS)[number]) && (
              <option value={domainValue}>{domainValue}</option>
            )}
            {AXIOM_DOMAIN_OPTIONS.map((option) => (
              <option key={option} value={option}>{option}</option>
            ))}
          </select>
          <span className="ml-auto text-xs text-fg-muted opacity-0 group-hover/row:opacity-60">
            {Math.round(axiom.confidence * 100)}%
          </span>
        </div>
        <p className="text-sm text-fg-primary">
          <InlineEdit
            value={axiom.statement}
            multiline
            onSave={(v) => onUpdate(index, { statement: v })}
          />
        </p>
      </div>
      <RowKebabMenu>
        <button
          onClick={() => onConvertToLore(index)}
          className="w-full flex items-center gap-2.5 px-3 py-2.5 text-left text-xs text-fg-secondary hover:bg-white/5 transition-colors"
        >
          <BookOpen className="w-3.5 h-3.5 text-amber-400" />
          Move to lore
        </button>
        <button
          onClick={() => onDelete(index)}
          className="w-full flex items-center gap-2.5 px-3 py-2.5 text-left text-xs text-red-400 hover:bg-red-500/5 transition-colors"
        >
          <Trash2 className="w-3.5 h-3.5" />
          Delete
        </button>
      </RowKebabMenu>
    </motion.div>
  );
}

export function LoreRow({
  fact,
  index,
  onUpdate,
  onDelete,
  onConvertToAxiom,
  onPromoteToRule,
  canPromoteToRule,
}: {
  fact: ExtractedLoreFact;
  index: number;
  onUpdate: (i: number, partial: Partial<ExtractedLoreFact>) => void;
  onDelete: (i: number) => void;
  onConvertToAxiom: (i: number) => void;
  onPromoteToRule: (i: number) => void;
  canPromoteToRule: boolean;
}) {
  const typeColors: Record<string, string> = {
    state: "tag-cyan",
    relationship: "tag-purple",
    attribute: "tag-amber",
    occurrence: "tag-red",
    rule: "tag-emerald",
    mechanic: "tag-emerald",
  };

  return (
    <motion.div layout initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className={ROW_CLASSNAME}>
      <BookOpen className="mt-0.5 h-4 w-4 shrink-0 text-amber-400" />
      <div className="min-w-0 flex-1 space-y-1.5">
        <div className="flex flex-wrap items-center gap-2">
          <select
            value={fact.fact_type || "state"}
            onChange={(e) => onUpdate(index, { fact_type: e.target.value })}
            className={cn("rounded border bg-bg-card px-2 py-0.5 text-[10px]", typeColors[fact.fact_type] ?? "tag-dim")}
          >
            {!FACT_TYPE_OPTIONS.includes((fact.fact_type || "state") as (typeof FACT_TYPE_OPTIONS)[number]) && (
              <option value={fact.fact_type}>{fact.fact_type}</option>
            )}
            {FACT_TYPE_OPTIONS.map((option) => (
              <option key={option} value={option}>{option}</option>
            ))}
          </select>
          {fact.entity_names.length > 0 && (
            <span className="truncate text-[10px] text-fg-muted">
              re: {fact.entity_names.slice(0, 3).join(", ")}
            </span>
          )}
          <span className="ml-auto text-xs text-fg-muted opacity-0 group-hover/row:opacity-60">
            {Math.round(fact.confidence * 100)}%
          </span>
        </div>
        <p className="text-sm text-fg-primary">
          <InlineEdit
            value={fact.statement}
            multiline
            onSave={(v) => onUpdate(index, { statement: v })}
          />
        </p>
      </div>
      <RowKebabMenu>
        <button
          onClick={() => onConvertToAxiom(index)}
          className="w-full flex items-center gap-2.5 px-3 py-2.5 text-left text-xs text-fg-secondary hover:bg-white/5 transition-colors"
        >
          <Sparkles className="w-3.5 h-3.5 text-purple-400" />
          Move to axiom
        </button>
        <button
          onClick={() => onPromoteToRule(index)}
          disabled={!canPromoteToRule}
          className="w-full flex items-center gap-2.5 px-3 py-2.5 text-left text-xs text-fg-secondary hover:bg-white/5 transition-colors disabled:opacity-40"
          title={canPromoteToRule ? "Promote this lore fact into the linked system rules" : "This pack does not have a linked game system yet"}
        >
          <Layers className="w-3.5 h-3.5 text-emerald-400" />
          Promote to rule
        </button>
        <div className="border-t border-white/5" />
        <button
          onClick={() => onDelete(index)}
          className="w-full flex items-center gap-2.5 px-3 py-2.5 text-left text-xs text-red-400 hover:bg-red-500/5 transition-colors"
        >
          <Trash2 className="w-3.5 h-3.5" />
          Delete
        </button>
      </RowKebabMenu>
    </motion.div>
  );
}

export function RuleRow({
  rule,
  index,
  onUpdate,
  onDelete,
}: {
  rule: RuleInfo;
  index: number;
  onUpdate: (i: number, partial: Partial<RuleInfo>) => void;
  onDelete: (i: number) => void;
}) {
  return (
    <motion.div layout initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className={ROW_CLASSNAME}>
      <Layers className="mt-0.5 h-4 w-4 shrink-0 text-emerald-400" />
      <div className="min-w-0 flex-1 space-y-1.5">
        <div className="flex flex-wrap items-center gap-2">
          <select
            value={rule.rule_type || "custom"}
            onChange={(e) => onUpdate(index, { rule_type: e.target.value })}
            className="rounded border border-border bg-bg-card px-2 py-0.5 text-[10px] text-fg-secondary"
          >
            {RULE_TYPE_OPTIONS.map((option) => (
              <option key={option} value={option}>{option}</option>
            ))}
          </select>
        </div>
        <div className="text-sm font-semibold text-fg-primary">
          <InlineEdit value={rule.name} onSave={(v) => onUpdate(index, { name: v })} />
        </div>
        <p className="text-sm text-fg-primary">
          <InlineEdit
            value={rule.description ?? ""}
            multiline
            onSave={(v) => onUpdate(index, { description: v })}
          />
        </p>
        <p className="text-[11px] text-fg-muted">
          Formula: <InlineEdit value={rule.formula ?? ""} onSave={(v) => onUpdate(index, { formula: v || null })} />
        </p>
      </div>
      <RowKebabMenu>
        <button
          onClick={() => onDelete(index)}
          className="w-full flex items-center gap-2.5 px-3 py-2.5 text-left text-xs text-red-400 hover:bg-red-500/5 transition-colors"
        >
          <Trash2 className="w-3.5 h-3.5" />
          Delete
        </button>
      </RowKebabMenu>
    </motion.div>
  );
}

export function PackListItem({
  pack,
  selected,
  onClick,
  onDelete,
}: {
  pack: KnowledgePack;
  selected: boolean;
  onClick: () => void;
  onDelete?: () => void;
}) {
  const statusColor: Record<string, string> = {
    ready: "tag-emerald",
    applied: "tag-cyan",
    archived: "tag-dim",
    pending: "tag-amber",
    review_pending: "tag-amber",
    error: "tag-red",
  };

  return (
    <div className="group/pack relative">
      <button
        onClick={onClick}
        className={cn(
          "w-full rounded-lg border px-3 py-2.5 pr-8 text-left transition-all",
          selected
            ? "border-accent-primary bg-accent-primary/10 text-fg-primary"
            : "border-transparent text-fg-secondary hover:border-border hover:bg-bg-hover",
          pack.status === "archived" && "opacity-50",
        )}
      >
        <div className="flex items-start gap-2">
          <FlaskConical className={cn("mt-0.5 h-4 w-4 shrink-0", selected ? "text-accent-primary" : "text-fg-muted")} />
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium">{pack.name}</p>
            <p className="mt-0.5 text-[10px] text-fg-muted">
              {pack.entity_count}E · {pack.axiom_count}A · {pack.lore_fact_count}L
            </p>
            {pack.system_name && <p className="truncate text-[10px] text-accent-primary/80">{pack.system_name}</p>}
            <div className="mt-1 flex flex-wrap items-center gap-1">
              <span className={cn("rounded border px-1.5 py-0.5 text-[9px]", statusColor[pack.status] ?? "tag-dim")}>
                {pack.status}
              </span>
              {pack.parent_pack_ids && pack.parent_pack_ids.length > 0 && (
                <span className="tag-purple rounded border px-1.5 py-0.5 text-[9px]" title="Has lineage">
                  lineage
                </span>
              )}
            </div>
          </div>
        </div>
      </button>
      {onDelete && (
        <button
          className="absolute right-1.5 top-1/2 -translate-y-1/2 p-1 rounded text-fg-muted opacity-0 group-hover/pack:opacity-100 hover:text-red-400 hover:bg-red-500/10 transition-all"
          title={pack.status === "archived" ? "Delete pack" : "Archive pack"}
          onClick={(e) => {
            e.stopPropagation();
            onDelete();
          }}
        >
          {pack.status === "archived" ? <Trash2 className="h-3 w-3" /> : <Archive className="h-3 w-3" />}
        </button>
      )}
    </div>
  );
}
