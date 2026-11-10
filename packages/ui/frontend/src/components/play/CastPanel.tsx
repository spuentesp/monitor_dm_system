"use client";

import { useQuery } from "@tanstack/react-query";
import { Bot, Users } from "lucide-react";

import { entitiesApi } from "@/lib/api";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface CastPanelProps {
  /** The session's controlled character ids (user-controlled roster). */
  controlledCharacterIds: string[];
  /** The session's current speaker character id. */
  speakerCharacterId: string | null;
  /** Optimistic speaker marker until the session refetch confirms the switch. */
  pendingSpeakerId?: string | null;
  /** Universe scope for the GM-controlled NPC list. */
  universeId?: string | null;
  /** Called when the user clicks one of their characters: switch immediately. */
  onSwitchSpeaker: (id: string, name: string) => void;
}

interface CastRow {
  id: string;
  name: string;
}

/** Pure: which badge (if any) a user-character row shows. */
export function speakerBadge(
  rowId: string,
  activeSpeakerId: string | null | undefined,
  sessionSpeakerId: string | null | undefined,
): "speaking" | "speaks next" | null {
  if (rowId !== activeSpeakerId) return null;
  return rowId === sessionSpeakerId ? "speaking" : "speaks next";
}

/** Pure: universe-scoped, capped GM-controlled NPC rows. */
export function filterCastNpcs(
  npcs: Array<{ id: string; name: string; universe_id: string | null }>,
  universeId: string | null | undefined,
  cap = 4,
): CastRow[] {
  return (npcs || [])
    .filter((n) => !universeId || n.universe_id === universeId)
    .slice(0, cap)
    .map((n) => ({ id: n.id, name: n.name }));
}

// ---------------------------------------------------------------------------
// CastPanel — compact who-is-who list (Phase 4 Task 5)
// ---------------------------------------------------------------------------

/**
 * Cast panel for the play console: user characters first (speaker marked,
 * clicking one switches the speaker immediately via
 * SessionPatch.speaker_character_id), then GM-controlled NPCs. Backed by the
 * same roster the scene loop uses (`controlled_character_ids` on the
 * session).
 */
export function CastPanel({
  controlledCharacterIds,
  speakerCharacterId,
  pendingSpeakerId,
  universeId,
  onSwitchSpeaker,
}: CastPanelProps) {
  // Names for the user-controlled roster: standalone characters resolve from
  // the roster list; Neo4j-backed incarnations fall back to a per-id lookup.
  const rosterKey = controlledCharacterIds.join(",") || "none";
  const { data: userRows = [], isLoading: rosterLoading } = useQuery({
    queryKey: ["play-cast-roster", rosterKey],
    queryFn: async (): Promise<CastRow[]> => {
      let names = new Map<string, string>();
      try {
        const standalone = await entitiesApi.listStandaloneCharacters({ limit: 100 });
        names = new Map(standalone.map((c) => [c.id, c.name] as [string, string]));
      } catch {
        // roster still renders with per-id lookups below
      }
      const rows: CastRow[] = [];
      for (const id of controlledCharacterIds) {
        let name = names.get(id);
        if (!name) {
          try {
            const entity = await entitiesApi.getEntity(id);
            name = entity.name;
          } catch {
            name = id.slice(0, 8);
          }
        }
        rows.push({ id, name });
      }
      return rows;
    },
  });

  // GM-controlled NPCs in this universe. Scene-present membership is not
  // exposed to the play console by any endpoint today, so the panel lists the
  // universe's NPCs (see Phase 4 report — a scene-cast payload endpoint would
  // tighten this to "present only").
  const { data: npcRows = [] } = useQuery({
    queryKey: ["play-cast-npcs", universeId ?? "all"],
    queryFn: async (): Promise<CastRow[]> => {
      const listing = await entitiesApi.listNPCs({ limit: 8 });
      return filterCastNpcs(listing.items || [], universeId);
    },
  });

  const activeSpeakerId = pendingSpeakerId ?? speakerCharacterId;

  return (
    <div className="glass rounded-2xl border border-white/5 p-4 space-y-3" data-testid="cast-panel">
      <div className="flex items-center gap-2 text-slate-200">
        <Users className="w-4 h-4 text-emerald-400" />
        <h2 className="text-sm font-semibold">Cast</h2>
      </div>

      <div>
        <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-1.5">
          Your characters
        </p>
        {rosterLoading && userRows.length === 0 ? (
          <p className="text-xs text-slate-500">Loading…</p>
        ) : userRows.length === 0 ? (
          <p className="text-xs text-slate-500">No controlled characters on this session.</p>
        ) : (
          <ul className="space-y-1">
            {userRows.map((row) => {
              const badge = speakerBadge(row.id, activeSpeakerId, speakerCharacterId);
              return (
                <li key={row.id}>
                  <button
                    type="button"
                    onClick={() => onSwitchSpeaker(row.id, row.name)}
                    className={cn(
                      "w-full flex items-center gap-2 rounded-md px-2 py-1.5 text-xs text-left transition-colors",
                      badge
                        ? "bg-emerald-500/10 text-emerald-200 border border-emerald-500/20"
                        : "text-slate-300 hover:bg-white/5 border border-transparent",
                    )}
                    title={badge ? "Speaking now" : `Make ${row.name} the speaker`}
                  >
                    <Users className="w-3 h-3 flex-shrink-0" />
                    <span className="truncate">{row.name}</span>
                    {badge && (
                      <span className="ml-auto tag-purple text-[9px] uppercase flex-shrink-0">
                        {badge}
                      </span>
                    )}
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      <div className="border-t border-white/5 pt-2">
        <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-1.5">
          GM-controlled
        </p>
        {npcRows.length === 0 ? (
          <p className="text-xs text-slate-500">No NPCs loaded.</p>
        ) : (
          <ul className="space-y-1">
            {npcRows.map((row) => (
              <li
                key={row.id}
                className="flex items-center gap-2 rounded-md px-2 py-1.5 text-xs text-slate-400"
              >
                <Bot className="w-3 h-3 flex-shrink-0 text-purple-300/70" />
                <span className="truncate">{row.name}</span>
                <span className="ml-auto text-[9px] uppercase text-slate-600 flex-shrink-0">
                  GM
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
