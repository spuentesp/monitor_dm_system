"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, Pencil, Plus, Trash2, Zap } from "lucide-react";
import { DialogFooter, DialogShell } from "@/components/DialogShell";
import { entitiesApi } from "@/lib/api";
import type { OntologyEvent } from "@/lib/types";
import {
  CANON_LEVELS,
  EnumSelect,
  Field,
  isoToLocal,
  ListState,
  localToIso,
  SIMULATION_SCOPES,
  Tag,
} from "./shared";

// Events tab of /forge/ontology (F2-2 phase 6). Temporal events with
// start/end times; filters mirror the backend's EventFilter.

export function EventsTab({ universeId }: { universeId: string }) {
  const qc = useQueryClient();
  const [canonLevel, setCanonLevel] = useState("");
  const [minMagnitude, setMinMagnitude] = useState(1);
  const [startAfter, setStartAfter] = useState("");
  const [startBefore, setStartBefore] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [editing, setEditing] = useState<OntologyEvent | null>(null);

  const queryFilters = {
    canon_level: canonLevel || undefined,
    min_magnitude: minMagnitude,
    start_after: localToIso(startAfter) ?? undefined,
    start_before: localToIso(startBefore) ?? undefined,
    limit: 100,
  };

  const eventsQ = useQuery({
    queryKey: ["ontology-events", universeId, queryFilters],
    queryFn: () => entitiesApi.listEvents(universeId, queryFilters),
  });
  const events = eventsQ.data?.events ?? [];

  const invalidate = () =>
    qc.invalidateQueries({ queryKey: ["ontology-events", universeId] });

  const deleteMut = useMutation({
    mutationFn: (id: string) => entitiesApi.deleteEvent(id, { force: true }),
    onSuccess: invalidate,
  });

  return (
    <div className="flex flex-col h-full overflow-y-auto px-6 py-4 space-y-4">
      {/* Filter row */}
      <div className="flex flex-wrap items-end gap-3">
        <Field label="Canon level">
          <EnumSelect
            ariaLabel="Filter by canon level"
            value={canonLevel}
            onChange={setCanonLevel}
            options={CANON_LEVELS}
            allowAll
          />
        </Field>
        <Field label="Starts after">
          <input
            aria-label="Filter by start after"
            type="datetime-local"
            className="input-cyber py-1 text-xs"
            value={startAfter}
            onChange={(e) => setStartAfter(e.target.value)}
          />
        </Field>
        <Field label="Starts before">
          <input
            aria-label="Filter by start before"
            type="datetime-local"
            className="input-cyber py-1 text-xs"
            value={startBefore}
            onChange={(e) => setStartBefore(e.target.value)}
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
          <Plus className="w-3.5 h-3.5" /> New event
        </button>
      </div>

      <ListState
        isLoading={eventsQ.isLoading}
        isError={eventsQ.isError}
        error={eventsQ.error}
        isEmpty={events.length === 0}
        emptyMessage="No events match the current filters."
      />

      {/* List */}
      <div className="space-y-2">
        {events.map((ev) => (
          <div
            key={ev.id}
            className="glass-dark rounded-lg border border-white/5 px-4 py-3 flex items-start gap-3"
          >
            <div className="flex-1 min-w-0">
              <p className="text-sm text-slate-200 leading-relaxed">{ev.title}</p>
              {ev.description && (
                <p className="text-xs text-slate-500 mt-0.5 line-clamp-2">{ev.description}</p>
              )}
              <div className="flex flex-wrap items-center gap-1.5 mt-1.5">
                <Tag>{ev.canon_level}</Tag>
                <Tag>{ev.scope}</Tag>
                <span className="text-[10px] text-slate-600">
                  {new Date(ev.start_time).toLocaleString()}
                  {ev.end_time ? ` → ${new Date(ev.end_time).toLocaleString()}` : ""} · magnitude{" "}
                  {ev.magnitude}
                </span>
              </div>
            </div>
            <button
              aria-label={`Edit event ${ev.title}`}
              className="p-1.5 text-slate-500 hover:text-cyan-300"
              onClick={() => setEditing(ev)}
            >
              <Pencil className="w-3.5 h-3.5" />
            </button>
            <button
              aria-label={`Delete event ${ev.title}`}
              className="p-1.5 text-slate-500 hover:text-red-300 disabled:opacity-40"
              disabled={deleteMut.isPending}
              onClick={() => {
                if (window.confirm(`Delete event "${ev.title}"? This cannot be undone.`)) {
                  deleteMut.mutate(ev.id);
                }
              }}
            >
              <Trash2 className="w-3.5 h-3.5" />
            </button>
          </div>
        ))}
      </div>

      {showCreate && (
        <EventFormModal
          universeId={universeId}
          onClose={() => setShowCreate(false)}
          onSaved={() => {
            setShowCreate(false);
            invalidate();
          }}
        />
      )}
      {editing && (
        <EventFormModal
          universeId={universeId}
          event={editing}
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

function EventFormModal({
  universeId,
  event,
  onClose,
  onSaved,
}: {
  universeId: string;
  event?: OntologyEvent;
  onClose: () => void;
  onSaved: () => void;
}) {
  const isEdit = !!event;
  const [title, setTitle] = useState(event?.title ?? "");
  const [description, setDescription] = useState(event?.description ?? "");
  const [startTime, setStartTime] = useState(isoToLocal(event?.start_time));
  const [endTime, setEndTime] = useState(isoToLocal(event?.end_time));
  const [magnitude, setMagnitude] = useState<number>(event?.magnitude ?? 5);
  const [scope, setScope] = useState<string>(event?.scope ?? "local");
  const [canonLevel, setCanonLevel] = useState<string>(event?.canon_level ?? "canon");

  const startIso = localToIso(startTime);

  const save = useMutation({
    mutationFn: () =>
      isEdit
        ? entitiesApi.updateEvent(event!.id, {
            title: title.trim(),
            description: description.trim() || null,
            start_time: startIso!,
            end_time: localToIso(endTime),
            magnitude,
            scope,
            canon_level: canonLevel,
          })
        : entitiesApi.createEvent(universeId, {
            title: title.trim(),
            description: description.trim() || undefined,
            start_time: startIso!,
            end_time: localToIso(endTime),
            magnitude,
            scope,
            canon_level: canonLevel,
          }),
    onSuccess: onSaved,
  });

  return (
    <DialogShell
      title={isEdit ? "Edit event" : "New event"}
      icon={Zap}
      onClose={onClose}
      footer={
        <DialogFooter>
          <button className="btn-ghost text-xs" onClick={onClose} disabled={save.isPending}>
            Cancel
          </button>
          <button
            className="btn-cyber text-xs py-1.5 disabled:opacity-40"
            disabled={save.isPending || !title.trim() || !startIso}
            onClick={() => save.mutate()}
          >
            {save.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : null}
            {isEdit ? "Save changes" : "Create event"}
          </button>
        </DialogFooter>
      }
    >
      <div className="p-4 space-y-3">
        <Field label="Title">
          <input
            aria-label="Title"
            className="input-cyber w-full text-sm py-1.5"
            maxLength={200}
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="e.g. The fall of House Dray"
          />
        </Field>
        <Field label="Description">
          <textarea
            aria-label="Description"
            className="input-cyber w-full text-sm resize-none"
            rows={2}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Start time">
            <input
              aria-label="Start time"
              type="datetime-local"
              className="input-cyber py-1 text-xs w-full"
              value={startTime}
              onChange={(e) => setStartTime(e.target.value)}
            />
          </Field>
          <Field label="End time">
            <input
              aria-label="End time"
              type="datetime-local"
              className="input-cyber py-1 text-xs w-full"
              value={endTime}
              onChange={(e) => setEndTime(e.target.value)}
            />
          </Field>
          <Field label="Magnitude">
            <input
              aria-label="Magnitude"
              type="number"
              min={0}
              max={10}
              className="input-cyber py-1 text-xs w-full"
              value={magnitude}
              onChange={(e) => setMagnitude(Number(e.target.value) || 0)}
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
          <Field label="Canon level">
            <EnumSelect
              ariaLabel="Canon level"
              value={canonLevel}
              onChange={setCanonLevel}
              options={CANON_LEVELS}
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
