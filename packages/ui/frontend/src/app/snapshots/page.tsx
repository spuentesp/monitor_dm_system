"use client";

import { useState, useMemo } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Camera,
  GitCompareArrows,
  GitFork,
  Loader2,
  Plus,
  RefreshCw,
  RotateCcw,
  Trash2,
  WifiOff,
  X,
  Layers,
} from "lucide-react";
import { universesApi } from "@/lib/api";
import type { Multiverse, Universe, WorldSnapshot, SnapshotComparison } from "@/lib/types";
import { cn, formatRelativeTime } from "@/lib/utils";
import { DialogShell, DialogFooter } from "@/components/DialogShell";

// ─── Component ────────────────────────────────────────────────

export default function SnapshotsPage() {
  const qc = useQueryClient();

  // ─── Data loading ──────────────────────────────────────────

  const multiversesQ = useQuery({
    queryKey: ["multiverses"],
    queryFn: () => universesApi.listMultiverses(),
  });

  const [selectedMvId, setSelectedMvId] = useState<string | null>(null);
  const [selectedUniverseId, setSelectedUniverseId] = useState<string | null>(null);

  const universesQ = useQuery({
    queryKey: ["universes", selectedMvId],
    queryFn: () => universesApi.listUniverses(selectedMvId ?? undefined),
    enabled: !!selectedMvId,
  });

  // Auto-select first multiverse + universe on first load.
  if (
    !selectedMvId &&
    multiversesQ.data &&
    multiversesQ.data.length > 0 &&
    !multiversesQ.isLoading
  ) {
    setSelectedMvId(multiversesQ.data[0].id);
  }
  if (
    selectedMvId &&
    !selectedUniverseId &&
    universesQ.data &&
    universesQ.data.length > 0 &&
    !universesQ.isLoading
  ) {
    setSelectedUniverseId(universesQ.data[0].id);
  }

  const snapshotsQ = useQuery({
    queryKey: ["snapshots", selectedUniverseId],
    queryFn: () => universesApi.listSnapshots(selectedUniverseId!),
    enabled: !!selectedUniverseId,
  });

  // ─── Selection for compare ─────────────────────────────────

  const [selectedForCompare, setSelectedForCompare] = useState<Set<string>>(new Set());

  // ─── Dialog state ──────────────────────────────────────────

  const [createOpen, setCreateOpen] = useState(false);
  const [restoreTarget, setRestoreTarget] = useState<WorldSnapshot | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<WorldSnapshot | null>(null);
  const [compareResult, setCompareResult] = useState<SnapshotComparison | null>(null);

  // ─── Mutations ─────────────────────────────────────────────

  const forkMut = useMutation({
    mutationFn: (name: string) =>
      universesApi.forkUniverse(selectedUniverseId!, { name }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["universes"] });
    },
  });

  const createMut = useMutation({
    mutationFn: (data: { name: string; description?: string }) =>
      universesApi.createSnapshot(selectedUniverseId!, data),
    onSuccess: () => {
      setCreateOpen(false);
      qc.invalidateQueries({ queryKey: ["snapshots", selectedUniverseId] });
    },
  });

  const restoreMut = useMutation({
    mutationFn: (sid: string) => universesApi.restoreSnapshot(selectedUniverseId!, sid),
    onSuccess: () => {
      setRestoreTarget(null);
      qc.invalidateQueries({ queryKey: ["snapshots", selectedUniverseId] });
    },
  });

  const deleteMut = useMutation({
    mutationFn: (sid: string) => universesApi.deleteSnapshot(selectedUniverseId!, sid),
    onSuccess: () => {
      setDeleteTarget(null);
      setSelectedForCompare((prev) => {
        const next = new Set(prev);
        if (deleteTarget) next.delete(deleteTarget.snapshot_id);
        return next;
      });
      qc.invalidateQueries({ queryKey: ["snapshots", selectedUniverseId] });
    },
  });

  const compareMut = useMutation({
    mutationFn: (ids: [string, string]) =>
      universesApi.compareSnapshots(selectedUniverseId!, ids[0], ids[1]),
    onSuccess: (data) => setCompareResult(data),
  });

  // ─── Derived ───────────────────────────────────────────────

  const snapshots = snapshotsQ.data ?? [];
  const canCompare = selectedForCompare.size === 2;
  const orderedPairs = useMemo(() => Array.from(selectedForCompare), [selectedForCompare]);

  // ─── Render ────────────────────────────────────────────────

  return (
    <div className="min-h-screen p-6 lg:p-8 max-w-7xl mx-auto">
      {/* Header */}
      <header className="mb-6">
        <div className="flex items-center gap-3 mb-2">
          <Camera className="h-6 w-6 text-accent-primary" />
          <h1 className="text-2xl font-bold text-fg-primary">World Snapshots</h1>
        </div>
        <p className="text-sm text-fg-muted max-w-2xl">
          Capture point-in-time snapshots of a universe, compare them to see what changed,
          and restore earlier states if a session went off the rails.
        </p>
      </header>

      {/* Universe picker */}
      <div className="card-glass p-4 mb-6 flex flex-wrap items-end gap-4">
        <div>
          <label className="block text-xs text-fg-muted mb-1">Multiverse</label>
          <select
            className="select w-56"
            value={selectedMvId ?? ""}
            onChange={(e) => {
              setSelectedMvId(e.target.value || null);
              setSelectedUniverseId(null);
            }}
          >
            <option value="">— select —</option>
            {(multiversesQ.data ?? []).map((mv: Multiverse) => (
              <option key={mv.id} value={mv.id}>
                {mv.name}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="block text-xs text-fg-muted mb-1">Universe</label>
          <select
            className="select w-72"
            value={selectedUniverseId ?? ""}
            onChange={(e) => {
              setSelectedUniverseId(e.target.value || null);
              setSelectedForCompare(new Set());
            }}
            disabled={!selectedMvId || universesQ.isLoading}
          >
            <option value="">— select —</option>
            {(universesQ.data ?? []).map((u: Universe) => (
              <option key={u.id} value={u.id}>
                {u.name}
              </option>
            ))}
          </select>
        </div>

        <button
          className="btn-primary ml-auto"
          onClick={() => setCreateOpen(true)}
          disabled={!selectedUniverseId}
        >
          <Plus className="h-4 w-4" /> New Snapshot
        </button>

        <button
          className="btn-secondary"
          onClick={() => {
            const name = window.prompt(
              "Name for the forked universe (a deep copy of all canon):",
            );
            if (name?.trim()) forkMut.mutate(name.trim());
          }}
          disabled={!selectedUniverseId || forkMut.isPending}
          title="Fork this universe into an independent copy (M-35)"
        >
          <GitFork className={cn("h-4 w-4", forkMut.isPending && "animate-pulse")} />
          Fork
        </button>

        <button
          className="btn-secondary"
          onClick={() => snapshotsQ.refetch()}
          disabled={!selectedUniverseId || snapshotsQ.isFetching}
          title="Refresh"
        >
          <RefreshCw className={cn("h-4 w-4", snapshotsQ.isFetching && "animate-spin")} />
        </button>
      </div>

      {/* Connection-error banner */}
      {snapshotsQ.isError && (
        <div className="card-glass border-red-500/30 bg-red-500/5 p-4 mb-6 flex items-center gap-3">
          <WifiOff className="h-5 w-5 text-red-400" />
          <div className="text-sm text-red-300">
            Could not reach the backend. Check the API is running and try again.
          </div>
        </div>
      )}

      {/* Compare action bar (only visible when 2 selected) */}
      {canCompare && (
        <div className="card-glass border-accent-primary/30 p-3 mb-4 flex items-center gap-3">
          <GitCompareArrows className="h-4 w-4 text-accent-primary" />
          <span className="text-sm">2 snapshots selected</span>
          <button
            className="btn-primary ml-auto"
            onClick={() =>
              compareMut.mutate([orderedPairs[0], orderedPairs[1]] as [string, string])
            }
            disabled={compareMut.isPending}
          >
            {compareMut.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <GitCompareArrows className="h-4 w-4" />
            )}
            Compare
          </button>
          <button
            className="btn-ghost"
            onClick={() => setSelectedForCompare(new Set())}
            title="Clear selection"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      )}

      {/* Snapshot list */}
      {!selectedUniverseId ? (
        <EmptyState
          icon={Layers}
          title="Pick a universe"
          message="Select a multiverse and universe above to view its snapshots."
        />
      ) : snapshotsQ.isLoading ? (
        <div className="flex items-center justify-center py-16 text-fg-muted">
          <Loader2 className="h-6 w-6 animate-spin mr-2" /> Loading snapshots…
        </div>
      ) : snapshots.length === 0 ? (
        <EmptyState
          icon={Camera}
          title="No snapshots yet"
          message="Click 'New Snapshot' to capture the current state of this universe."
        />
      ) : (
        <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {snapshots.map((s) => (
            <SnapshotCard
              key={s.snapshot_id}
              snapshot={s}
              selectedForCompare={selectedForCompare.has(s.snapshot_id)}
              onToggleCompare={() =>
                setSelectedForCompare((prev) => {
                  const next = new Set(prev);
                  if (next.has(s.snapshot_id)) next.delete(s.snapshot_id);
                  else if (next.size < 2) next.add(s.snapshot_id);
                  return next;
                })
              }
              onRestore={() => setRestoreTarget(s)}
              onDelete={() => setDeleteTarget(s)}
            />
          ))}
        </ul>
      )}

      {/* ── Dialogs ──────────────────────────────────────────── */}

      {createOpen && (
        <CreateDialog
          onClose={() => setCreateOpen(false)}
          onSubmit={(data) => createMut.mutate(data)}
          isPending={createMut.isPending}
          error={createMut.error as Error | null}
        />
      )}

      {restoreTarget && (
        <ConfirmDialog
          title="Restore this snapshot?"
          icon={RotateCcw}
          iconClassName="text-amber-400"
          message={
            <span>
              This will replace the current state of the universe with the contents of{" "}
              <span className="font-semibold">"{restoreTarget.name}"</span> created{" "}
              {formatRelativeTime(restoreTarget.created_at)}. This action cannot be undone.
            </span>
          }
          confirmLabel="Restore"
          onClose={() => setRestoreTarget(null)}
          onConfirm={() => restoreMut.mutate(restoreTarget.snapshot_id)}
          isPending={restoreMut.isPending}
          error={restoreMut.error as Error | null}
        />
      )}

      {deleteTarget && (
        <ConfirmDialog
          title="Delete this snapshot?"
          icon={Trash2}
          iconClassName="text-red-400"
          message={
            <span>
              Permanently delete snapshot{" "}
              <span className="font-semibold">"{deleteTarget.name}"</span>? You can&apos;t undo
              this.
            </span>
          }
          confirmLabel="Delete"
          confirmClassName="btn-danger"
          onClose={() => setDeleteTarget(null)}
          onConfirm={() => deleteMut.mutate(deleteTarget.snapshot_id)}
          isPending={deleteMut.isPending}
          error={deleteMut.error as Error | null}
        />
      )}

      {compareResult && (
        <CompareDialog
          comparison={compareResult}
          snapshots={snapshots}
          onClose={() => setCompareResult(null)}
        />
      )}
    </div>
  );
}

// ─── Sub-components ───────────────────────────────────────────

function SnapshotCard({
  snapshot,
  selectedForCompare,
  onToggleCompare,
  onRestore,
  onDelete,
}: {
  snapshot: WorldSnapshot;
  selectedForCompare: boolean;
  onToggleCompare: () => void;
  onRestore: () => void;
  onDelete: () => void;
}) {
  return (
    <li
      className={cn(
        "card-glass p-4 transition-colors",
        selectedForCompare && "border-accent-primary/60 bg-accent-primary/5",
      )}
    >
      <div className="flex items-start gap-2 mb-2">
        <Camera className="h-4 w-4 text-accent-primary mt-0.5 flex-shrink-0" />
        <div className="min-w-0 flex-1">
          <h3 className="text-sm font-semibold text-fg-primary truncate">{snapshot.name}</h3>
          {snapshot.description && (
            <p className="text-xs text-fg-muted mt-0.5 line-clamp-2">{snapshot.description}</p>
          )}
        </div>
      </div>

      <dl className="grid grid-cols-3 gap-1 text-[10px] text-fg-muted mb-3">
        <Stat label="entities" value={snapshot.entity_count} />
        <Stat label="facts" value={snapshot.fact_count} />
        <Stat label="rels" value={snapshot.relationship_count} />
      </dl>

      <p className="text-[11px] text-fg-dim mb-3">
        Created {formatRelativeTime(snapshot.created_at)}
      </p>

      <div className="flex flex-wrap gap-1.5">
        <button
          className={cn(
            "btn-ghost flex-1 text-xs",
            selectedForCompare && "bg-accent-primary/20 text-accent-primary",
          )}
          onClick={onToggleCompare}
          title="Select to compare"
        >
          <GitCompareArrows className="h-3 w-3" />
          {selectedForCompare ? "Selected" : "Compare"}
        </button>
        <button
          className="btn-ghost flex-1 text-xs"
          onClick={onRestore}
          title="Restore this snapshot"
        >
          <RotateCcw className="h-3 w-3" /> Restore
        </button>
        <button
          className="btn-ghost text-red-400 hover:text-red-300"
          onClick={onDelete}
          title="Delete snapshot"
        >
          <Trash2 className="h-3 w-3" />
        </button>
      </div>
    </li>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <dt className="uppercase tracking-wide">{label}</dt>
      <dd className="text-sm font-semibold text-fg-primary">{value.toLocaleString()}</dd>
    </div>
  );
}

function EmptyState({
  icon: Icon,
  title,
  message,
}: {
  icon: React.ElementType;
  title: string;
  message: string;
}) {
  return (
    <div className="card-glass p-12 text-center">
      <Icon className="h-10 w-10 text-fg-dim mx-auto mb-3" />
      <h3 className="text-sm font-semibold text-fg-primary mb-1">{title}</h3>
      <p className="text-xs text-fg-muted max-w-sm mx-auto">{message}</p>
    </div>
  );
}

function CreateDialog({
  onClose,
  onSubmit,
  isPending,
  error,
}: {
  onClose: () => void;
  onSubmit: (data: { name: string; description?: string }) => void;
  isPending: boolean;
  error: Error | null;
}) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");

  const canSubmit = name.trim().length > 0 && !isPending;

  return (
    <DialogShell title="Create snapshot" icon={Camera} onClose={onClose}>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (canSubmit) onSubmit({ name: name.trim(), description: description.trim() || undefined });
        }}
        className="p-4 space-y-3"
      >
        <div>
          <label className="block text-xs text-fg-muted mb-1">Name</label>
          <input
            autoFocus
            className="input w-full"
            placeholder="e.g. Before the goblin ambush"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
          />
        </div>
        <div>
          <label className="block text-xs text-fg-muted mb-1">
            Description <span className="text-fg-dim">(optional)</span>
          </label>
          <textarea
            className="input w-full min-h-[60px]"
            placeholder="Why are you saving this state?"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </div>
        {error && <p className="text-xs text-red-400">{error.message}</p>}
        <DialogFooter>
          <button type="button" className="btn-ghost" onClick={onClose} disabled={isPending}>
            Cancel
          </button>
          <button type="submit" className="btn-primary" disabled={!canSubmit}>
            {isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Camera className="h-4 w-4" />}
            Create
          </button>
        </DialogFooter>
      </form>
    </DialogShell>
  );
}

function ConfirmDialog({
  title,
  icon,
  iconClassName,
  message,
  confirmLabel,
  confirmClassName = "btn-primary",
  onClose,
  onConfirm,
  isPending,
  error,
}: {
  title: string;
  icon: React.ElementType;
  iconClassName?: string;
  message: React.ReactNode;
  confirmLabel: string;
  confirmClassName?: string;
  onClose: () => void;
  onConfirm: () => void;
  isPending: boolean;
  error: Error | null;
}) {
  return (
    <DialogShell title={title} icon={icon} iconClassName={iconClassName} onClose={onClose}>
      <div className="p-4 space-y-3">
        <p className="text-sm text-fg-muted">{message}</p>
        {error && <p className="text-xs text-red-400">{error.message}</p>}
        <DialogFooter>
          <button className="btn-ghost" onClick={onClose} disabled={isPending}>
            Cancel
          </button>
          <button className={confirmClassName} onClick={onConfirm} aria-label="Confirm" disabled={isPending}>
            {isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
            {confirmLabel}
          </button>
        </DialogFooter>
      </div>
    </DialogShell>
  );
}

function CompareDialog({
  comparison,
  snapshots,
  onClose,
}: {
  comparison: SnapshotComparison;
  snapshots: WorldSnapshot[];
  onClose: () => void;
}) {
  const nameOf = (id: string) => snapshots.find((s) => s.snapshot_id === id)?.name ?? id.slice(0, 8);

  return (
    <DialogShell
      title="Snapshot comparison"
      icon={GitCompareArrows}
      onClose={onClose}
      maxWidthClassName="max-w-2xl"
    >
      <div className="p-4 space-y-4 max-h-[70vh] overflow-y-auto">
        <div className="text-xs text-fg-muted">
          Comparing <span className="font-semibold text-fg-primary">{nameOf(comparison.snapshot_a)}</span>{" "}
          → <span className="font-semibold text-fg-primary">{nameOf(comparison.snapshot_b)}</span>
        </div>

        <div className="grid grid-cols-3 gap-2 text-center">
          <DiffStat label="Entities" added={comparison.entities_added} removed={comparison.entities_removed} modified={comparison.entities_modified} />
          <DiffStat label="Facts" added={comparison.facts_added} removed={comparison.facts_removed} modified={comparison.facts_modified} />
          <div className="card-glass p-3 text-xs text-fg-muted">
            {comparison.diff.length} detailed change{comparison.diff.length === 1 ? "" : "s"}
          </div>
        </div>

        {comparison.diff.length > 0 && (
          <ul className="space-y-1 text-xs">
            {comparison.diff.slice(0, 50).map((d, i) => (
              <li
                key={i}
                className={cn(
                  "px-2 py-1 rounded border",
                  d.type === "added" && "border-emerald-500/30 bg-emerald-500/5 text-emerald-200",
                  d.type === "removed" && "border-red-500/30 bg-red-500/5 text-red-200",
                  d.type === "modified" && "border-amber-500/30 bg-amber-500/5 text-amber-200",
                )}
              >
                <span className="font-mono mr-2">{d.type}</span>
                {d.entity_id}
                {d.field && <span className="text-fg-muted"> · {d.field}</span>}
              </li>
            ))}
            {comparison.diff.length > 50 && (
              <li className="text-fg-muted text-center pt-2">
                … and {comparison.diff.length - 50} more
              </li>
            )}
          </ul>
        )}

        <DialogFooter>
          <button className="btn-primary" onClick={onClose}>
            Close
          </button>
        </DialogFooter>
      </div>
    </DialogShell>
  );
}

function DiffStat({
  label,
  added,
  removed,
  modified,
}: {
  label: string;
  added: number;
  removed: number;
  modified: number;
}) {
  return (
    <div className="card-glass p-3 text-xs">
      <div className="text-fg-muted mb-1">{label}</div>
      <div className="flex justify-around font-mono">
        <span className="text-emerald-400">+{added}</span>
        <span className="text-red-400">−{removed}</span>
        <span className="text-amber-400">~{modified}</span>
      </div>
    </div>
  );
}
