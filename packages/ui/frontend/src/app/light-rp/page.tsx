"use client";

import { useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Upload } from "lucide-react";
import { entitiesApi } from "@/lib/api";
import { CharacterChat } from "@/components/characters/CharacterChat";
import { CharacterCardGrid } from "@/components/lightrp/CharacterCardGrid";
import { useNotify } from "@/components/NotificationProvider";
import { errorMessage } from "@/lib/errors";
import type { StandaloneCharacter } from "@/lib/types";

export default function LightRpPage() {
  const qc = useQueryClient();
  const { notify } = useNotify();
  const fileRef = useRef<HTMLInputElement>(null);
  const [active, setActive] = useState<StandaloneCharacter | null>(null);
  const [importing, setImporting] = useState(false);

  const charactersQ = useQuery({
    queryKey: ["standalone-characters"],
    queryFn: () => entitiesApi.listStandaloneCharacters(),
  });

  async function importCard(file: File) {
    setImporting(true);
    try {
      await entitiesApi.importCharacterCard(file);
      await qc.invalidateQueries({ queryKey: ["standalone-characters"] });
      notify("success", `Imported ${file.name}`);
    } catch (e) {
      notify("error", `Import failed: ${errorMessage(e)}`);
    } finally {
      setImporting(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  async function deleteChar(c: StandaloneCharacter) {
    try {
      await entitiesApi.deleteStandaloneCharacter(c.id);
      await qc.invalidateQueries({ queryKey: ["standalone-characters"] });
    } catch (e) {
      notify("error", `Delete failed: ${errorMessage(e)}`);
    }
  }

  if (active) {
    return (
      <div className="h-full min-h-0 p-4">
        <CharacterChat character={active} onBack={() => setActive(null)} />
      </div>
    );
  }

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6 p-8">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-100">Light RP</h1>
          <p className="mt-1 text-sm text-slate-500">
            Story-free chats with your characters. No canon, no dice — just talk.
          </p>
        </div>
        <div>
          <input
            ref={fileRef}
            id="import-card"
            type="file"
            accept=".json,.png"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) void importCard(f);
            }}
          />
          <label htmlFor="import-card" className="btn-cyber flex cursor-pointer items-center gap-2 px-4 py-2 text-sm">
            <Upload className="h-4 w-4" /> {importing ? "Importing…" : "Import card"}
          </label>
        </div>
      </header>

      {charactersQ.isLoading ? (
        <div className="text-sm text-slate-500">Loading characters…</div>
      ) : (
        <CharacterCardGrid
          characters={charactersQ.data ?? []}
          onChat={setActive}
          onDelete={(c) => void deleteChar(c)}
        />
      )}
    </div>
  );
}
