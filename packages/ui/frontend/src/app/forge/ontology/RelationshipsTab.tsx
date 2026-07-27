"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { GitBranch, Loader2, Pencil, Plus, Trash2 } from "lucide-react";
import { DialogFooter, DialogShell } from "@/components/DialogShell";
import { entitiesApi, graphApi } from "@/lib/api";
import type { EntityRelationship } from "@/lib/types";
import { truncate } from "@/lib/utils";
import { EnumSelect, Field, ListState, Tag } from "./shared";

// Relationships tab of /forge/ontology (F2-2 phases 2 & 6). Lists the
// universe's edges via the universe-scoped list endpoint, creates via the
// existing M-37 edge endpoint, edits/deletes via the wave-1 endpoints.

const REL_TYPES = [
  "RELATED_TO",
  "KNOWS",
  "ALLIED_WITH",
  "HOSTILE_TO",
  "MEMBER_OF",
  "PART_OF",
  "SUBGROUP_OF",
  "AFFILIATED_WITH",
  "WORKS_FOR",
  "LEADS",
  "OWNS",
  "LOCATED_IN",
  "CONTAINS",
  "PARTICIPATES_IN",
  "SUBTYPE_OF",
  "INSTANCE_OF",
  "DERIVES_FROM",
  "CONTROLS",
  "CONTROLLED_BY",
  "REVERES",
] as const;

const REL_CATEGORIES = [
  "social",
  "membership",
  "ownership",
  "spatial",
  "temporal",
  "taxonomic",
  "power",
  "generic",
] as const;

export function RelationshipsTab({ universeId }: { universeId: string }) {
  const qc = useQueryClient();
  const [relType, setRelType] = useState("");
  const [category, setCategory] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [editing, setEditing] = useState<EntityRelationship | null>(null);

  const queryFilters = {
    rel_type: relType || undefined,
    category: category || undefined,
    limit: 500,
  };

  const relsQ = useQuery({
    queryKey: ["ontology-relationships", universeId, queryFilters],
    queryFn: () => entitiesApi.listUniverseRelationships(universeId, queryFilters),
  });
  const relationships = relsQ.data?.relationships ?? [];

  // id → entity label map for readable rows and the create form's pickers.
  const graphQ = useQuery({
    queryKey: ["universeGraph", universeId, "ontology-labels"],
    queryFn: () =>
      graphApi.getUniverseGraph(universeId, { depth: 1, limit_per_depth: 500 }),
  });
  const entityNames = useMemo(() => {
    const map = new Map<string, string>();
    for (const n of graphQ.data?.nodes ?? []) {
      map.set(n.id, n.data?.label ?? n.id);
    }
    return map;
  }, [graphQ.data]);

  const nameOf = (id: string) => entityNames.get(id) ?? truncate(id, 10);

  const invalidate = () =>
    qc.invalidateQueries({ queryKey: ["ontology-relationships", universeId] });

  const deleteMut = useMutation({
    mutationFn: (id: string) => entitiesApi.deleteRelationship(id),
    onSuccess: invalidate,
  });

  return (
    <div className="flex flex-col h-full overflow-y-auto px-6 py-4 space-y-4">
      {/* Filter row */}
      <div className="flex flex-wrap items-end gap-3">
        <Field label="Type">
          <EnumSelect
            ariaLabel="Filter by relationship type"
            value={relType}
            onChange={setRelType}
            options={REL_TYPES}
            allowAll
          />
        </Field>
        <Field label="Category">
          <EnumSelect
            ariaLabel="Filter by category"
            value={category}
            onChange={setCategory}
            options={REL_CATEGORIES}
            allowAll
          />
        </Field>
        <div className="flex-1" />
        <button
          className="btn-cyber text-xs py-1.5"
          onClick={() => setShowCreate(true)}
          disabled={entityNames.size === 0}
          title={entityNames.size === 0 ? "No entities in this universe yet" : undefined}
        >
          <Plus className="w-3.5 h-3.5" /> New relationship
        </button>
      </div>

      <ListState
        isLoading={relsQ.isLoading}
        isError={relsQ.isError}
        error={relsQ.error}
        isEmpty={relationships.length === 0}
        emptyMessage="No relationships match the current filters."
      />

      {/* List */}
      <div className="space-y-2">
        {relationships.map((r) => (
          <div
            key={r.relationship_id}
            className="glass-dark rounded-lg border border-white/5 px-4 py-3 flex items-start gap-3"
          >
            <div className="flex-1 min-w-0">
              <p className="text-sm text-slate-200 leading-relaxed">
                {nameOf(r.from_entity_id)}
                <span className="text-cyan-400 mx-2">{r.rel_type.replace(/_/g, " ")}</span>
                {nameOf(r.to_entity_id)}
              </p>
              <div className="flex flex-wrap items-center gap-1.5 mt-1.5">
                <Tag>{r.category}</Tag>
                {r.tags.map((t) => (
                  <Tag key={t}>{t}</Tag>
                ))}
                <span className="text-[10px] text-slate-700 font-mono">
                  edge #{r.relationship_id}
                </span>
              </div>
            </div>
            <button
              aria-label={`Edit relationship ${r.relationship_id}`}
              className="p-1.5 text-slate-500 hover:text-cyan-300"
              onClick={() => setEditing(r)}
            >
              <Pencil className="w-3.5 h-3.5" />
            </button>
            <button
              aria-label={`Delete relationship ${r.relationship_id}`}
              className="p-1.5 text-slate-500 hover:text-red-300 disabled:opacity-40"
              disabled={deleteMut.isPending}
              onClick={() => {
                if (
                  window.confirm(
                    `Delete relationship ${nameOf(r.from_entity_id)} → ${nameOf(r.to_entity_id)}? This cannot be undone.`,
                  )
                ) {
                  deleteMut.mutate(r.relationship_id);
                }
              }}
            >
              <Trash2 className="w-3.5 h-3.5" />
            </button>
          </div>
        ))}
      </div>

      {showCreate && (
        <RelationshipCreateModal
          universeId={universeId}
          entityNames={entityNames}
          onClose={() => setShowCreate(false)}
          onSaved={() => {
            setShowCreate(false);
            invalidate();
          }}
        />
      )}
      {editing && (
        <RelationshipEditModal
          relationship={editing}
          nameOf={nameOf}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            invalidate();
          }}
        />
      )}
    </div>
  );
}

function RelationshipCreateModal({
  universeId,
  entityNames,
  onClose,
  onSaved,
}: {
  universeId: string;
  entityNames: Map<string, string>;
  onClose: () => void;
  onSaved: () => void;
}) {
  const entityIds = [...entityNames.keys()];
  const [fromId, setFromId] = useState(entityIds[0] ?? "");
  const [toId, setToId] = useState(entityIds[1] ?? entityIds[0] ?? "");
  const [relType, setRelType] = useState<string>(REL_TYPES[0]);

  const save = useMutation({
    mutationFn: () =>
      entitiesApi.createRelationship({ from_id: fromId, to_id: toId, rel_type: relType }),
    onSuccess: onSaved,
  });

  const entitySelect = (
    ariaLabel: string,
    value: string,
    onChange: (v: string) => void,
  ) => (
    <select
      aria-label={ariaLabel}
      className="input-cyber py-1 text-xs w-full"
      value={value}
      onChange={(e) => onChange(e.target.value)}
    >
      {entityIds.map((id) => (
        <option key={id} value={id}>
          {entityNames.get(id)}
        </option>
      ))}
    </select>
  );

  return (
    <DialogShell
      title="New relationship"
      icon={GitBranch}
      onClose={onClose}
      footer={
        <DialogFooter>
          <button className="btn-ghost text-xs" onClick={onClose} disabled={save.isPending}>
            Cancel
          </button>
          <button
            className="btn-cyber text-xs py-1.5 disabled:opacity-40"
            disabled={save.isPending || !fromId || !toId || fromId === toId}
            onClick={() => save.mutate()}
          >
            {save.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : null}
            Create relationship
          </button>
        </DialogFooter>
      }
    >
      <div className="p-4 space-y-3">
        <Field label="From entity">{entitySelect("From entity", fromId, setFromId)}</Field>
        <Field label="To entity">{entitySelect("To entity", toId, setToId)}</Field>
        <Field label="Type">
          <EnumSelect
            ariaLabel="Relationship type"
            value={relType}
            onChange={setRelType}
            options={REL_TYPES}
          />
        </Field>
        {fromId && fromId === toId && (
          <p className="text-[11px] text-amber-300">
            A relationship needs two different entities.
          </p>
        )}
        {save.isError && (
          <p className="text-[11px] text-red-300">
            Save failed: {(save.error as Error)?.message}
          </p>
        )}
      </div>
    </DialogShell>
  );
}

function RelationshipEditModal({
  relationship,
  nameOf,
  onClose,
  onSaved,
}: {
  relationship: EntityRelationship;
  nameOf: (id: string) => string;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [category, setCategory] = useState(relationship.category);
  const [tagsText, setTagsText] = useState(relationship.tags.join(", "));
  const [propsText, setPropsText] = useState(
    Object.keys(relationship.properties ?? {}).length > 0
      ? JSON.stringify(relationship.properties, null, 2)
      : "",
  );
  const [propsError, setPropsError] = useState<string | null>(null);

  const save = useMutation({
    mutationFn: () => {
      let properties: Record<string, unknown> | undefined;
      const raw = propsText.trim();
      if (raw) {
        try {
          const parsed = JSON.parse(raw) as unknown;
          if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
            throw new Error("Properties must be a JSON object");
          }
          properties = parsed as Record<string, unknown>;
        } catch (err) {
          setPropsError((err as Error).message);
          throw err;
        }
      }
      setPropsError(null);
      return entitiesApi.updateRelationship(relationship.relationship_id, {
        category,
        tags: tagsText
          .split(",")
          .map((t) => t.trim())
          .filter(Boolean),
        properties,
      });
    },
    onSuccess: onSaved,
  });

  return (
    <DialogShell
      title="Edit relationship"
      icon={GitBranch}
      onClose={onClose}
      footer={
        <DialogFooter>
          <button className="btn-ghost text-xs" onClick={onClose} disabled={save.isPending}>
            Cancel
          </button>
          <button
            className="btn-cyber text-xs py-1.5 disabled:opacity-40"
            disabled={save.isPending}
            onClick={() => save.mutate()}
          >
            {save.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : null}
            Save changes
          </button>
        </DialogFooter>
      }
    >
      <div className="p-4 space-y-3">
        <p className="text-xs text-slate-400">
          {nameOf(relationship.from_entity_id)}
          <span className="text-cyan-400 mx-2">
            {relationship.rel_type.replace(/_/g, " ")}
          </span>
          {nameOf(relationship.to_entity_id)}
        </p>
        <Field label="Category">
          <EnumSelect
            ariaLabel="Category"
            value={category}
            onChange={setCategory}
            options={REL_CATEGORIES}
          />
        </Field>
        <Field label="Tags (comma-separated)">
          <input
            aria-label="Tags"
            className="input-cyber py-1 text-xs w-full"
            value={tagsText}
            onChange={(e) => setTagsText(e.target.value)}
            placeholder="grim, secret"
          />
        </Field>
        <Field label="Properties (JSON object, optional)">
          <textarea
            aria-label="Properties"
            className="input-cyber w-full text-xs font-mono resize-none"
            rows={4}
            value={propsText}
            onChange={(e) => setPropsText(e.target.value)}
            placeholder='{"since": "the war"}'
          />
        </Field>
        {propsError && <p className="text-[11px] text-red-300">{propsError}</p>}
        {save.isError && !propsError && (
          <p className="text-[11px] text-red-300">
            Save failed: {(save.error as Error)?.message}
          </p>
        )}
      </div>
    </DialogShell>
  );
}
