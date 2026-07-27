"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Landmark, Loader2, Pencil, Plus, Trash2 } from "lucide-react";
import { DialogFooter, DialogShell } from "@/components/DialogShell";
import { entitiesApi } from "@/lib/api";
import type { OntologyAxiom } from "@/lib/types";
import {
  CANON_LEVELS,
  EnumSelect,
  Field,
  ListState,
  SIMULATION_SCOPES,
  Tag,
} from "./shared";

// Axioms tab of /forge/ontology (F2-2 phase 6). Axioms are ontological
// world truths ("magic exists") — the strongest form of canon.

export function AxiomsTab({ universeId }: { universeId: string }) {
  const qc = useQueryClient();
  const [domain, setDomain] = useState("");
  const [canonLevel, setCanonLevel] = useState("");
  const [minMagnitude, setMinMagnitude] = useState(1);
  const [showCreate, setShowCreate] = useState(false);
  const [editing, setEditing] = useState<OntologyAxiom | null>(null);

  const queryFilters = {
    domain: domain || undefined,
    canon_level: canonLevel || undefined,
    min_magnitude: minMagnitude,
    limit: 200,
  };

  const axiomsQ = useQuery({
    queryKey: ["ontology-axioms", universeId, queryFilters],
    queryFn: () => entitiesApi.listAxioms(universeId, queryFilters),
  });
  const axioms = axiomsQ.data?.axioms ?? [];

  const invalidate = () =>
    qc.invalidateQueries({ queryKey: ["ontology-axioms", universeId] });

  const deleteMut = useMutation({
    mutationFn: (id: string) => entitiesApi.deleteAxiom(id, { force: true }),
    onSuccess: invalidate,
  });

  return (
    <div className="flex flex-col h-full overflow-y-auto px-6 py-4 space-y-4">
      {/* Filter row */}
      <div className="flex flex-wrap items-end gap-3">
        <Field label="Domain">
          <input
            aria-label="Filter by domain"
            className="input-cyber py-1 text-xs w-40"
            placeholder="magic, physics, …"
            value={domain}
            onChange={(e) => setDomain(e.target.value)}
          />
        </Field>
        <Field label="Canon level">
          <EnumSelect
            ariaLabel="Filter by canon level"
            value={canonLevel}
            onChange={setCanonLevel}
            options={CANON_LEVELS}
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
            value={minMagnitude}
            onChange={(e) =>
              setMinMagnitude(Math.max(1, Math.min(10, Number(e.target.value) || 1)))
            }
          />
        </Field>
        <div className="flex-1" />
        <button className="btn-cyber text-xs py-1.5" onClick={() => setShowCreate(true)}>
          <Plus className="w-3.5 h-3.5" /> New axiom
        </button>
      </div>

      <ListState
        isLoading={axiomsQ.isLoading}
        isError={axiomsQ.isError}
        error={axiomsQ.error}
        isEmpty={axioms.length === 0}
        emptyMessage="No axioms match the current filters."
      />

      {/* List */}
      <div className="space-y-2">
        {axioms.map((a) => (
          <div
            key={a.id}
            className="glass-dark rounded-lg border border-white/5 px-4 py-3 flex items-start gap-3"
          >
            <div className="flex-1 min-w-0">
              <p className="text-sm text-slate-200 leading-relaxed">{a.statement}</p>
              <div className="flex flex-wrap items-center gap-1.5 mt-1.5">
                <Tag>{a.domain}</Tag>
                <Tag>{a.canon_level}</Tag>
                <Tag>{a.scope}</Tag>
                <span className="text-[10px] text-slate-600">
                  magnitude {a.magnitude} · {Math.round(a.confidence * 100)}% conf
                  {a.source_ref ? ` · ${a.source_ref}` : ""}
                </span>
              </div>
            </div>
            <button
              aria-label={`Edit axiom ${a.statement}`}
              className="p-1.5 text-slate-500 hover:text-cyan-300"
              onClick={() => setEditing(a)}
            >
              <Pencil className="w-3.5 h-3.5" />
            </button>
            <button
              aria-label={`Delete axiom ${a.statement}`}
              className="p-1.5 text-slate-500 hover:text-red-300 disabled:opacity-40"
              disabled={deleteMut.isPending}
              onClick={() => {
                if (window.confirm(`Delete axiom "${a.statement}"? This cannot be undone.`)) {
                  deleteMut.mutate(a.id);
                }
              }}
            >
              <Trash2 className="w-3.5 h-3.5" />
            </button>
          </div>
        ))}
      </div>

      {showCreate && (
        <AxiomFormModal
          universeId={universeId}
          onClose={() => setShowCreate(false)}
          onSaved={() => {
            setShowCreate(false);
            invalidate();
          }}
        />
      )}
      {editing && (
        <AxiomFormModal
          universeId={universeId}
          axiom={editing}
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

function AxiomFormModal({
  universeId,
  axiom,
  onClose,
  onSaved,
}: {
  universeId: string;
  axiom?: OntologyAxiom;
  onClose: () => void;
  onSaved: () => void;
}) {
  const isEdit = !!axiom;
  const [statement, setStatement] = useState(axiom?.statement ?? "");
  const [domain, setDomain] = useState(axiom?.domain ?? "");
  const [magnitude, setMagnitude] = useState<number>(axiom?.magnitude ?? 8);
  const [scope, setScope] = useState<string>(axiom?.scope ?? "global");
  const [canonLevel, setCanonLevel] = useState<string>(axiom?.canon_level ?? "canon");
  const [confidence, setConfidence] = useState<number>(axiom?.confidence ?? 0.9);
  const [sourceRef, setSourceRef] = useState(axiom?.source_ref ?? "");

  const save = useMutation({
    mutationFn: () =>
      isEdit
        ? entitiesApi.updateAxiom(axiom!.id, {
            statement: statement.trim(),
            domain: domain.trim(),
            magnitude,
            scope,
            canon_level: canonLevel,
            confidence,
          })
        : entitiesApi.createAxiom(universeId, {
            statement: statement.trim(),
            domain: domain.trim(),
            magnitude,
            scope,
            canon_level: canonLevel,
            confidence,
            source_ref: sourceRef.trim() || undefined,
          }),
    onSuccess: onSaved,
  });

  return (
    <DialogShell
      title={isEdit ? "Edit axiom" : "New axiom"}
      icon={Landmark}
      onClose={onClose}
      footer={
        <DialogFooter>
          <button className="btn-ghost text-xs" onClick={onClose} disabled={save.isPending}>
            Cancel
          </button>
          <button
            className="btn-cyber text-xs py-1.5 disabled:opacity-40"
            disabled={save.isPending || !statement.trim() || !domain.trim()}
            onClick={() => save.mutate()}
          >
            {save.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : null}
            {isEdit ? "Save changes" : "Create axiom"}
          </button>
        </DialogFooter>
      }
    >
      <div className="p-4 space-y-3">
        <Field label="Statement">
          <textarea
            aria-label="Statement"
            className="input-cyber w-full text-sm resize-none"
            rows={2}
            maxLength={500}
            value={statement}
            onChange={(e) => setStatement(e.target.value)}
            placeholder="e.g. Magic exists and is woven into reality"
          />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Domain">
            <input
              aria-label="Domain"
              className="input-cyber py-1 text-xs w-full"
              placeholder="magic, physics, society…"
              value={domain}
              onChange={(e) => setDomain(e.target.value)}
            />
          </Field>
          <Field label="Canon level">
            <EnumSelect
              ariaLabel="Canon level"
              value={canonLevel}
              onChange={setCanonLevel}
              options={CANON_LEVELS}
            />
          </Field>
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
          {!isEdit && (
            <Field label="Source reference">
              <input
                aria-label="Source reference"
                className="input-cyber py-1 text-xs w-full"
                placeholder="Corebook p. 123 (optional)"
                value={sourceRef}
                onChange={(e) => setSourceRef(e.target.value)}
              />
            </Field>
          )}
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
