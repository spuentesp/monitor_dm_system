"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Brain, Loader2, Trash2 } from "lucide-react";
import { lightRpApi, type MemoryItem } from "@/lib/lightRpApi";
import { useNotify } from "@/components/NotificationProvider";
import { errorMessage } from "@/lib/errors";

/** "What this character remembers about you" — with per-memory delete. */
export function MemoryPanel({
  characterId,
  characterName,
}: {
  characterId: string;
  characterName: string;
}) {
  const qc = useQueryClient();
  const { notify } = useNotify();
  const [deleting, setDeleting] = useState<string | null>(null);

  const memoriesQ = useQuery({
    queryKey: ["light-rp-memories", characterId],
    queryFn: () => lightRpApi.listMemoriesAboutYou(characterId, { limit: 50 }),
  });

  async function forget(memory: MemoryItem) {
    setDeleting(memory.id);
    try {
      // Cross-component call: the delete endpoint must be invoked with the
      // character and the exact memory id so recall forgets it too.
      await lightRpApi.deleteMemory(characterId, memory.id);
      await qc.invalidateQueries({ queryKey: ["light-rp-memories", characterId] });
      notify("success", "Memory deleted.");
    } catch (e) {
      notify("error", `Delete failed: ${errorMessage(e)}`);
    } finally {
      setDeleting(null);
    }
  }

  if (memoriesQ.isLoading) {
    return (
      <div className="flex items-center gap-2 p-4 text-sm text-fg-muted">
        <Loader2 className="h-4 w-4 animate-spin" /> Loading memories…
      </div>
    );
  }
  if (memoriesQ.isError) {
    return (
      <div role="alert" className="p-4 text-sm text-red-300/80">
        Couldn&apos;t load memories — check the backend and retry.
      </div>
    );
  }

  const memories = memoriesQ.data?.memories ?? [];
  if (memories.length === 0) {
    return (
      <div className="p-4 text-sm text-fg-muted">
        {characterName} doesn&apos;t remember anything about you yet — chat a while and it will stick.
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-2 p-4">
      <p className="text-xs text-fg-dim">
        What {characterName} remembers about you ({memoriesQ.data?.total ?? memories.length}).
        Deleting a memory makes the character forget it in future chats.
      </p>
      {memories.map((m) => (
        <div key={m.id} className="glass flex items-start gap-3 rounded-xl px-3 py-2">
          <Brain className="mt-0.5 h-4 w-4 shrink-0 text-accent-primary" />
          <div className="min-w-0 flex-1">
            <div className="text-sm text-fg-secondary">{m.text}</div>
            <div className="mt-0.5 text-[10px] uppercase tracking-wide text-fg-dim">
              {m.created_at ? new Date(m.created_at).toLocaleString() : ""} · importance{" "}
              {(m.importance ?? 0).toFixed(2)}
            </div>
          </div>
          <button
            type="button"
            className="btn-ghost p-1.5"
            title="Forget this memory"
            aria-label={`Forget memory: ${m.text.slice(0, 40)}`}
            disabled={deleting === m.id}
            onClick={() => void forget(m)}
          >
            {deleting === m.id ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Trash2 className="h-4 w-4" />
            )}
          </button>
        </div>
      ))}
    </div>
  );
}
