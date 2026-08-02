"use client";

import { useCallback, useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { ApiError, imageApi } from "@/lib/api";
import { errorMessage } from "@/lib/errors";
import type { VisualIdentity, VisualIdentityUpdate } from "@/lib/types";
import { useNotify } from "@/components/NotificationProvider";

type FormState = {
  description: string;
  species_or_type: string;
  apparent_age: string;
  build: string;
  hair: string;
  eyes: string;
  skin_or_surface: string;
  signature_attire: string;
  distinguishing_features: string; // one per line
  palette: string; // comma-separated
  style_hint: string;
};

function toForm(identity: VisualIdentity): FormState {
  return {
    description: identity.description ?? "",
    species_or_type: identity.species_or_type ?? "",
    apparent_age: identity.apparent_age ?? "",
    build: identity.build ?? "",
    hair: identity.hair ?? "",
    eyes: identity.eyes ?? "",
    skin_or_surface: identity.skin_or_surface ?? "",
    signature_attire: identity.signature_attire ?? "",
    distinguishing_features: identity.distinguishing_features.join("\n"),
    palette: identity.palette.join(", "),
    style_hint: identity.style_hint ?? "",
  };
}

function toUpdate(identity: VisualIdentity, form: FormState): VisualIdentityUpdate {
  const list = (raw: string, sep: RegExp) =>
    raw
      .split(sep)
      .map((s) => s.trim())
      .filter(Boolean);
  const opt = (s: string) => (s.trim() ? s.trim() : null);
  return {
    identity_id: identity.identity_id,
    expected_version: identity.version,
    description: form.description,
    species_or_type: opt(form.species_or_type),
    apparent_age: opt(form.apparent_age),
    build: opt(form.build),
    hair: opt(form.hair),
    eyes: opt(form.eyes),
    skin_or_surface: opt(form.skin_or_surface),
    signature_attire: opt(form.signature_attire),
    distinguishing_features: list(form.distinguishing_features, /\r?\n/),
    palette: list(form.palette, /,/),
    style_hint: opt(form.style_hint),
  };
}

/**
 * Editor for a character/entity visual identity. Loads the current draft
 * (falling back to the approved version), saves new versions as drafts with
 * optimistic locking (a 409 surfaces a reload affordance), and — for
 * canon-anchored identities — offers "Submit for review", which stages a
 * CanonKeeper proposal server-side on the same PUT.
 */
export function VisualIdentityEditor({
  characterId,
  entityId,
  universeId,
  onSaved,
}: {
  characterId?: string;
  entityId?: string | null;
  universeId?: string | null;
  onSaved?: (identity: VisualIdentity) => void;
}) {
  const { notify } = useNotify();
  const [identity, setIdentity] = useState<VisualIdentity | null>(null);
  const [form, setForm] = useState<FormState | null>(null);
  const [loading, setLoading] = useState(true);
  const [missing, setMissing] = useState(false);
  const [conflict, setConflict] = useState(false);
  const [saving, setSaving] = useState(false);
  const [savedNote, setSavedNote] = useState<string | null>(null);

  const anchor = {
    character_id: characterId ?? undefined,
    entity_id: entityId ?? undefined,
    universe_id: universeId ?? undefined,
  };

  const load = useCallback(async () => {
    setLoading(true);
    setMissing(false);
    setConflict(false);
    setSavedNote(null);
    try {
      let found: VisualIdentity;
      try {
        found = await imageApi.getCurrentVisualIdentity({ ...anchor, status: "draft" });
      } catch (e) {
        if (!(e instanceof ApiError && e.status === 404)) throw e;
        found = await imageApi.getCurrentVisualIdentity({ ...anchor, status: "approved" });
      }
      setIdentity(found);
      setForm(toForm(found));
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) {
        setMissing(true);
        setIdentity(null);
        setForm(null);
      } else {
        notify("error", `Couldn't load visual identity: ${errorMessage(e)}`);
      }
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [characterId, entityId, universeId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function save(submitForReview: boolean) {
    if (!identity || !form || saving) return;
    setSaving(true);
    setSavedNote(null);
    try {
      const updated = await imageApi.updateVisualIdentity(toUpdate(identity, form));
      setIdentity(updated);
      setForm(toForm(updated));
      setConflict(false);
      setSavedNote(
        submitForReview
          ? "Submitted for CanonKeeper review — the proposal is pending."
          : `Saved as draft v${updated.version}.`,
      );
      onSaved?.(updated);
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        setConflict(true);
      } else {
        notify("error", `Save failed: ${errorMessage(e)}`);
      }
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <div className="flex items-center gap-2 p-4 text-xs text-fg-muted">
        <Loader2 className="h-3.5 w-3.5 animate-spin" /> Loading visual identity…
      </div>
    );
  }

  if (missing) {
    return (
      <div className="p-4 text-xs text-fg-muted">
        No visual identity yet for this character. Identities are created automatically when a
        portrait is generated with canonical context.
      </div>
    );
  }

  if (!identity || !form) return null;

  const set = (key: keyof FormState) => (e: { target: { value: string } }) =>
    setForm({ ...form, [key]: e.target.value });

  return (
    <div className="flex flex-col gap-3 p-4">
      <div className="flex items-center gap-2 text-[11px] text-fg-dim">
        <span className="rounded-md border border-white/10 bg-white/5 px-2 py-0.5 capitalize">
          {identity.status}
        </span>
        <span>v{identity.version}</span>
        {identity.entity_id && <span className="text-cyan-300/80">canon-anchored</span>}
      </div>

      {conflict && (
        <div
          role="alert"
          className="flex items-center justify-between gap-3 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-200"
        >
          Someone else saved a newer version of this identity.
          <button type="button" onClick={() => void load()} className="btn-ghost px-2 py-1 text-xs">
            Reload
          </button>
        </div>
      )}
      {savedNote && <div className="text-xs text-emerald-300">{savedNote}</div>}

      <Field label="Description">
        <textarea
          id="vi-description"
          className="input-cyber min-h-[60px] resize-y"
          value={form.description}
          onChange={set("description")}
        />
      </Field>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Field label="Species/type">
          <input id="vi-species" className="input-cyber" value={form.species_or_type} onChange={set("species_or_type")} />
        </Field>
        <Field label="Apparent age">
          <input id="vi-age" className="input-cyber" value={form.apparent_age} onChange={set("apparent_age")} />
        </Field>
        <Field label="Build">
          <input id="vi-build" className="input-cyber" value={form.build} onChange={set("build")} />
        </Field>
        <Field label="Hair">
          <input id="vi-hair" className="input-cyber" value={form.hair} onChange={set("hair")} />
        </Field>
        <Field label="Eyes">
          <input id="vi-eyes" className="input-cyber" value={form.eyes} onChange={set("eyes")} />
        </Field>
        <Field label="Skin/surface">
          <input id="vi-skin" className="input-cyber" value={form.skin_or_surface} onChange={set("skin_or_surface")} />
        </Field>
      </div>
      <Field label="Signature attire">
        <input
          id="vi-attire"
          className="input-cyber"
          value={form.signature_attire}
          onChange={set("signature_attire")}
        />
      </Field>
      <Field label="Distinguishing features" hint="one per line">
        <textarea
          id="vi-features"
          className="input-cyber min-h-[50px] resize-y"
          value={form.distinguishing_features}
          onChange={set("distinguishing_features")}
        />
      </Field>
      <Field label="Palette" hint="comma-separated color cues">
        <input id="vi-palette" className="input-cyber" value={form.palette} onChange={set("palette")} />
      </Field>
      <Field label="Style hint">
        <input id="vi-style" className="input-cyber" value={form.style_hint} onChange={set("style_hint")} />
      </Field>

      <div className="flex justify-end gap-2 border-t border-border pt-3">
        <button
          type="button"
          onClick={() => void save(false)}
          disabled={saving}
          className="btn-ghost px-3 py-1.5 text-xs"
        >
          {saving ? "Saving…" : "Save draft"}
        </button>
        {identity.entity_id && (
          <button
            type="button"
            onClick={() => void save(true)}
            disabled={saving}
            title="Save and stage a CanonKeeper proposal for the canonical entity"
            className="btn-cyber px-3 py-1.5 text-xs"
          >
            Submit for review
          </button>
        )}
      </div>
    </div>
  );
}

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  const id = (children as React.ReactElement<{ id?: string }>).props.id;
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-[11px] text-fg-muted">
        {label}
        {hint && <span className="ml-1 text-fg-dim">({hint})</span>}
      </label>
      {children}
    </div>
  );
}
