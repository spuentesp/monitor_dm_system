"use client";

import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Loader2, MessageCircle } from "lucide-react";
import { entitiesApi, universesApi } from "@/lib/api";
import { lightRpApi, type ConversationStartResult, type UniverseCharacter } from "@/lib/lightRpApi";
import { useNotify } from "@/components/NotificationProvider";
import { errorMessage } from "@/lib/errors";
import type { StandaloneCharacter } from "@/lib/types";

/**
 * One-click chat with any character in a universe.
 *
 * Picking a universe character opens the chat immediately (first message
 * included) — no import step, no interview, no mode choice. The character's
 * card is fetched so the chat view can render it.
 */
export function UniverseCharacterPicker({
  personaId,
  onStarted,
  onClose,
}: {
  personaId?: string | null;
  onStarted: (character: StandaloneCharacter, started: ConversationStartResult) => void;
  onClose: () => void;
}) {
  const { notify } = useNotify();
  const [universeId, setUniverseId] = useState("");
  const [startingId, setStartingId] = useState<string | null>(null);

  const universesQ = useQuery({
    queryKey: ["universes", "all"],
    queryFn: () => universesApi.listUniverses(),
  });

  useEffect(() => {
    if (!universeId && universesQ.data?.length) {
      setUniverseId(universesQ.data[0].id);
    }
  }, [universesQ.data, universeId]);

  const charactersQ = useQuery({
    queryKey: ["light-rp-universe-characters", universeId],
    queryFn: () => lightRpApi.listUniverseCharacters(universeId),
    enabled: !!universeId,
  });

  async function chatWith(entity: UniverseCharacter) {
    setStartingId(entity.entity_id);
    try {
      // Cross-component call: one action opens the chat with a first message.
      const started = await lightRpApi.startUniverseCharacterChat({
        entity_id: entity.entity_id,
        persona_character_id: personaId ?? null,
      });
      const card = await entitiesApi.getStandaloneCharacter(started.character_id);
      onStarted(card, started);
    } catch (e) {
      notify("error", `Couldn't start chat: ${errorMessage(e)}`);
    } finally {
      setStartingId(null);
    }
  }

  return (
    <div className="flex flex-col gap-3 p-4">
      <p className="text-sm text-fg-secondary">Pick a character to talk to. The chat opens right away.</p>
      <select
        className="input-cyber"
        value={universeId}
        onChange={(e) => setUniverseId(e.target.value)}
        aria-label="Universe"
      >
        {(universesQ.data ?? []).map((u) => (
          <option key={u.id} value={u.id}>
            {u.name}
          </option>
        ))}
      </select>
      {charactersQ.isLoading ? (
        <div className="flex items-center gap-2 text-sm text-fg-muted">
          <Loader2 className="h-4 w-4 animate-spin" /> Loading characters…
        </div>
      ) : charactersQ.isError ? (
        <div role="alert" className="text-sm text-red-300/80">
          Couldn&apos;t load universe characters.
        </div>
      ) : (charactersQ.data ?? []).length === 0 ? (
        <div className="text-sm text-fg-muted">No characters in this universe yet.</div>
      ) : (
        <div className="flex max-h-72 flex-col gap-2 overflow-y-auto">
          {(charactersQ.data ?? []).map((entity) => (
            <button
              key={entity.entity_id}
              type="button"
              className="glass flex items-center gap-3 rounded-xl px-3 py-2 text-left hover:bg-white/5"
              disabled={startingId !== null}
              onClick={() => void chatWith(entity)}
            >
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-accent-primary/15 text-xs font-bold text-accent-primary">
                {entity.name.slice(0, 2).toUpperCase()}
              </div>
              <div className="min-w-0 flex-1">
                <div className="truncate text-sm font-semibold text-fg-primary">{entity.name}</div>
                <div className="truncate text-xs text-fg-muted">{entity.description || "Universe character"}</div>
              </div>
              {startingId === entity.entity_id ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <MessageCircle className="h-4 w-4 text-accent-primary" />
              )}
            </button>
          ))}
        </div>
      )}
      <button type="button" className="btn-ghost justify-center text-xs" onClick={onClose}>
        Cancel
      </button>
    </div>
  );
}
