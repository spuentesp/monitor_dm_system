"use client";

import { useQueries } from "@tanstack/react-query";
import { History } from "lucide-react";
import { entitiesApi } from "@/lib/api";
import type { StandaloneCharacter } from "@/lib/types";
import { formatRelativeTime } from "@/lib/utils";

const CAP = 6;

/**
 * Recent light-RP conversations across all roster characters, newest first.
 *
 * Clicking a card reopens that conversation (transcript loads, and the
 * backend rehydrates the live loop from Mongo on the next send).
 */
export function RecentChatsRail({
  characters,
  onOpen,
}: {
  characters: StandaloneCharacter[];
  onOpen: (character: StandaloneCharacter, conversationId: string) => void;
}) {
  const convQueries = useQueries({
    queries: characters.map((c) => ({
      queryKey: ["character-conversations", c.id],
      queryFn: () => entitiesApi.listCharacterConversations(c.id, CAP),
    })),
  });

  const recent = convQueries
    .flatMap((q, i) => (q.data ?? []).map((conv) => ({ character: characters[i], conv })))
    .sort((a, b) => (b.conv.updated_at ?? "").localeCompare(a.conv.updated_at ?? ""))
    .slice(0, CAP);

  if (recent.length === 0) return null;

  return (
    <section aria-label="Recent chats" className="space-y-2">
      <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
        <History className="h-3.5 w-3.5" /> Recent chats
      </div>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-3">
        {recent.map(({ character, conv }, i) => (
          <button
            key={`${character.id}:${conv.conversation_id ?? i}`}
            type="button"
            onClick={() => conv.conversation_id && onOpen(character, conv.conversation_id)}
            className="glass rounded-xl px-4 py-3 text-left transition-colors hover:border-accent-primary/40"
            title={`Reopen this chat with ${character.name}`}
          >
            <div className="truncate text-sm font-medium text-slate-200">{character.name}</div>
            <div className="mt-0.5 truncate text-[11px] text-slate-500">
              {conv.turn_count} turns · {conv.status ?? "unknown"} ·{" "}
              {formatRelativeTime(conv.updated_at)}
            </div>
          </button>
        ))}
      </div>
    </section>
  );
}
