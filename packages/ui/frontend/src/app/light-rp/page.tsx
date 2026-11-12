"use client";

import { useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Images, MessageCircle, Palette, Sparkles, Upload } from "lucide-react";
import { entitiesApi, imageApi } from "@/lib/api";
import { CharacterChat } from "@/components/characters/CharacterChat";
import { DialogShell } from "@/components/DialogShell";
import { CharacterCardGrid } from "@/components/lightrp/CharacterCardGrid";
import { RecentChatsRail } from "@/components/lightrp/RecentChatsRail";
import { UniverseCharacterPicker } from "@/components/lightrp/UniverseCharacterPicker";
import { AssetGallery, PendingAssetPreview } from "@/components/visual/AssetGallery";
import { VisualIdentityEditor } from "@/components/visual/VisualIdentityEditor";
import { useNotify } from "@/components/NotificationProvider";
import { errorMessage } from "@/lib/errors";
import type { ConversationStartResult } from "@/lib/lightRpApi";
import type { PortraitResponse, StandaloneCharacter } from "@/lib/types";

export default function LightRpPage() {
  const qc = useQueryClient();
  const { notify } = useNotify();
  const fileRef = useRef<HTMLInputElement>(null);
  const [active, setActive] = useState<StandaloneCharacter | null>(null);
  const [activeStarted, setActiveStarted] = useState<ConversationStartResult | null>(null);
  // Reopening a past chat from the Recent chats rail: load its transcript
  // instead of starting a new conversation.
  const [resumeId, setResumeId] = useState<string | null>(null);
  const [importing, setImporting] = useState(false);
  // The user's persona — bound by name + description into every chat started
  // from this page (the cast rule keeps the character from speaking for it).
  const [personaId, setPersonaId] = useState<string>("");
  const [pickUniverseCharacter, setPickUniverseCharacter] = useState(false);
  // Freshly generated portrait awaiting approval — the card image only
  // changes when the user approves with "use as avatar".
  const [portraitPreview, setPortraitPreview] = useState<{
    character: StandaloneCharacter;
    result: PortraitResponse;
  } | null>(null);
  const [identityFor, setIdentityFor] = useState<StandaloneCharacter | null>(null);
  const [galleryFor, setGalleryFor] = useState<StandaloneCharacter | null>(null);

  const charactersQ = useQuery({
    queryKey: ["standalone-characters"],
    queryFn: () => entitiesApi.listStandaloneCharacters(),
  });

  const personas = (charactersQ.data ?? []).filter((c) => c.is_ooc_persona);

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

  async function generatePortrait(c: StandaloneCharacter) {
    try {
      const result = await imageApi.generatePortrait(c.id);
      if (result.approval_status === "pending") {
        setPortraitPreview({ character: c, result });
        notify("info", `Portrait generated for ${c.name} — review and approve to use it.`);
      } else {
        await qc.invalidateQueries({ queryKey: ["standalone-characters"] });
        notify("success", `Portrait updated for ${c.name}`);
      }
    } catch (e) {
      notify("error", `Portrait failed: ${errorMessage(e)}`);
    }
  }

  if (active) {
    return (
      <div className="h-full min-h-0 p-4">
        <CharacterChat
          character={active}
          personaId={personaId || null}
          initialConversation={activeStarted}
          resumeConversationId={resumeId}
          onBack={() => {
            setActive(null);
            setActiveStarted(null);
            setResumeId(null);
          }}
        />
      </div>
    );
  }

  return (
    <div className="mx-auto flex h-full max-w-6xl flex-col gap-6 overflow-y-auto p-8">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-100">Light RP</h1>
          <p className="mt-1 text-sm text-slate-500">
            Story-free chats with your characters. No canon, no dice — just talk.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-xs text-fg-muted">
            You are
            <select
              className="input-cyber py-1.5 text-xs"
              value={personaId}
              onChange={(e) => setPersonaId(e.target.value)}
              aria-label="Your persona"
            >
              <option value="">No persona</option>
              {personas.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            className="btn-ghost flex items-center gap-2 px-4 py-2 text-sm"
            onClick={() => setPickUniverseCharacter(true)}
          >
            <MessageCircle className="h-4 w-4" /> Chat with a universe character
          </button>
          <input
            ref={fileRef}
            id="import-card"
            type="file"
            accept=".json,.png,.charx"
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
      ) : charactersQ.isError ? (
        <div
          role="alert"
          className="glass flex items-center justify-between gap-3 rounded-xl px-5 py-4 text-sm text-red-300/80"
        >
          Couldn't load your characters — check the backend and retry.
          <button
            type="button"
            onClick={() => void charactersQ.refetch()}
            className="btn-ghost px-3 py-1.5 text-xs"
          >
            Retry
          </button>
        </div>
      ) : (
        <>
          <RecentChatsRail
            characters={charactersQ.data ?? []}
            onOpen={(c, conversationId) => {
              setActive(c);
              setResumeId(conversationId);
            }}
          />
          <CharacterCardGrid
            characters={charactersQ.data ?? []}
            onChat={(c) => {
              setActive(c);
              setResumeId(null);
            }}
            onGeneratePortrait={(c) => void generatePortrait(c)}
            onEditVisualIdentity={setIdentityFor}
            onVisualReferences={setGalleryFor}
            onDelete={(c) => void deleteChar(c)}
          />
        </>
      )}

      {portraitPreview && (
        <DialogShell
          title={`New portrait for ${portraitPreview.character.name}`}
          icon={Sparkles}
          onClose={() => setPortraitPreview(null)}
          maxWidthClassName="max-w-lg"
        >
          <div className="p-4">
            <PendingAssetPreview
              assetId={portraitPreview.result.asset_id}
              imageUrl={portraitPreview.result.avatar_url}
              alt={`Portrait preview for ${portraitPreview.character.name}`}
              allowAvatar
              onDecided={(status) => {
                if (status === "approved") {
                  void qc.invalidateQueries({ queryKey: ["standalone-characters"] });
                }
                setPortraitPreview(null);
              }}
            />
          </div>
        </DialogShell>
      )}

      {identityFor && (
        <DialogShell
          title={`Visual identity — ${identityFor.name}`}
          icon={Palette}
          onClose={() => setIdentityFor(null)}
          maxWidthClassName="max-w-2xl"
        >
          <VisualIdentityEditor
            characterId={identityFor.id}
            entityId={identityFor.entity_id}
            universeId={identityFor.default_universe_id}
          />
        </DialogShell>
      )}

      {galleryFor && (
        <DialogShell
          title={`Visual references — ${galleryFor.name}`}
          icon={Images}
          onClose={() => setGalleryFor(null)}
          maxWidthClassName="max-w-3xl"
        >
          <div className="p-4">
            <AssetGallery
              filter={{ character_id: galleryFor.id }}
              allowAvatar
              onChanged={() => void qc.invalidateQueries({ queryKey: ["standalone-characters"] })}
            />
          </div>
        </DialogShell>
      )}

      {pickUniverseCharacter && (
        <DialogShell
          title="Chat with a universe character"
          icon={MessageCircle}
          onClose={() => setPickUniverseCharacter(false)}
          maxWidthClassName="max-w-2xl"
        >
          <UniverseCharacterPicker
            personaId={personaId || null}
            onStarted={(card, started) => {
              setPickUniverseCharacter(false);
              setActiveStarted(started);
              setActive(card);
            }}
            onClose={() => setPickUniverseCharacter(false)}
          />
        </DialogShell>
      )}
    </div>
  );
}
