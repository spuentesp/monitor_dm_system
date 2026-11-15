"use client";

import { useState } from "react";
import { Plus } from "lucide-react";
import { entitiesApi } from "@/lib/api";
import { DialogShell } from "@/components/DialogShell";
import { useNotify } from "@/components/NotificationProvider";
import { errorMessage } from "@/lib/errors";

/** Create a character card — or a persona card for the "You are" picker — from scratch. */
export function CharacterCreateDialog({
  onCreated,
  onClose,
}: {
  onCreated: () => void;
  onClose: () => void;
}) {
  const { notify } = useNotify();
  const [name, setName] = useState("");
  const [isPersona, setIsPersona] = useState(false);
  const [description, setDescription] = useState("");
  const [personality, setPersonality] = useState("");
  const [firstMessage, setFirstMessage] = useState("");
  const [saving, setSaving] = useState(false);

  async function submit() {
    const trimmed = name.trim();
    if (!trimmed || saving) return;
    setSaving(true);
    try {
      await entitiesApi.createStandaloneCharacter({
        name: trimmed,
        description: description.trim() || undefined,
        personality: personality.trim() || undefined,
        first_message: firstMessage.trim() || undefined,
        is_ooc_persona: isPersona,
      });
      notify(
        "success",
        isPersona ? `Persona "${trimmed}" created — pick it in the "You are" menu.` : `Character "${trimmed}" created.`,
      );
      onCreated();
    } catch (e) {
      notify("error", `Create failed: ${errorMessage(e)}`);
    } finally {
      setSaving(false);
    }
  }

  return (
    <DialogShell title={isPersona ? "New persona (you)" : "New character"} icon={Plus} onClose={onClose} maxWidthClassName="max-w-lg">
      <div className="flex flex-col gap-3 p-4">
        <label className="flex flex-col gap-1 text-xs text-fg-muted">
          Name
          <input
            className="input-cyber"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder={isPersona ? "Your character's name" : "Character name"}
            autoFocus
          />
        </label>
        <label className="flex items-center gap-2 text-xs text-fg-muted">
          <input
            type="checkbox"
            checked={isPersona}
            onChange={(e) => setIsPersona(e.target.checked)}
            className="h-3.5 w-3.5 accent-accent-primary"
          />
          This is my persona — appears in the "You are" picker, not the roster
        </label>
        <label className="flex flex-col gap-1 text-xs text-fg-muted">
          Description / persona
          <textarea
            className="input-cyber min-h-[72px] resize-y"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Who they are, how they talk, what drives them…"
          />
        </label>
        <label className="flex flex-col gap-1 text-xs text-fg-muted">
          Personality (short)
          <input
            className="input-cyber"
            value={personality}
            onChange={(e) => setPersonality(e.target.value)}
            placeholder="e.g. witty, guarded, playful"
          />
        </label>
        <label className="flex flex-col gap-1 text-xs text-fg-muted">
          First message (optional)
          <textarea
            className="input-cyber min-h-[56px] resize-y"
            value={firstMessage}
            onChange={(e) => setFirstMessage(e.target.value)}
            placeholder="What they say when a chat opens"
          />
        </label>
        <div className="flex justify-end gap-2 pt-1">
          <button type="button" className="btn-ghost px-4 py-2 text-sm" onClick={onClose}>
            Cancel
          </button>
          <button
            type="button"
            className="btn-cyber px-4 py-2 text-sm"
            disabled={!name.trim() || saving}
            onClick={() => void submit()}
          >
            {saving ? "Creating…" : "Create"}
          </button>
        </div>
      </div>
    </DialogShell>
  );
}
