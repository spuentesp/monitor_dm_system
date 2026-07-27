"use client";

import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Brain, Loader2 } from "lucide-react";
import { DialogFooter, DialogShell } from "@/components/DialogShell";
import { entitiesApi } from "@/lib/api";
import type {
  BehavioralTrigger,
  CharacterPreference,
  EmotionalTendency,
  NPCProfile,
  NPCProfileUpsert,
} from "@/lib/types";

// ─── NPC profile editor (F2-2 phase 5) ────────────────────────
// Modal editor for the Mongo NPCProfile behind a world NPC. Simple fields
// are plain inputs, string lists are one-per-line textareas, traits are
// `name = score` lines, and the three structured lists (tendencies /
// preferences / triggers) are edited as JSON. The backend PUT upserts, so
// this same form creates a profile when none exists yet (GET → 404).

/** True when the query error is the API's 404 (no profile written yet). */
export function isProfileMissing(err: unknown): boolean {
  return (
    typeof err === "object" &&
    err !== null &&
    "status" in err &&
    (err as { status?: unknown }).status === 404
  );
}

function lines(text: string): string[] {
  return text
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean);
}

function toLines(list: string[] | undefined): string {
  return (list ?? []).join("\n");
}

/** Parse `name = score` lines into the traits map. Throws on bad lines. */
function parseTraits(text: string): Record<string, number> {
  const out: Record<string, number> = {};
  for (const raw of lines(text)) {
    const m = /^([^=]+?)\s*=\s*(-?\d+(?:\.\d+)?)$/.exec(raw);
    if (!m) throw new Error(`Bad trait line "${raw}" — expected "name = score".`);
    const score = Number(m[2]);
    if (score < 0 || score > 1) throw new Error(`Trait "${m[1]}" score must be 0–1.`);
    out[m[1].trim()] = score;
  }
  return out;
}

function traitsToText(traits: Record<string, number> | undefined): string {
  return Object.entries(traits ?? {})
    .map(([k, v]) => `${k} = ${v}`)
    .join("\n");
}

/** Parse a JSON textarea that must hold an array (empty = []). */
function parseJsonList<T>(text: string, label: string): T[] {
  if (!text.trim()) return [];
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    throw new Error(`${label} is not valid JSON.`);
  }
  if (!Array.isArray(parsed)) throw new Error(`${label} must be a JSON array.`);
  return parsed as T[];
}

function jsonListText(list: unknown[] | undefined): string {
  return list && list.length > 0 ? JSON.stringify(list, null, 2) : "";
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="text-[10px] text-slate-600 uppercase tracking-wider mb-1">{label}</p>
      {children}
    </div>
  );
}

export function NPCProfileEditor({
  npcId,
  npcName,
  onClose,
  onSaved,
}: {
  npcId: string;
  npcName?: string;
  onClose: () => void;
  onSaved?: () => void;
}) {
  const qc = useQueryClient();
  const profileQ = useQuery({
    queryKey: ["npc-profile", npcId],
    queryFn: () => entitiesApi.getNPCProfile(npcId),
    retry: false,
  });
  // 404 just means "no profile yet" — the PUT upserts, so the form starts
  // empty instead of erroring out.
  const missing = profileQ.isError && isProfileMissing(profileQ.error);
  const fatal = profileQ.isError && !missing;
  const profile: NPCProfile | null = profileQ.data ?? null;

  const [speechStyle, setSpeechStyle] = useState("");
  const [emotionalState, setEmotionalState] = useState("");
  const [gmNotes, setGmNotes] = useState("");
  const [traitsText, setTraitsText] = useState("");
  const [valuesText, setValuesText] = useState("");
  const [fearsText, setFearsText] = useState("");
  const [desiresText, setDesiresText] = useState("");
  const [catchphrasesText, setCatchphrasesText] = useState("");
  const [mannerismsText, setMannerismsText] = useState("");
  const [secretsText, setSecretsText] = useState("");
  const [tendenciesText, setTendenciesText] = useState("");
  const [preferencesText, setPreferencesText] = useState("");
  const [triggersText, setTriggersText] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const [hydrated, setHydrated] = useState(false);

  // Fill the form once the profile arrives (or once we know there is none).
  useEffect(() => {
    if (hydrated) return;
    if (profile) {
      setSpeechStyle(profile.speech_style ?? "");
      setEmotionalState(profile.current_emotional_state ?? "");
      setGmNotes(profile.gm_notes ?? "");
      setTraitsText(traitsToText(profile.traits));
      setValuesText(toLines(profile.values));
      setFearsText(toLines(profile.fears));
      setDesiresText(toLines(profile.desires));
      setCatchphrasesText(toLines(profile.catchphrases));
      setMannerismsText(toLines(profile.mannerisms));
      setSecretsText(toLines(profile.secrets));
      setTendenciesText(jsonListText(profile.emotional_tendencies));
      setPreferencesText(jsonListText(profile.preferences));
      setTriggersText(jsonListText(profile.triggers));
      setHydrated(true);
    } else if (missing) {
      setHydrated(true);
    }
  }, [profile, missing, hydrated]);

  const save = useMutation({
    mutationFn: (body: NPCProfileUpsert) => entitiesApi.updateNPCProfile(npcId, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["npc-profile", npcId] });
      onSaved?.();
      onClose();
    },
  });

  const submit = () => {
    try {
      const body: NPCProfileUpsert = {
        speech_style: speechStyle.trim() || null,
        current_emotional_state: emotionalState.trim() || null,
        gm_notes: gmNotes.trim() || null,
        traits: parseTraits(traitsText),
        values: lines(valuesText),
        fears: lines(fearsText),
        desires: lines(desiresText),
        catchphrases: lines(catchphrasesText),
        mannerisms: lines(mannerismsText),
        secrets: lines(secretsText),
        emotional_tendencies: parseJsonList<EmotionalTendency>(
          tendenciesText,
          "Emotional tendencies",
        ),
        preferences: parseJsonList<CharacterPreference>(preferencesText, "Preferences"),
        triggers: parseJsonList<BehavioralTrigger>(triggersText, "Behavioral triggers"),
      };
      setFormError(null);
      save.mutate(body);
    } catch (err) {
      setFormError((err as Error).message);
    }
  };

  return (
    <DialogShell
      title={npcName ? `NPC profile — ${npcName}` : "NPC profile"}
      icon={Brain}
      onClose={onClose}
      maxWidthClassName="max-w-2xl"
      footer={
        <DialogFooter>
          <button className="btn-ghost text-xs" onClick={onClose} disabled={save.isPending}>
            Cancel
          </button>
          <button
            className="btn-cyber text-xs py-1.5 disabled:opacity-40"
            disabled={save.isPending || profileQ.isLoading || fatal}
            onClick={submit}
          >
            {save.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : null}
            {missing ? "Create profile" : "Save profile"}
          </button>
        </DialogFooter>
      }
    >
      <div className="p-4 space-y-3 max-h-[70vh] overflow-y-auto">
        {profileQ.isLoading && (
          <div className="flex items-center gap-2 text-slate-500 text-sm py-8 justify-center">
            <Loader2 className="w-4 h-4 animate-spin" /> Loading profile…
          </div>
        )}
        {fatal && (
          <p className="text-sm text-red-300 py-8 text-center">
            Could not load profile: {(profileQ.error as Error)?.message}
          </p>
        )}
        {missing && (
          <p className="text-[11px] text-slate-500">
            No profile exists for this NPC yet — saving will create one.
          </p>
        )}
        {hydrated && !fatal && (
          <>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Speech style">
                <input
                  aria-label="Speech style"
                  className="input-cyber w-full text-sm py-1"
                  value={speechStyle}
                  onChange={(e) => setSpeechStyle(e.target.value)}
                  placeholder="e.g. terse military clipped"
                />
              </Field>
              <Field label="Current emotional state">
                <input
                  aria-label="Current emotional state"
                  className="input-cyber w-full text-sm py-1"
                  value={emotionalState}
                  onChange={(e) => setEmotionalState(e.target.value)}
                  placeholder="e.g. wary"
                />
              </Field>
            </div>
            <Field label="Traits (name = 0–1 score, one per line)">
              <textarea
                aria-label="Traits"
                className="input-cyber w-full text-xs font-mono resize-none"
                rows={3}
                value={traitsText}
                onChange={(e) => setTraitsText(e.target.value)}
                placeholder={"openness = 0.8\nconscientiousness = 0.3"}
              />
            </Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Values (one per line)">
                <textarea
                  aria-label="Values"
                  className="input-cyber w-full text-xs resize-none"
                  rows={3}
                  value={valuesText}
                  onChange={(e) => setValuesText(e.target.value)}
                />
              </Field>
              <Field label="Fears (one per line)">
                <textarea
                  aria-label="Fears"
                  className="input-cyber w-full text-xs resize-none"
                  rows={3}
                  value={fearsText}
                  onChange={(e) => setFearsText(e.target.value)}
                />
              </Field>
              <Field label="Desires (one per line)">
                <textarea
                  aria-label="Desires"
                  className="input-cyber w-full text-xs resize-none"
                  rows={3}
                  value={desiresText}
                  onChange={(e) => setDesiresText(e.target.value)}
                />
              </Field>
              <Field label="Catchphrases (one per line)">
                <textarea
                  aria-label="Catchphrases"
                  className="input-cyber w-full text-xs resize-none"
                  rows={3}
                  value={catchphrasesText}
                  onChange={(e) => setCatchphrasesText(e.target.value)}
                />
              </Field>
              <Field label="Mannerisms (one per line)">
                <textarea
                  aria-label="Mannerisms"
                  className="input-cyber w-full text-xs resize-none"
                  rows={3}
                  value={mannerismsText}
                  onChange={(e) => setMannerismsText(e.target.value)}
                />
              </Field>
              <Field label="Secrets — GM only (one per line)">
                <textarea
                  aria-label="Secrets"
                  className="input-cyber w-full text-xs resize-none"
                  rows={3}
                  value={secretsText}
                  onChange={(e) => setSecretsText(e.target.value)}
                />
              </Field>
            </div>
            <Field label='Emotional tendencies (JSON array, e.g. [{"emotion":"anger","baseline":0.3,"volatility":0.7}])'>
              <textarea
                aria-label="Emotional tendencies"
                className="input-cyber w-full text-xs font-mono resize-none"
                rows={3}
                value={tendenciesText}
                onChange={(e) => setTendenciesText(e.target.value)}
              />
            </Field>
            <Field label="Preferences (JSON array of {category, item, valence, reason?})">
              <textarea
                aria-label="Preferences"
                className="input-cyber w-full text-xs font-mono resize-none"
                rows={3}
                value={preferencesText}
                onChange={(e) => setPreferencesText(e.target.value)}
              />
            </Field>
            <Field label="Behavioral triggers (JSON array of {condition, reaction, intensity, is_hidden})">
              <textarea
                aria-label="Behavioral triggers"
                className="input-cyber w-full text-xs font-mono resize-none"
                rows={3}
                value={triggersText}
                onChange={(e) => setTriggersText(e.target.value)}
              />
            </Field>
            <Field label="GM notes">
              <textarea
                aria-label="GM notes"
                className="input-cyber w-full text-sm resize-none"
                rows={4}
                value={gmNotes}
                onChange={(e) => setGmNotes(e.target.value)}
              />
            </Field>
          </>
        )}
        {formError && <p className="text-[11px] text-red-300">{formError}</p>}
        {save.isError && (
          <p className="text-[11px] text-red-300">
            Save failed: {(save.error as Error)?.message}
          </p>
        )}
      </div>
    </DialogShell>
  );
}
