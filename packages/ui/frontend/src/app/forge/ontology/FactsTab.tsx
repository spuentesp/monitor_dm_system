"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, Pencil, Plus, Sparkles, Trash2 } from "lucide-react";
import { DialogFooter, DialogShell } from "@/components/DialogShell";
import { entitiesApi } from "@/lib/api";
import type { OntologyFact } from "@/lib/types";
import {
  CANON_LEVELS,
  EnumSelect,
  Field,
  ListState,
  SIMULATION_SCOPES,
  Tag,
} from "./shared";

// Facts tab of /forge/ontology (F2-2 phase 6). Filterable list + create /
// edit / delete against the wave-1 ontology CRUD endpoints.

const FACT_TYPES = ["state", "relationship", "attribute", "occurrence"] as const;
const FACT_STATUSES = ["active", "superseded", "tombstoned"] as const;
const KNOWLEDGE_SCOPES = ["world", "character", "player", "faction", "rumor"] as const;

interface FactFilters {
  fact_type: string;
  canon_level: string;
  status: string;
  scope: string;
  min_magnitude: number;
}

const DEFAULT_FILTERS: FactFilters = {
  fact_type: "",
  canon_level: "",
  status: "",
  scope: "",
  min_magnitude: 1,
};

export function FactsTab({ universeId }: { universeId: string }) {
  const qc = useQueryClient();
  const [filters, setFilters] = useState<FactFilters>(DEFAULT_FILTERS);
  const [showCreate, setShowCreate] = useState(false);
  const [editing, setEditing] = useState<OntologyFact | null>(null);

  const queryFilters = {
    fact_type: filters.fact_type || undefined,
    canon_level: filters.canon_level || undefined,
    status: filters.status || undefined,
    scope: filters.scope || undefined,
    min_magnitude: filters.min_magnitude,
    limit: 100,
  };

  const factsQ = useQuery({
    queryKey: ["ontology-facts", universeId, queryFilters],
    queryFn: () => entitiesApi.listFacts(universeId, queryFilters),
  });
  const facts = factsQ.data?.facts ?? [];

  const invalidate = () =>
    qc.invalidateQueries({ queryKey: ["ontology-facts", universeId] });

  const deleteMut = useMutation({
    mutationFn: (id: string) => entitiesApi.deleteFact(id, { force: true }),
    onSuccess: invalidate,
  });

  const set = (patch: Partial<FactFilters>) => setFilters((f) => ({ ...f, ...patch }));

  return (
    <div className="flex flex-col h-full overflow-y-auto px-6 py-4 space-y-4">
      {/* Filter row */}
      <div className="flex flex-wrap items-end gap-3">
        <Field label="Type">
          <EnumSelect
            ariaLabel="Filter by fact type"
            value={filters.fact_type}
            onChange={(v) => set({ fact_type: v })}
            options={FACT_TYPES}
            allowAll
          />
        </Field>
        <Field label="Canon level">
          <EnumSelect
            ariaLabel="Filter by canon level"
            value={filters.canon_level}
            onChange={(v) => set({ canon_level: v })}
            options={CANON_LEVELS}
            allowAll
          />
        </Field>
        <Field label="Status">
          <EnumSelect
            ariaLabel="Filter by status"
            value={filters.status}
            onChange={(v) => set({ status: v })}
            options={FACT_STATUSES}
            allowAll
          />
        </Field>
        <Field label="Scope">
          <EnumSelect
            ariaLabel="Filter by scope"
            value={filters.scope}
            onChange={(v) => set({ scope: v })}
            options={SIMULATION_SCOPES}
            allowAll
          />
        </Field>
        <Field label="Min magnitude">
          <input
            aria-label="Filter by minimum magnitude"
            type="number"
            min={1}
            max={10}
            className="input-cyber py-1 text-xs w-20"
            value={filters.min_magnitude}
            onChange={(e) =>
              set({ min_magnitude: Math.max(1, Math.min(10, Number(e.target.value) || 1)) })
            }
          />
        </Field>
        <div className="flex-1" />
        <button className="btn-cyber text-xs py-1.5" onClick={() => setShowCreate(true)}>
          <Plus className="w-3.5 h-3.5" /> New fact
        </button>
      </div>

      <ListState
        isLoading={factsQ.isLoading}
        isError={factsQ.isError}
        error={factsQ.error}
        isEmpty={facts.length === 0}
        emptyMessage="No facts match the current filters."
      />

      {/* List */}
      <div className="space-y-2">
        {facts.map((f) => (
          <div
            key={f.id}
            className="glass-dark rounded-lg border border-white/5 px-4 py-3 flex items-start gap-3"
          >
            <div className="flex-1 min-w-0">
              <p className="text-sm text-slate-200 leading-relaxed">{f.statement}</p>
              <div className="flex flex-wrap items-center gap-1.5 mt-1.5">
                <Tag>{f.fact_type}</Tag>
                <Tag>{f.canon_level}</Tag>
                <Tag>{f.status}</Tag>
                <Tag>{f.scope}</Tag>
                <span className="text-[10px] text-slate-600">
                  magnitude {f.magnitude} · {Math.round(f.confidence * 100)}% conf
                </span>
              </div>
            </div>
            <button
              aria-label={`Edit fact ${f.statement}`}
              className="p-1.5 text-slate-500 hover:text-cyan-300"
              onClick={() => setEditing(f)}
            >
              <Pencil className="w-3.5 h-3.5" />
            </button>
            <button
              aria-label={`Delete fact ${f.statement}`}
              className="p-1.5 text-slate-500 hover:text-red-300 disabled:opacity-40"
              disabled={deleteMut.isPending}
              onClick={() => {
                if (window.confirm(`Delete fact "${f.statement}"? This cannot be undone.`)) {
                  deleteMut.mutate(f.id);
                }
              }}
            >
              <Trash2 className="w-3.5 h-3.5" />
            </button>
          </div>
        ))}
      </div>

      {showCreate && (
        <FactFormModal
          universeId={universeId}
          onClose={() => setShowCreate(false)}
          onSaved={() => {
            setShowCreate(false);
            invalidate();
          }}
        />
      )}
      {editing && (
        <FactFormModal
          universeId={universeId}
          fact={editing}
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

function FactFormModal({
  universeId,
  fact,
  onClose,
  onSaved,
}: {
  universeId: string;
  /** When set, the modal edits that fact; otherwise it creates a new one. */
  fact?: OntologyFact;
  onClose: () => void;
  onSaved: () => void;
}) {
  const isEdit = !!fact;
  const [statement, setStatement] = useState(fact?.statement ?? "");
  const [factType, setFactType] = useState<string>(fact?.fact_type ?? "state");
  const [canonLevel, setCanonLevel] = useState<string>(fact?.canon_level ?? "canon");
  const [knowledgeScope, setKnowledgeScope] = useState<string>(
    fact?.knowledge_scope ?? "world",
  );
  const [status, setStatus] = useState<string>(fact?.status ?? "active");
  const [magnitude, setMagnitude] = useState<number>(fact?.magnitude ?? 1);
  const [scope, setScope] = useState<string>(fact?.scope ?? "local");
  const [confidence, setConfidence] = useState<number>(fact?.confidence ?? 1);

  const save = useMutation({
    mutationFn: () =>
      isEdit
        ? entitiesApi.updateFact(fact!.id, {
            statement: statement.trim(),
            canon_level: canonLevel,
            knowledge_scope: knowledgeScope,
            status,
            confidence,
          })
        : entitiesApi.createFact(universeId, {
            statement: statement.trim(),
            fact_type: factType,
            canon_level: canonLevel,
            knowledge_scope: knowledgeScope,
            magnitude,
            scope,
            confidence,
          }),
    onSuccess: onSaved,
  });

  return (
    <DialogShell
      title={isEdit ? "Edit fact" : "New fact"}
      icon={Sparkles}
      onClose={onClose}
      footer={
        <DialogFooter>
          <button className="btn-ghost text-xs" onClick={onClose} disabled={save.isPending}>
            Cancel
          </button>
          <button
            className="btn-cyber text-xs py-1.5 disabled:opacity-40"
            disabled={save.isPending || !statement.trim()}
            onClick={() => save.mutate()}
          >
            {save.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : null}
            {isEdit ? "Save changes" : "Create fact"}
          </button>
        </DialogFooter>
      }
    >
      <div className="p-4 space-y-3">
        <Field label="Statement">
          <textarea
            aria-label="Statement"
            className="input-cyber w-full text-sm resize-none"
            rows={3}
            value={statement}
            onChange={(e) => setStatement(e.target.value)}
            placeholder="e.g. The bridge over the Greywater is broken"
          />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          {!isEdit && (
            <Field label="Type">
              <EnumSelect
                ariaLabel="Fact type"
                value={factType}
                onChange={setFactType}
                options={FACT_TYPES}
              />
            </Field>
          )}
          <Field label="Canon level">
            <EnumSelect
              ariaLabel="Canon level"
              value={canonLevel}
              onChange={setCanonLevel}
              options={CANON_LEVELS}
            />
          </Field>
          <Field label="Knowledge scope">
            <EnumSelect
              ariaLabel="Knowledge scope"
              value={knowledgeScope}
              onChange={setKnowledgeScope}
              options={KNOWLEDGE_SCOPES}
            />
          </Field>
          {isEdit && (
            <Field label="Status">
              <EnumSelect
                ariaLabel="Status"
                value={status}
                onChange={setStatus}
                options={FACT_STATUSES}
              />
            </Field>
          )}
          {!isEdit && (
            <>
              <Field label="Magnitude">
                <input
                  aria-label="Magnitude"
                  type="number"
                  min={1}
                  max={10}
                  className="input-cyber py-1 text-xs w-full"
                  value={magnitude}
                  onChange={(e) => setMagnitude(Number(e.target.value) || 1)}
                />
              </Field>
              <Field label="Scope">
                <EnumSelect
                  ariaLabel="Scope"
                  value={scope}
                  onChange={setScope}
                  options={SIMULATION_SCOPES}
                />
              </Field>
            </>
          )}
          <Field label="Confidence (0–1)">
            <input
              aria-label="Confidence"
              type="number"
              min={0}
              max={1}
              step={0.05}
              className="input-cyber py-1 text-xs w-full"
              value={confidence}
              onChange={(e) => setConfidence(Number(e.target.value))}
            />
          </Field>
        </div>
        {save.isError && (
          <p className="text-[11px] text-red-300">
            Save failed: {(save.error as Error)?.message}
          </p>
        )}
      </div>
    </DialogShell>
  );
}
