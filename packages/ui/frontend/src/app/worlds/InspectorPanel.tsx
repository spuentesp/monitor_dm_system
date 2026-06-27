"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import {
  X, Edit3, Save, Trash2, Plus, Link2, Loader2,
  MapPin, Users, Shield, Brain, Sparkles, Tag, Network,
  Layers, Globe2, FlaskConical,
} from "lucide-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { entitiesApi } from "@/lib/api";
import { WORLDS_KEYS } from "@/lib/query-keys";
import { cn } from "@/lib/utils";
import type { GraphNodeData, GraphNodeKind } from "@/lib/types";
import type { Node } from "@xyflow/react";

// Minimal per-kind config (border + bg + icon + colors) used by the
// inspector for node chrome. Subset of the worldGraph KIND_CONFIG —
// lives here so this file is self-contained and doesn't break when
// other extraction work happens.
const KIND_CONFIG: Record<
  GraphNodeKind,
  { border: string; bg: string; icon: React.ElementType; iconColor: string; tagClass: string; label: string }
> = {
  multiverse: { border: "border-purple-500/40", bg: "bg-purple-500/8",  icon: Layers,    iconColor: "text-purple-400",  tagClass: "tag-purple",  label: "Multiverse" },
  universe:   { border: "border-cyan-500/40",   bg: "bg-cyan-500/8",    icon: Globe2,    iconColor: "text-cyan-400",    tagClass: "tag-cyan",    label: "Universe" },
  character:  { border: "border-emerald-500/40",bg: "bg-emerald-500/8", icon: Users,     iconColor: "text-emerald-400", tagClass: "tag-emerald", label: "Character" },
  location:   { border: "border-amber-500/40",  bg: "bg-amber-500/8",   icon: MapPin,    iconColor: "text-amber-400",   tagClass: "tag-amber",   label: "Location" },
  faction:    { border: "border-red-500/40",    bg: "bg-red-500/8",     icon: Shield,    iconColor: "text-red-400",     tagClass: "tag-red",     label: "Faction" },
  concept:    { border: "border-violet-500/40", bg: "bg-violet-500/8",  icon: Brain,     iconColor: "text-violet-400",  tagClass: "tag-violet",  label: "Concept" },
  axiom:      { border: "border-slate-500/40",  bg: "bg-slate-500/8",   icon: Sparkles,  iconColor: "text-slate-400",   tagClass: "tag-slate",   label: "Axiom" },
  lore:       { border: "border-teal-500/40",   bg: "bg-teal-500/8",    icon: Tag,       iconColor: "text-teal-400",    tagClass: "tag-teal",    label: "Lore" },
  rule:       { border: "border-orange-500/40", bg: "bg-orange-500/8",  icon: FlaskConical, iconColor: "text-orange-400", tagClass: "tag-orange", label: "Rule" },
  pack:       { border: "border-pink-500/40",   bg: "bg-pink-500/8",    icon: Sparkles,  iconColor: "text-pink-400",   tagClass: "tag-pink",    label: "Pack" },
};

export function InspectorPanel({ node, onFocusEntity }: { node: Node<GraphNodeData> | null; onFocusEntity?: (id: string, label: string) => void }) {
  const qc = useQueryClient();
  const editable = !!node && !["multiverse", "universe"].includes(node.data.kind);

  // ── Edit state (M-36) ──────────────────────────────────────
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [tags, setTags] = useState<string[]>([]);
  const [tagInput, setTagInput] = useState("");

  // Reset the draft whenever a different node is selected.
  useEffect(() => {
    setEditing(false);
    setName(node?.data.label ?? "");
    setDescription(node?.data.description ?? "");
    setTags(node?.data.tags ?? []);
    setTagInput("");
  }, [node?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const save = useMutation({
    mutationFn: () =>
      entitiesApi.updateEntity(node!.id, {
        name: name.trim(),
        description: description.trim(),
        tags,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: WORLDS_KEYS.graphBase });
      setEditing(false);
    },
  });

  if (!node) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center text-center px-6 gap-3">
        <Network className="w-10 h-10 text-slate-800" />
        <p className="text-sm text-slate-500">Select a node</p>
        <p className="text-xs text-slate-700 leading-relaxed">
          Click any entity in the graph to inspect and edit it.
        </p>
      </div>
    );
  }

  const cfg = KIND_CONFIG[node.data.kind as GraphNodeKind];
  const Icon = cfg.icon;

  const addTag = () => {
    const t = tagInput.trim();
    if (t && !tags.includes(t)) setTags([...tags, t]);
    setTagInput("");
  };

  return (
    <div className="flex-1 overflow-y-auto p-4 space-y-4">
      <div className="flex items-start gap-3">
        <div className={cn("p-2.5 rounded-xl border flex-shrink-0", cfg.bg, cfg.border)}>
          <Icon className={cn("w-5 h-5", cfg.iconColor)} />
        </div>
        <div className="flex-1 min-w-0">
          {editing ? (
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="input-cyber w-full text-sm py-1"
              placeholder="Name"
            />
          ) : (
            <h2 className="text-base font-semibold text-slate-100 leading-tight truncate">
              {node.data.label}
            </h2>
          )}
          <span className={cn("text-[10px] mt-1 inline-block", cfg.tagClass)}>{cfg.label}</span>
        </div>
        {editable && !editing && (
          <button
            onClick={() => setEditing(true)}
            className="p-1.5 rounded text-slate-500 hover:text-purple-300 transition-colors"
            title="Edit entity"
          >
            <Edit3 className="w-3.5 h-3.5" />
          </button>
        )}
      </div>

      <div>
        <p className="text-[10px] text-slate-600 uppercase tracking-wider mb-1.5">Description</p>
        {editing ? (
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={4}
            className="input-cyber w-full text-sm resize-none"
            placeholder="Describe this entity…"
          />
        ) : node.data.description ? (
          <p className="text-sm text-slate-400 leading-relaxed">{node.data.description}</p>
        ) : (
          <p className="text-xs text-slate-700 italic">No description.</p>
        )}
      </div>

      {!editing && node.data.subtitle && (
        <div>
          <p className="text-[10px] text-slate-600 uppercase tracking-wider mb-1.5">Details</p>
          <p className="text-sm text-slate-400">{node.data.subtitle}</p>
        </div>
      )}

      <div>
        <p className="text-[10px] text-slate-600 uppercase tracking-wider mb-2">Tags</p>
        <div className="flex flex-wrap gap-1.5">
          {tags.map((t) => (
            <span key={t} className="tag-dim inline-flex items-center gap-1">
              {t}
              {editing && (
                <button
                  onClick={() => setTags(tags.filter((x) => x !== t))}
                  aria-label={`Remove tag ${t}`}
                  className="text-slate-500 hover:text-red-300"
                >
                  <X className="w-2.5 h-2.5" />
                </button>
              )}
            </span>
          ))}
          {!editing && tags.length === 0 && (
            <span className="text-xs text-slate-700 italic">No tags.</span>
          )}
        </div>
        {editing && (
          <div className="flex items-center gap-1.5 mt-2">
            <input
              value={tagInput}
              onChange={(e) => setTagInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addTag(); } }}
              className="input-cyber flex-1 text-xs py-1"
              placeholder="Add tag + Enter"
            />
            <button onClick={addTag} aria-label="Add tag" className="p-1 text-purple-400 hover:text-purple-300">
              <Plus className="w-3.5 h-3.5" />
            </button>
          </div>
        )}
      </div>

      <div>
        <p className="text-[10px] text-slate-600 uppercase tracking-wider mb-1">ID</p>
        <p className="font-mono text-xs text-slate-700">{node.id}</p>
      </div>

      {editing ? (
        <div className="space-y-2 pt-1">
          {save.isError && (
            <p className="text-[11px] text-red-300">
              Save failed: {(save.error as Error)?.message}
            </p>
          )}
          <div className="flex gap-2">
            <button
              onClick={() => save.mutate()}
              disabled={save.isPending || !name.trim()}
              className="btn-cyber flex-1 justify-center text-xs py-1.5 disabled:opacity-40"
            >
              {save.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
              Save
            </button>
            <button
              onClick={() => setEditing(false)}
              disabled={save.isPending}
              className="btn-ghost flex-1 justify-center text-xs py-1.5 border border-white/10"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <div className="flex gap-2 pt-1">
          {onFocusEntity && editable && (
            <button
              onClick={() => onFocusEntity(node.id, node.data.label)}
              className="btn-ghost flex-1 justify-center text-xs py-1.5 text-purple-400 hover:text-purple-300 border border-purple-500/20"
              title="Show connections"
            >
              <Link2 className="w-3.5 h-3.5" />
              Focus
            </button>
          )}
          {node.data.kind === "universe" && (
            <a
              href={`/worlds?universe=${node.id}`}
              className="btn-cyber flex-1 justify-center text-xs py-1.5"
              title="Open in the tree with stories and scenes"
            >
              <Globe2 className="w-3.5 h-3.5" />
              Open tree
            </a>
          )}
        </div>
      )}
    </div>
  );
}
