"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  BookOpen,
  ChevronRight,
  Copy,
  Dice5,
  Loader2,
  RefreshCw,
  Search,
  Trash2,
  Users,
} from "lucide-react";
import { templatesApi } from "@/lib/api";
import type { EntityTemplate } from "@/lib/types";
import { cn } from "@/lib/utils";

// ═══════════════════════════════════════════════════════════════
//  Entity type badge config
// ═══════════════════════════════════════════════════════════════

const ENTITY_TYPE_BADGE: Record<string, { color: string; bg: string; border: string }> = {
  character: { color: "text-amber-300", bg: "bg-amber-500/10", border: "border-amber-500/20" },
  npc: { color: "text-cyan-300", bg: "bg-cyan-500/10", border: "border-cyan-500/20" },
  creature: { color: "text-red-300", bg: "bg-red-500/10", border: "border-red-500/20" },
  location: { color: "text-emerald-300", bg: "bg-emerald-500/10", border: "border-emerald-500/20" },
  faction: { color: "text-purple-300", bg: "bg-purple-500/10", border: "border-purple-500/20" },
  item: { color: "text-blue-300", bg: "bg-blue-500/10", border: "border-blue-500/20" },
  concept: { color: "text-slate-300", bg: "bg-slate-500/10", border: "border-slate-500/20" },
};

function getTypeBadge(entityType: string) {
  return ENTITY_TYPE_BADGE[entityType] ?? ENTITY_TYPE_BADGE.concept;
}

// ═══════════════════════════════════════════════════════════════
//  Template Card
// ═══════════════════════════════════════════════════════════════

function TemplateCard({
  template,
  isSelected,
  onSelect,
  onDelete,
}: {
  template: EntityTemplate;
  isSelected: boolean;
  onSelect: () => void;
  onDelete: () => void;
}) {
  const badge = getTypeBadge(template.entity_type);
  const varCount = template.variable_properties?.length ?? 0;

  return (
    <button
      onClick={onSelect} aria-label="Select template"
      className={cn(
        "w-full text-left glass-dark rounded-xl border p-3 space-y-2 transition-all",
        isSelected
          ? "border-cyan-500/30 bg-cyan-500/5"
          : "border-white/5 hover:border-white/10 hover:bg-white/2"
      )}
    >
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold text-slate-200 truncate flex-1">{template.name}</span>
        <div className="flex items-center gap-1.5 flex-shrink-0 ml-2">
          <span className={cn("text-[10px] px-1.5 py-0.5 rounded border", badge.color, badge.bg, badge.border)}>
            {template.entity_type}
          </span>
          <button
            onClick={(e) => { e.stopPropagation(); onDelete(); }}
            className="text-slate-600 hover:text-red-400 transition-colors"
            title="Delete template"
          >
            <Trash2 className="w-3 h-3" />
          </button>
        </div>
      </div>

      {template.description && (
        <p className="text-[11px] text-slate-500 leading-relaxed line-clamp-2">{template.description}</p>
      )}

      <div className="flex items-center gap-3 text-[10px] text-slate-600">
        {varCount > 0 && <span className="flex items-center gap-0.5"><Dice5 className="w-2.5 h-2.5" /> {varCount} variable</span>}
        {template.usage_count > 0 && <span className="flex items-center gap-0.5"><Copy className="w-2.5 h-2.5" /> Used {template.usage_count}×</span>}
        {template.parent_template_id && <span className="flex items-center gap-0.5"><ChevronRight className="w-2.5 h-2.5" /> Inherited</span>}
      </div>
    </button>
  );
}

// ═══════════════════════════════════════════════════════════════
//  Template Detail
// ═══════════════════════════════════════════════════════════════

function TemplateDetail({
  template,
  onInstantiate,
}: {
  template: EntityTemplate;
  onInstantiate: () => void;
}) {
  const badge = getTypeBadge(template.entity_type);

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <BookOpen className="w-4 h-4 text-cyan-400" />
          <h3 className="text-sm font-semibold text-slate-200">{template.name}</h3>
        </div>
        <span className={cn("text-[10px] px-2 py-0.5 rounded border", badge.color, badge.bg, badge.border)}>
          {template.entity_type}
        </span>
      </div>

      {/* Description */}
      {template.description && (
        <p className="text-xs text-slate-400 leading-relaxed">{template.description}</p>
      )}

      {/* Base Properties */}
      {Object.keys(template.base_properties).length > 0 && (
        <section className="space-y-1.5">
          <h4 className="text-[10px] font-bold tracking-widest uppercase text-emerald-400">Base Properties</h4>
          <div className="glass-dark rounded-lg border border-white/5 p-2.5 space-y-1">
            {Object.entries(template.base_properties).map(([key, value]) => (
              <div key={key} className="flex items-center justify-between text-xs">
                <span className="text-slate-400">{key}</span>
                <span className="text-slate-200 font-mono">{String(value)}</span>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Variable Properties */}
      {template.variable_properties.length > 0 && (
        <section className="space-y-1.5">
          <h4 className="text-[10px] font-bold tracking-widest uppercase text-amber-400">Variable Properties</h4>
          <div className="space-y-1">
            {template.variable_properties.map((vp, i) => (
              <div key={i} className="glass-dark rounded-lg border border-white/5 px-2.5 py-2 flex items-center justify-between">
                <span className="text-xs text-slate-300 font-mono">{vp.property_path}</span>
                <span className="text-[10px] text-slate-500 bg-white/5 px-1.5 py-0.5 rounded">{vp.generation_type}</span>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Naming Pattern */}
      <section className="space-y-1.5">
        <h4 className="text-[10px] font-bold tracking-widest uppercase text-purple-400">Naming</h4>
        <div className="glass-dark rounded-lg border border-white/5 px-2.5 py-2 flex items-center justify-between">
          <span className="text-xs text-slate-300">{template.naming_pattern.type}</span>
          {template.naming_pattern.pattern && (
            <span className="text-[10px] text-slate-500 font-mono">{template.naming_pattern.pattern}</span>
          )}
        </div>
      </section>

      {/* State Tags */}
      {template.default_state_tags.length > 0 && (
        <section className="space-y-1.5">
          <h4 className="text-[10px] font-bold tracking-widest uppercase text-cyan-400">Default Tags</h4>
          <div className="flex flex-wrap gap-1.5">
            {template.default_state_tags.map((tag, i) => (
              <span key={i} className="text-[10px] bg-cyan-500/10 text-cyan-400 px-2 py-0.5 rounded-lg border border-cyan-500/20">
                {tag}
              </span>
            ))}
          </div>
        </section>
      )}

      {/* Instantiate button */}
      <button onClick={onInstantiate} className="btn-cyber w-full text-xs py-2 mt-2">
        <Users className="w-3.5 h-3.5" /> Instantiate from Template
      </button>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
//  Template Browser (main export)
// ═══════════════════════════════════════════════════════════════

interface TemplateBrowserProps {
  universeId: string | null;
  onInstantiate?: (template: EntityTemplate) => void;
}

export function TemplateBrowser({ universeId, onInstantiate }: TemplateBrowserProps) {
  const [search, setSearch] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [filterType, setFilterType] = useState<string | null>(null);
  const queryClient = useQueryClient();

  const { data: listData, isLoading, refetch } = useQuery({
    queryKey: ["templates", universeId, filterType],
    queryFn: () => templatesApi.list(universeId ?? undefined, filterType ?? undefined),
    enabled: true,
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => templatesApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["templates"] });
      if (selectedId) setSelectedId(null);
    },
  });

  const templates = listData?.templates ?? [];
  const filtered = search
    ? templates.filter((t) =>
        t.name.toLowerCase().includes(search.toLowerCase()) ||
        t.description.toLowerCase().includes(search.toLowerCase())
      )
    : templates;

  const selectedTemplate = selectedId ? templates.find((t) => t.template_id === selectedId) : null;

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Toolbar */}
      <div className="flex items-center gap-2 px-4 py-2 border-b border-white/5 flex-shrink-0">
        <BookOpen className="w-3.5 h-3.5 text-cyan-400 flex-shrink-0" />
        <span className="text-xs font-semibold text-slate-300 flex-1">Templates</span>
        <button onClick={() => refetch()} className="btn-ghost text-xs py-0.5 px-2">
          <RefreshCw className="w-3 h-3" />
        </button>
      </div>

      {/* Search + filter */}
      <div className="px-4 py-2 space-y-2 border-b border-white/5 flex-shrink-0">
        <div className="flex gap-2">
          <div className="relative flex-1">
            <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3 h-3 text-slate-600" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search templates..."
              className="input-cyber pl-7 py-1 text-xs w-full"
            />
          </div>
        </div>
        <div className="flex flex-wrap gap-1">
          {["all", "character", "npc", "creature", "location", "faction", "item"].map((type) => (
            <button
              key={type}
              onClick={() => setFilterType(type === "all" ? null : type)}
              className={cn(
                "text-[10px] px-2 py-0.5 rounded-lg border transition-all",
                (type === "all" ? !filterType : filterType === type)
                  ? "bg-cyan-500/15 text-cyan-300 border-cyan-500/30"
                  : "text-slate-500 border-white/5 hover:text-slate-300"
              )}
            >
              {type}
            </button>
          ))}
        </div>
      </div>

      {/* Content: list + detail */}
      <div className="flex-1 overflow-hidden flex">
        {/* List */}
        <div className={cn("overflow-y-auto px-3 py-3 space-y-2", selectedTemplate ? "w-1/2 border-r border-white/5" : "w-full")}>
          {isLoading && (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="w-5 h-5 text-slate-600 animate-spin" />
            </div>
          )}
          {!isLoading && filtered.length === 0 && (
            <div className="text-center py-8">
              <BookOpen className="w-8 h-8 text-slate-700 mx-auto mb-2" />
              <p className="text-xs text-slate-600">
                {universeId ? "No templates found" : "Select a universe to see templates"}
              </p>
            </div>
          )}
          {filtered.map((t) => (
            <TemplateCard
              key={t.template_id}
              template={t}
              isSelected={selectedId === t.template_id}
              onSelect={() => setSelectedId(selectedId === t.template_id ? null : t.template_id)}
              onDelete={() => deleteMutation.mutate(t.template_id)}
            />
          ))}
        </div>

        {/* Detail */}
        <AnimatePresence>
          {selectedTemplate && (
            <motion.div
              initial={{ opacity: 0, x: 12 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: 12 }}
              className="w-1/2 overflow-y-auto px-4 py-3"
            >
              <TemplateDetail
                template={selectedTemplate}
                onInstantiate={() => onInstantiate?.(selectedTemplate)}
              />
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Footer */}
      <div className="px-4 py-2 border-t border-white/5 flex-shrink-0 text-[10px] text-slate-700">
        {filtered.length} template{filtered.length !== 1 ? "s" : ""} · {listData?.total ?? 0} total
      </div>
    </div>
  );
}