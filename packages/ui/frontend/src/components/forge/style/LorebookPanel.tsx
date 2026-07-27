"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { universesApi } from "@/lib/api";
import { LorebookEditor } from "@/components/lorebook/LorebookEditor";

/**
 * Lorebook tab for /forge/style (F3-4.4). Universe selector on top; the
 * shared LorebookEditor below in universe mode (character picker +
 * "universe-wide" scope). The editor is a full-height modal by design, so it
 * is embedded in a height-bounded wrapper here.
 */
export function LorebookPanel() {
  const universesQ = useQuery({
    queryKey: ["universes"],
    queryFn: () => universesApi.listUniverses(),
  });

  const [selectedUniverseId, setSelectedUniverseId] = useState<string | null>(null);

  // Auto-select the first universe on load.
  if (
    !selectedUniverseId &&
    universesQ.data &&
    universesQ.data.length > 0 &&
    !universesQ.isLoading
  ) {
    setSelectedUniverseId(universesQ.data[0].id);
  }

  const universes = universesQ.data ?? [];

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-3 flex-shrink-0">
        <div>
          <h2 className="text-lg font-bold text-slate-100">Lorebook</h2>
          <p className="text-sm text-slate-500 mt-1">
            Keyword-triggered lore entries, per character or universe-wide.
          </p>
        </div>
        <select
          aria-label="Universe"
          value={selectedUniverseId ?? ""}
          onChange={(e) => setSelectedUniverseId(e.target.value || null)}
          className="ml-auto bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-slate-200"
        >
          {universes.length === 0 && <option value="">No universes</option>}
          {universes.map((u) => (
            <option key={u.id} value={u.id}>
              {u.name}
            </option>
          ))}
        </select>
      </div>

      {selectedUniverseId ? (
        // The editor is a full-height modal (flex flex-col h-full); embed it
        // in a viewport-bounded wrapper so it fits the tab cleanly.
        <div className="h-[70vh] min-h-[480px] rounded-lg border border-zinc-800 overflow-hidden">
          <LorebookEditor universeId={selectedUniverseId} onClose={undefined} />
        </div>
      ) : (
        !universesQ.isLoading && (
          <p className="text-sm text-slate-500">
            Create a universe first to manage its lorebook.
          </p>
        )
      )}
    </div>
  );
}
