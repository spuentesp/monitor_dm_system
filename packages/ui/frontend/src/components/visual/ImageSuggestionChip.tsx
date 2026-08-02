"use client";

import { useState } from "react";
import { ImagePlus, Loader2, X } from "lucide-react";

import { imageApi } from "@/lib/api";
import { errorMessage } from "@/lib/errors";
import { cn } from "@/lib/utils";
import { useNotify } from "@/components/NotificationProvider";
import type { ImageSuggestionMeta } from "@/features/chat/types";
import type { ApprovalStatus } from "@/lib/types";

import { PendingAssetPreview } from "./AssetGallery";

const REASON_LABEL: Record<ImageSuggestionMeta["reason"], string> = {
  location_change: "New location",
  npc_entry: "New face",
  visual_state_change: "Appearance changed",
  climax: "Climax",
};

/**
 * A "generate an image?" chip driven by the scene loop's deterministic
 * suggestions (Task 9). NOTHING generates on mount — only an explicit click
 * fires the existing scene/portrait endpoint with trigger="loop_suggestion"
 * and the suggestion's source_turn_id as provenance. The returned PENDING
 * asset reuses the Task 8 PendingAssetPreview approval flow; the chip settles
 * (the parent removes it) after dismiss or an approve/reject decision.
 */
export function ImageSuggestionChip({
  suggestion,
  sessionId,
  characterId = null,
  onSettled,
  className,
}: {
  suggestion: ImageSuggestionMeta;
  /** Play-chat session id — scope for scene-endpoint generations. */
  sessionId: string;
  /** Persona character id, when one is selected — portrait anchor. */
  characterId?: string | null;
  /** Called with the suggestion id once the chip is done (dismissed or the
   *  generated asset was approved/rejected) so the parent can remove it. */
  onSettled: (suggestionId: string) => void;
  className?: string;
}) {
  const { notify } = useNotify();
  const [busy, setBusy] = useState(false);
  const [pending, setPending] = useState<
    | {
        assetId: string;
        imageUrl: string;
        promptWarnings: readonly string[];
        referenceAssetIds: readonly string[];
      }
    | null
  >(null);

  async function generate() {
    if (busy) return;
    setBusy(true);
    try {
      const provenance = {
        trigger: "loop_suggestion" as const,
        source_turn_id: suggestion.source_turn_id,
      };
      // Portrait-typed suggestions use the portrait endpoint only when a
      // character anchor exists (the endpoint is character-card based);
      // otherwise the session-scoped scene endpoint covers the moment.
      if (suggestion.asset_type === "portrait" && characterId) {
        const res = await imageApi.generatePortrait(characterId, provenance);
        setPending({
          assetId: res.asset_id,
          imageUrl: res.avatar_url,
          promptWarnings: res.prompt_warnings ?? [],
          referenceAssetIds: [],
        });
      } else {
        const res = await imageApi.generateScene({ session_id: sessionId, ...provenance });
        setPending({
          assetId: res.asset_id,
          imageUrl: res.image_url,
          promptWarnings: res.prompt_warnings ?? [],
          referenceAssetIds: [],
        });
      }
    } catch (e) {
      notify("error", `Image generation failed: ${errorMessage(e)}`);
    } finally {
      setBusy(false);
    }
  }

  if (pending) {
    return (
      <PendingAssetPreview
        assetId={pending.assetId}
        imageUrl={pending.imageUrl}
        alt={`Generated image for: ${REASON_LABEL[suggestion.reason]}`}
        allowAvatar={suggestion.asset_type === "portrait" && !!characterId}
        warnings={pending.promptWarnings}
        referenceAssetIds={pending.referenceAssetIds}
        onDecided={(_status: ApprovalStatus) => onSettled(suggestion.suggestion_id)}
        className={className}
      />
    );
  }

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border border-purple-500/30 bg-purple-500/10 text-purple-200 text-[11px]",
        className,
      )}
    >
      <button
        type="button"
        onClick={() => void generate()}
        disabled={busy}
        className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full hover:bg-purple-500/20 disabled:opacity-60 transition-colors"
        title={`${REASON_LABEL[suggestion.reason]} — generate an image (nothing happens until you click)`}
      >
        {busy ? <Loader2 className="w-3 h-3 animate-spin" /> : <ImagePlus className="w-3 h-3" />}
        Illustrate: {REASON_LABEL[suggestion.reason]}
      </button>
      <button
        type="button"
        aria-label={`Dismiss image suggestion: ${REASON_LABEL[suggestion.reason]}`}
        onClick={() => onSettled(suggestion.suggestion_id)}
        disabled={busy}
        className="pr-2 py-1 text-purple-300/70 hover:text-purple-100 disabled:opacity-60 transition-colors"
      >
        <X className="w-3 h-3" />
      </button>
    </span>
  );
}
