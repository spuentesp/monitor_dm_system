"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import {
  Users,
  Plus,
  Upload,
  MessageCircle,
  Sparkles,
  Trash2,
  Save,
  Download,
  Brain,
  Loader2,
} from "lucide-react";
import { entitiesApi } from "@/lib/api";
import type { StandaloneCharacter } from "@/lib/types";
import { ENTITY_KEYS } from "@/lib/query-keys";
import { DialogShell, DialogFooter } from "@/components/DialogShell";
import { useNotify } from "@/components/NotificationProvider";
import { CharacterChat } from "@/components/characters/CharacterChat";
import { cn } from "@/lib/utils";
import { errorMessage } from "@/lib/errors";

export default function CharactersPage() {
  const qc = useQueryClient();
  const { notify } = useNotify();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [chatting, setChatting] = useState(false);
  const [creating, setCreating] = useState(false);

  const { data: characters = [], isLoading } = useQuery({
    queryKey: ENTITY_KEYS.standaloneCharacters(),
    queryFn: () => entitiesApi.listStandaloneCharacters({ limit: 100 }),
  });

  const selected = characters.find((c) => c.id === selectedId) ?? null;

  const importCard = useMutation({
    mutationFn: (file: File) => entitiesApi.importCharacterCard(file),
    onSuccess: (ch) => {
      qc.invalidateQueries({ queryKey: ENTITY_KEYS.standaloneCharacters() });
      setSelectedId(ch.id);
      notify("success", `Imported ${ch.name}`);
    },
    onError: (e: unknown) => notify("error", `Import failed: ${errorMessage(e)}`),
  });

  if (chatting && selected) {
    return (
      <div className="h-full">
        <CharacterChat character={selected} onBack={() => setChatting(false)} />
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0">
      {/* Roster */}
      <div className="flex flex-1 flex-col min-h-0">
        <header className="flex items-center gap-3 border-b border-border p-4">
          <Users className="h-5 w-5 text-accent-primary" />
          <div className="mr-auto">
            <h1 className="text-sm font-semibold text-fg-primary">Characters</h1>
            <p className="text-xs text-fg-muted">Roster & conversatory — chat with MONITOR-backed characters</p>
          </div>
          <label className="btn-ghost cursor-pointer gap-1.5">
            <Upload className="h-4 w-4" />
            <span className="text-xs">Import card</span>
            <input
              type="file"
              accept=".json,.png"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) importCard.mutate(f);
                e.target.value = "";
              }}
            />
          </label>
          <button className="btn-cyber gap-1.5" onClick={() => setCreating(true)}>
            <Plus className="h-4 w-4" />
            <span className="text-xs">New character</span>
          </button>
        </header>

        <div className="flex-1 overflow-y-auto p-4">
          {isLoading ? (
            <div className="flex items-center justify-center gap-2 py-16 text-fg-muted">
              <Loader2 className="h-4 w-4 animate-spin" /> Loading roster…
            </div>
          ) : characters.length === 0 ? (
            <EmptyState onCreate={() => setCreating(true)} />
          ) : (
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {characters.map((c) => (
                <RosterCard
                  key={c.id}
                  character={c}
                  active={c.id === selectedId}
                  onSelect={() => setSelectedId(c.id)}
                  onChat={() => {
                    setSelectedId(c.id);
                    setChatting(true);
                  }}
                />
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Detail */}
      {selected && (
        <CharacterDetail
          key={selected.id}
          character={selected}
          onChat={() => setChatting(true)}
          onClose={() => setSelectedId(null)}
        />
      )}

      {creating && (
        <NewCharacterDialog
          onClose={() => setCreating(false)}
          onCreated={(ch) => {
            setCreating(false);
            setSelectedId(ch.id);
          }}
        />
      )}
    </div>
  );
}

function RosterCard({
  character,
  active,
  onSelect,
  onChat,
}: {
  character: StandaloneCharacter;
  active: boolean;
  onSelect: () => void;
  onChat: () => void;
}) {
  return (
    <motion.div
      layout
      whileHover={{ y: -2 }}
      onClick={onSelect}
      className={cn(
        "group cursor-pointer rounded-xl border bg-bg-card p-3 transition-colors",
        active ? "border-accent-primary" : "border-border hover:border-accent-primary/50",
      )}
    >
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-accent-primary/15 text-sm font-bold text-accent-primary">
          {character.name.slice(0, 2).toUpperCase()}
        </div>
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold text-fg-primary">{character.name}</div>
          <div className="truncate text-xs text-fg-muted">{character.description || "No description"}</div>
        </div>
      </div>
      <div className="mt-3 flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          <span
            className={cn(
              "rounded-full px-2 py-0.5 text-[10px] font-medium",
              character.entity_id
                ? "bg-emerald-500/10 text-emerald-300"
                : "bg-bg-hover text-fg-dim",
            )}
          >
            {character.entity_id ? "MONITOR" : "Light card"}
          </span>
          {character.versions && character.versions.length > 1 ? (
            <span
              className="rounded-full bg-bg-hover px-2 py-0.5 text-[10px] font-medium text-fg-muted"
              title={`${character.versions.length} incarnations across universes`}
            >
              {character.versions.length}×
            </span>
          ) : null}
        </div>
        <button
          className="btn-ghost gap-1 px-2 py-1 text-xs opacity-0 transition-opacity group-hover:opacity-100"
          onClick={(e) => {
            e.stopPropagation();
            onChat();
          }}
        >
          <MessageCircle className="h-3.5 w-3.5" /> Chat
        </button>
      </div>
    </motion.div>
  );
}

function CharacterDetail({
  character,
  onChat,
  onClose,
}: {
  character: StandaloneCharacter;
  onChat: () => void;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const { notify } = useNotify();
  const [form, setForm] = useState({
    name: character.name,
    description: character.description,
    personality: character.personality,
    gm_notes: character.gm_notes,
    first_message: character.first_message,
  });
  const dirty =
    form.name !== character.name ||
    form.description !== character.description ||
    form.personality !== character.personality ||
    form.gm_notes !== character.gm_notes ||
    form.first_message !== character.first_message;

  const save = useMutation({
    mutationFn: () => entitiesApi.updateStandaloneCharacter(character.id, form),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ENTITY_KEYS.standaloneCharacters() });
      notify("success", "Saved");
    },
    onError: (e: unknown) => notify("error", `Save failed: ${errorMessage(e)}`),
  });

  const expand = useMutation({
    mutationFn: () => entitiesApi.expandCharacter(character.id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ENTITY_KEYS.standaloneCharacters() });
      notify("success", "Expanded into a MONITOR profile");
    },
    onError: (e: unknown) => notify("error", `Expansion failed: ${errorMessage(e)}`),
  });

  // ── Character Versions (per-universe incarnations) ──
  const [newIncUniverse, setNewIncUniverse] = useState("");
  const versionsQ = useQuery({
    queryKey: ["character-versions", character.id],
    queryFn: () => entitiesApi.listCharacterVersions(character.id),
    enabled: !!character.entity_id,
  });
  const addVersion = useMutation({
    mutationFn: (universeId: string) =>
      entitiesApi.createCharacterVersion(character.id, { universe_id: universeId }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["character-versions", character.id] });
      qc.invalidateQueries({ queryKey: ENTITY_KEYS.standaloneCharacters() });
      setNewIncUniverse("");
      notify("success", "Incarnation created in that universe");
    },
    onError: (e: unknown) => notify("error", `Add incarnation failed: ${errorMessage(e)}`),
  });
  const delVersion = useMutation({
    mutationFn: (universeId: string) =>
      entitiesApi.deleteCharacterVersion(character.id, universeId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["character-versions", character.id] });
      qc.invalidateQueries({ queryKey: ENTITY_KEYS.standaloneCharacters() });
      notify("success", "Incarnation deleted");
    },
    onError: (e: unknown) => notify("error", `Delete failed: ${errorMessage(e)}`),
  });

  const del = useMutation({
    mutationFn: () => entitiesApi.deleteStandaloneCharacter(character.id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ENTITY_KEYS.standaloneCharacters() });
      notify("success", "Deleted");
      onClose();
    },
    onError: (e: unknown) => notify("error", `Delete failed: ${errorMessage(e)}`),
  });

  return (
    <aside className="flex w-96 shrink-0 flex-col border-l border-border bg-bg-card/50">
      <div className="flex items-center gap-2 border-b border-border p-4">
        <span className="text-sm font-semibold text-fg-primary">Edit character</span>
        <span
          className={cn(
            "ml-auto rounded-full px-2 py-0.5 text-[10px] font-medium",
            character.entity_id ? "bg-emerald-500/10 text-emerald-300" : "bg-bg-hover text-fg-dim",
          )}
        >
          {character.entity_id ? "MONITOR-backed" : "Light card"}
        </span>
      </div>

      <div className="flex-1 space-y-3 overflow-y-auto p-4">
        <Field label="Name">
          <input className="input-cyber w-full" value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })} />
        </Field>
        <Field label="Description">
          <textarea className="input-cyber w-full" rows={2} value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })} />
        </Field>
        <Field label="Personality">
          <textarea className="input-cyber w-full" rows={3} value={form.personality}
            onChange={(e) => setForm({ ...form, personality: e.target.value })} />
        </Field>
        <Field label="First message">
          <textarea className="input-cyber w-full" rows={2} value={form.first_message}
            onChange={(e) => setForm({ ...form, first_message: e.target.value })} />
        </Field>
        <Field label="Author / GM notes (hidden)">
          <textarea className="input-cyber w-full" rows={2} value={form.gm_notes}
            onChange={(e) => setForm({ ...form, gm_notes: e.target.value })} />
        </Field>

        <div className="flex items-center gap-2 pt-1 text-xs text-fg-muted">
          <Brain className="h-3.5 w-3.5" /> {character.memory_count} memories
          <a
            className="btn-ghost ml-auto gap-1 px-2 py-1"
            href={entitiesApi.exportCharacterCardUrl(character.id)}
          >
            <Download className="h-3.5 w-3.5" /> Export
          </a>
        </div>

        {!character.entity_id && (
          <button
            className="btn-ghost w-full justify-center gap-2 border border-accent-primary/30"
            onClick={() => expand.mutate()}
            disabled={expand.isPending}
          >
            {expand.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
            Expand to MONITOR profile
          </button>
        )}

        {character.entity_id ? (
          <div className="mt-4 rounded-lg border border-border bg-bg-card/50 p-3">
            <div className="mb-2 flex items-center gap-2">
              <span className="text-xs font-semibold text-fg-secondary">
                Incarnations
              </span>
              <span className="text-[10px] text-fg-dim">
                {versionsQ.data?.length ?? 0}
              </span>
            </div>
            <ul className="space-y-1 text-xs">
              {versionsQ.data?.map((v) => (
                <li
                  key={v.version_id}
                  className="flex items-center gap-2 rounded bg-bg-hover px-2 py-1"
                  title={`entity ${v.entity_id.slice(0, 8)}…`}
                >
                  <span className="font-mono text-fg-muted">
                    uni:{v.universe_id.slice(0, 8)}…
                  </span>
                  <span className="text-fg-dim">
                    ent:{v.entity_id.slice(0, 8)}…
                  </span>
                  <button
                    className="btn-ghost ml-auto h-6 px-2 text-[10px] text-red-300 hover:bg-red-500/10"
                    disabled={delVersion.isPending}
                    onClick={() => {
                      if (
                        confirm(
                          `Delete incarnation in universe ${v.universe_id.slice(0, 8)}…? ` +
                            "This removes the entity + NPCProfile.",
                        )
                      ) {
                        delVersion.mutate(v.universe_id);
                      }
                    }}
                  >
                    <Trash2 className="h-3 w-3" />
                  </button>
                </li>
              ))}
              {versionsQ.isLoading ? (
                <li className="flex items-center gap-2 text-fg-muted">
                  <Loader2 className="h-3 w-3 animate-spin" /> loading…
                </li>
              ) : null}
            </ul>
            <div className="mt-2 flex gap-1">
              <input
                value={newIncUniverse}
                onChange={(e) => setNewIncUniverse(e.target.value)}
                placeholder="Universe UUID (paste or pick)"
                className="input-cyber flex-1 px-2 py-1 text-xs"
              />
              <button
                className="btn-cyber px-2 py-1 text-xs"
                disabled={!newIncUniverse.trim() || addVersion.isPending}
                onClick={() => addVersion.mutate(newIncUniverse.trim())}
              >
                {addVersion.isPending ? (
                  <Loader2 className="h-3 w-3 animate-spin" />
                ) : (
                  <Plus className="h-3 w-3" />
                )}
                Add
              </button>
            </div>
            <p className="mt-1 text-[10px] text-fg-dim">
              Each incarnation gets its own entity, NPCProfile, memory set,
              and relationship deltas. Two universes never share state.
            </p>
          </div>
        ) : null}
      </div>

      <div className="flex items-center gap-2 border-t border-border p-3">
        <button className="btn-danger p-2" onClick={() => del.mutate()} title="Delete" disabled={del.isPending}>
          <Trash2 className="h-4 w-4" />
        </button>
        <button
          className="btn-ghost gap-1.5"
          onClick={() => save.mutate()}
          disabled={!dirty || save.isPending}
        >
          {save.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
          Save
        </button>
        <button className="btn-cyber ml-auto gap-1.5" onClick={onChat}>
          <MessageCircle className="h-4 w-4" /> Chat
        </button>
      </div>
    </aside>
  );
}

function NewCharacterDialog({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: (ch: StandaloneCharacter) => void;
}) {
  const qc = useQueryClient();
  const { notify } = useNotify();
  const [form, setForm] = useState({
    name: "",
    description: "",
    personality: "",
    first_message: "",
    gm_notes: "",
  });
  const [concept, setConcept] = useState("");

  const create = useMutation({
    mutationFn: () => entitiesApi.createStandaloneCharacter(form),
    onSuccess: (ch) => {
      qc.invalidateQueries({ queryKey: ENTITY_KEYS.standaloneCharacters() });
      notify("success", `Created ${ch.name}`);
      onCreated(ch);
    },
    onError: (e: unknown) => notify("error", `Create failed: ${errorMessage(e)}`),
  });

  const assist = useMutation({
    mutationFn: () =>
      entitiesApi.draftCharacterCard({
        concept,
        name: form.name,
        description: form.description,
        personality: form.personality,
      }),
    onSuccess: (d) => {
      setForm({
        name: d.name,
        description: d.description,
        personality: d.personality,
        first_message: d.first_message,
        gm_notes: d.gm_notes,
      });
      notify("success", "Card drafted — review and tweak before creating");
    },
    onError: (e: unknown) => notify("error", `Assist failed: ${errorMessage(e)}`),
  });

  return (
    <DialogShell
      title="New character"
      icon={Users}
      onClose={onClose}
      footer={
        <DialogFooter>
          <button className="btn-ghost" onClick={onClose}>Cancel</button>
          <button
            className="btn-cyber"
            onClick={() => create.mutate()}
            disabled={!form.name.trim() || create.isPending}
          >
            {create.isPending ? "Creating…" : "Create"}
          </button>
        </DialogFooter>
      }
    >
      <div className="space-y-3 p-4">
        <div className="rounded-lg border border-accent-primary/25 bg-accent-primary/5 p-3">
          <span className="mb-1 flex items-center gap-1.5 text-xs font-medium text-accent-primary">
            <Sparkles className="h-3.5 w-3.5" /> Need a hand? Describe a concept and let the LLM draft the card.
          </span>
          <div className="flex gap-2">
            <input
              className="input-cyber flex-1"
              placeholder="e.g. a weary dockside tavern keeper hiding a smuggling past"
              value={concept}
              onChange={(e) => setConcept(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && concept.trim()) {
                  e.preventDefault();
                  assist.mutate();
                }
              }}
            />
            <button
              className="btn-ghost gap-1.5 whitespace-nowrap border border-accent-primary/30"
              onClick={() => assist.mutate()}
              disabled={!concept.trim() || assist.isPending}
            >
              {assist.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
              Draft
            </button>
          </div>
        </div>
        <Field label="Name">
          <input className="input-cyber w-full" autoFocus value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })} />
        </Field>
        <Field label="Description">
          <textarea className="input-cyber w-full" rows={2} value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })} />
        </Field>
        <Field label="Personality">
          <textarea className="input-cyber w-full" rows={3}
            placeholder="Dry, watchful tavern keeper; slow to trust…" value={form.personality}
            onChange={(e) => setForm({ ...form, personality: e.target.value })} />
        </Field>
        <Field label="First message (optional)">
          <textarea className="input-cyber w-full" rows={2} value={form.first_message}
            onChange={(e) => setForm({ ...form, first_message: e.target.value })} />
        </Field>
        <Field label="Author / GM notes (optional, hidden)">
          <textarea className="input-cyber w-full" rows={2} value={form.gm_notes}
            onChange={(e) => setForm({ ...form, gm_notes: e.target.value })} />
        </Field>
        <p className="text-xs text-fg-dim">
          A full MONITOR profile (traits, triggers, memory) is generated automatically the first time you chat.
        </p>
      </div>
    </DialogShell>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium text-fg-muted">{label}</span>
      {children}
    </label>
  );
}

function EmptyState({ onCreate }: { onCreate: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-20 text-center">
      <Users className="h-10 w-10 text-fg-dim" />
      <div className="text-sm text-fg-secondary">No characters yet</div>
      <div className="max-w-sm text-xs text-fg-muted">
        Create a character or import a SillyTavern / RisuAI card, then chat with it — MONITOR gives it
        memory, moods, and relationship deltas.
      </div>
      <button className="btn-cyber mt-2 gap-1.5" onClick={onCreate}>
        <Plus className="h-4 w-4" /> New character
      </button>
    </div>
  );
}
