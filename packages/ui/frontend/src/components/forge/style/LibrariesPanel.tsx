"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toneApi } from "@/lib/api";
import type { ToneLibrary, ToneProfile } from "@/lib/types";

/**
 * Tone Libraries tab (F3-4.2). Full CRUD over ToneLibraries: create, inline
 * edit, delete, set-default. The profile picker is wired to the same profiles
 * list the Profiles tab uses.
 */

const inputCls =
  "bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-slate-200";

interface LibraryFormState {
  name: string;
  description: string;
  priority: string; // kept as string so an empty input doesn't snap back to the default
  isDefault: boolean;
  profileIds: string[];
}

const EMPTY_FORM: LibraryFormState = {
  name: "",
  description: "",
  priority: "100",
  isDefault: false,
  profileIds: [],
};

function parsePriority(raw: string): number {
  const n = parseInt(raw, 10);
  if (Number.isNaN(n)) return 100;
  return Math.min(1000, Math.max(0, n));
}

function ProfilePicker({
  profiles,
  selected,
  onToggle,
  idPrefix,
}: {
  profiles: ToneProfile[];
  selected: string[];
  onToggle: (profileId: string) => void;
  idPrefix: string;
}) {
  if (profiles.length === 0) {
    return <p className="text-xs text-slate-500">No tone profiles available yet.</p>;
  }
  return (
    <div className="flex flex-wrap gap-2">
      {profiles.map((p) => {
        const checked = selected.includes(p.profile_id);
        return (
          <label
            key={p.profile_id}
            className={`flex items-center gap-1.5 text-xs px-2 py-1 rounded border cursor-pointer ${
              checked
                ? "border-cyan-500/50 bg-cyan-500/10 text-cyan-300"
                : "border-zinc-700 bg-zinc-900 text-slate-400 hover:text-slate-200"
            }`}
          >
            <input
              type="checkbox"
              id={`${idPrefix}-${p.profile_id}`}
              checked={checked}
              onChange={() => onToggle(p.profile_id)}
              className="sr-only"
            />
            {p.name}
          </label>
        );
      })}
    </div>
  );
}

function LibraryForm({
  state,
  setState,
  profiles,
  onSubmit,
  onCancel,
  submitLabel,
  isPending,
  idPrefix,
}: {
  state: LibraryFormState;
  setState: (s: LibraryFormState) => void;
  profiles: ToneProfile[];
  onSubmit: () => void;
  onCancel?: () => void;
  submitLabel: string;
  isPending: boolean;
  idPrefix: string;
}) {
  const toggle = (profileId: string) =>
    setState({
      ...state,
      profileIds: state.profileIds.includes(profileId)
        ? state.profileIds.filter((id) => id !== profileId)
        : [...state.profileIds, profileId],
    });

  return (
    <div className="space-y-2 bg-zinc-900/40 border border-zinc-800 rounded-lg p-4">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-2 items-end">
        <input
          aria-label={idPrefix === "create" ? "Library name" : "Edit library name"}
          value={state.name}
          onChange={(e) => setState({ ...state, name: e.target.value })}
          placeholder="Library name"
          className={inputCls}
        />
        <input
          aria-label={idPrefix === "create" ? "Library description" : "Edit library description"}
          value={state.description}
          onChange={(e) => setState({ ...state, description: e.target.value })}
          placeholder="Description"
          className={inputCls}
        />
        <div className="flex items-center gap-3">
          <input
            aria-label={idPrefix === "create" ? "Library priority" : "Edit library priority"}
            type="number"
            min={0}
            max={1000}
            value={state.priority}
            onChange={(e) => setState({ ...state, priority: e.target.value })}
            className={`w-24 ${inputCls}`}
          />
          <label className="flex items-center gap-1.5 text-xs text-slate-400">
            <input
              type="checkbox"
              aria-label={idPrefix === "create" ? "Default library" : "Edit default library"}
              checked={state.isDefault}
              onChange={(e) => setState({ ...state, isDefault: e.target.checked })}
            />
            default
          </label>
        </div>
      </div>
      <ProfilePicker
        profiles={profiles}
        selected={state.profileIds}
        onToggle={toggle}
        idPrefix={idPrefix}
      />
      <div className="flex gap-2">
        <button
          onClick={onSubmit}
          disabled={!state.name.trim() || isPending}
          className="px-3 py-2 rounded-lg bg-purple-600 hover:bg-purple-500 disabled:opacity-40 text-sm text-white"
        >
          {submitLabel}
        </button>
        {onCancel && (
          <button
            onClick={onCancel}
            className="px-3 py-2 rounded-lg text-sm text-slate-400 hover:text-slate-200"
          >
            Cancel
          </button>
        )}
      </div>
    </div>
  );
}

export function LibrariesPanel() {
  const qc = useQueryClient();
  const profilesQ = useQuery({
    queryKey: ["tone", "profiles"],
    queryFn: () => toneApi.listProfiles(),
  });
  const librariesQ = useQuery({
    queryKey: ["tone", "libraries"],
    queryFn: () => toneApi.listLibraries(),
  });

  const [isCreating, setIsCreating] = useState(false);
  const [createState, setCreateState] = useState<LibraryFormState>(EMPTY_FORM);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editState, setEditState] = useState<LibraryFormState>(EMPTY_FORM);

  const invalidate = () => qc.invalidateQueries({ queryKey: ["tone", "libraries"] });

  const createM = useMutation({
    mutationFn: () =>
      toneApi.createLibrary({
        name: createState.name.trim(),
        description: createState.description.trim(),
        priority: parsePriority(createState.priority),
        is_default: createState.isDefault,
        tone_profile_ids: createState.profileIds,
      }),
    onSuccess: () => {
      invalidate();
      setCreateState(EMPTY_FORM);
      setIsCreating(false);
    },
  });

  const updateM = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Parameters<typeof toneApi.updateLibrary>[1] }) =>
      toneApi.updateLibrary(id, body),
    onSuccess: () => {
      invalidate();
      setEditingId(null);
    },
  });

  const deleteM = useMutation({
    mutationFn: (id: string) => toneApi.deleteLibrary(id),
    onSuccess: invalidate,
  });

  const startEdit = (l: ToneLibrary) => {
    setEditingId(l.library_id);
    setEditState({
      name: l.name,
      description: l.description,
      priority: String(l.priority),
      isDefault: l.is_default,
      profileIds: [...l.tone_profile_ids],
    });
  };

  const profiles = profilesQ.data?.profiles ?? [];
  const libraries = librariesQ.data?.libraries ?? [];

  return (
    <div className="space-y-6 max-w-4xl">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-bold text-slate-100">Tone Libraries</h2>
          <p className="text-sm text-slate-500 mt-1">
            Bundles of tone profiles. The default library is the fallback when no
            specific library is set.
          </p>
        </div>
        {!isCreating && (
          <button
            onClick={() => setIsCreating(true)}
            className="px-3 py-2 rounded-lg bg-purple-600 hover:bg-purple-500 text-sm text-white flex-shrink-0"
          >
            New library
          </button>
        )}
      </div>

      {isCreating && (
        <LibraryForm
          state={createState}
          setState={setCreateState}
          profiles={profiles}
          onSubmit={() => createM.mutate()}
          onCancel={() => {
            setIsCreating(false);
            setCreateState(EMPTY_FORM);
          }}
          submitLabel="Create library"
          isPending={createM.isPending}
          idPrefix="create"
        />
      )}

      <div className="space-y-2">
        {librariesQ.isLoading && <p className="text-sm text-slate-500">Loading…</p>}
        {!librariesQ.isLoading && libraries.length === 0 && (
          <p className="text-sm text-slate-500">No tone libraries yet.</p>
        )}
        {libraries.map((l) =>
          editingId === l.library_id ? (
            <LibraryForm
              key={l.library_id}
              state={editState}
              setState={setEditState}
              profiles={profiles}
              onSubmit={() =>
                updateM.mutate({
                  id: l.library_id,
                  body: {
                    name: editState.name.trim(),
                    description: editState.description.trim(),
                    priority: parsePriority(editState.priority),
                    is_default: editState.isDefault,
                    tone_profile_ids: editState.profileIds,
                  },
                })
              }
              onCancel={() => setEditingId(null)}
              submitLabel="Save"
              isPending={updateM.isPending}
              idPrefix="edit"
            />
          ) : (
            <div
              key={l.library_id}
              className="flex items-start justify-between gap-4 bg-zinc-900/60 border border-zinc-800 rounded-lg px-4 py-3"
            >
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-slate-100">{l.name}</span>
                  {l.is_default && (
                    <span className="text-[10px] uppercase px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-300 border border-emerald-500/30">
                      default
                    </span>
                  )}
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-white/5 text-slate-500">
                    priority {l.priority}
                  </span>
                </div>
                {l.description && (
                  <p className="text-xs text-slate-400 mt-1">{l.description}</p>
                )}
                <p className="text-xs text-slate-500 mt-1">
                  {l.tone_profile_ids.length} profiles
                </p>
              </div>
              <div className="flex items-center gap-3 flex-shrink-0">
                {!l.is_default && (
                  <button
                    onClick={() =>
                      updateM.mutate({ id: l.library_id, body: { is_default: true } })
                    }
                    className="text-xs text-emerald-400 hover:text-emerald-300"
                  >
                    Set default
                  </button>
                )}
                <button
                  onClick={() => startEdit(l)}
                  className="text-xs text-slate-400 hover:text-slate-200"
                >
                  Edit
                </button>
                {!l.is_default && (
                  <button
                    onClick={() => deleteM.mutate(l.library_id)}
                    className="text-xs text-red-400 hover:text-red-300"
                  >
                    Delete
                  </button>
                )}
              </div>
            </div>
          ),
        )}
      </div>
    </div>
  );
}
