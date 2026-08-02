"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { imageApi } from "@/lib/api";
import { errorMessage } from "@/lib/errors";
import type {
  ApprovalStatus,
  GeneratedAsset,
  GeneratedAssetListFilter,
  ReferenceStatus,
} from "@/lib/types";
import { useNotify } from "@/components/NotificationProvider";
import { cn } from "@/lib/utils";

/**
 * The provider-side mode used to drive an asset's image generation.
 *
 * - ``"text-only"`` — the orchestrator fell back to text-only generation
 *   because the configured provider advertises no support for inline
 *   reference bytes. Today this is the only state shipped adapters reach
 *   (MiniMax and Gemini both report ``supports_reference_images=False``).
 * - ``"reference"`` — the orchestrator loaded approved reference bytes
 *   and forwarded them to the provider; the "reference conditioning
 *   active" warning is recorded on ``prompt_warnings``.
 * - ``"unknown"`` — the asset predates the warning pipeline; derive the
 *   mode from ``reference_asset_ids`` presence as a best-effort fallback.
 */
export type ReferenceConditioningMode = "text-only" | "reference" | "unknown";

/**
 * Derive the reference-conditioning mode from the asset's recorded
 * warnings (Task 11). When warnings are absent (older assets) fall back to
 * the presence of ``reference_asset_ids`` so the UI still surfaces a
 * meaningful signal.
 */
export function deriveReferenceConditioningMode(
  warnings: readonly string[] | undefined,
  referenceAssetIds: readonly string[] | undefined,
): ReferenceConditioningMode {
  const list = warnings ?? [];
  if (list.some((w) => w.includes("reference conditioning active"))) return "reference";
  if (list.some((w) => w.includes("text-only fallback"))) return "text-only";
  if ((referenceAssetIds ?? []).length > 0) return "reference";
  return "text-only";
}

function ReferenceModeBadge({ mode }: { mode: ReferenceConditioningMode }) {
  const label =
    mode === "reference" ? "Reference conditioning active" : "Text-only fallback";
  const cls =
    mode === "reference"
      ? "border-emerald-500/25 bg-emerald-500/10 text-emerald-300"
      : "border-amber-500/30 bg-amber-500/10 text-amber-300";
  const testId = mode === "reference" ? "ref-mode-active" : "ref-mode-text-only";
  return (
    <span
      data-testid={testId}
      title={
        mode === "reference"
          ? "Approved reference bytes were sent to the image provider alongside the prompt."
          : "The image provider does not consume reference bytes; this generation used the prompt text only."
      }
      className={cn(
        "rounded-md border px-2 py-0.5 text-[10px] font-medium",
        cls,
      )}
    >
      {label}
    </span>
  );
}

// ─── Shared review controls ──────────────────────────────────

function AssetReviewControls({
  showAvatarOption,
  busy,
  onApprove,
  onReject,
}: {
  showAvatarOption: boolean;
  busy: boolean;
  onApprove: (opts: { use_as_avatar: boolean; reference_status: ReferenceStatus }) => void;
  onReject: () => void;
}) {
  const [useAsAvatar, setUseAsAvatar] = useState(false);
  const [referenceStatus, setReferenceStatus] = useState<ReferenceStatus>("none");
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-3">
        <label className="flex items-center gap-1.5 text-[11px] text-fg-muted">
          Reference status
          <select
            aria-label="Reference status"
            className="input-cyber px-1.5 py-1 text-[11px]"
            value={referenceStatus}
            onChange={(e) => setReferenceStatus(e.target.value as ReferenceStatus)}
          >
            <option value="none">none</option>
            <option value="supporting">supporting</option>
            <option value="primary">primary</option>
          </select>
        </label>
        {showAvatarOption && (
          <label className="flex items-center gap-1.5 text-[11px] text-fg-muted">
            <input
              type="checkbox"
              className="h-3 w-3 accent-accent-primary"
              checked={useAsAvatar}
              onChange={(e) => setUseAsAvatar(e.target.checked)}
            />
            Use as avatar
          </label>
        )}
      </div>
      <div className="flex gap-2">
        <button
          type="button"
          disabled={busy}
          onClick={() => onApprove({ use_as_avatar: useAsAvatar, reference_status: referenceStatus })}
          className="btn-cyber px-3 py-1 text-xs"
        >
          Approve
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={onReject}
          className="btn-ghost border-red-500/30 px-3 py-1 text-xs text-red-300"
        >
          Reject
        </button>
      </div>
    </div>
  );
}

function StatusBadge({ status }: { status: ApprovalStatus }) {
  if (status === "pending") {
    return (
      <span className="rounded-md border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 text-[10px] text-amber-300">
        Pending approval
      </span>
    );
  }
  if (status === "rejected") {
    return (
      <span className="rounded-md border border-red-500/30 bg-red-500/10 px-2 py-0.5 text-[10px] text-red-300">
        Rejected
      </span>
    );
  }
  return (
    <span className="rounded-md border border-emerald-500/25 bg-emerald-500/10 px-2 py-0.5 text-[10px] text-emerald-300">
      Approved
    </span>
  );
}

// ─── Pending preview (post-generation) ───────────────────────

/**
 * Inline review card for a freshly generated PENDING asset. Only approving
 * (optionally with use_as_avatar) makes the image durable in galleries /
 * avatars; rejecting discards it from default views.
 *
 * The ``warnings`` and ``referenceAssetIds`` props surface the provider
 * mode on the preview (Task 11): "reference conditioning active" when
 * approved reference bytes were sent, "text-only fallback" otherwise.
 */
export function PendingAssetPreview({
  assetId,
  imageUrl,
  alt = "Generated image preview",
  allowAvatar = false,
  warnings,
  referenceAssetIds,
  onDecided,
  className,
}: {
  assetId: string;
  imageUrl: string;
  alt?: string;
  allowAvatar?: boolean;
  /** Optional ``prompt_warnings`` from the generation response. */
  warnings?: readonly string[];
  /** Optional ``reference_asset_ids`` from the generation response / asset. */
  referenceAssetIds?: readonly string[];
  onDecided?: (status: ApprovalStatus) => void;
  className?: string;
}) {
  const { notify } = useNotify();
  const [busy, setBusy] = useState(false);
  const [decided, setDecided] = useState<ApprovalStatus | null>(null);

  async function approve(opts: { use_as_avatar: boolean; reference_status: ReferenceStatus }) {
    if (busy) return;
    setBusy(true);
    try {
      await imageApi.approveAsset(assetId, opts);
      setDecided("approved");
      onDecided?.("approved");
    } catch (e) {
      notify("error", `Approve failed: ${errorMessage(e)}`);
    } finally {
      setBusy(false);
    }
  }

  async function reject() {
    if (busy) return;
    setBusy(true);
    try {
      await imageApi.rejectAsset(assetId);
      setDecided("rejected");
      onDecided?.("rejected");
    } catch (e) {
      notify("error", `Reject failed: ${errorMessage(e)}`);
    } finally {
      setBusy(false);
    }
  }

  if (decided === "rejected") {
    return <div className={cn("text-[11px] text-fg-dim", className)}>Image rejected.</div>;
  }

  const mode = deriveReferenceConditioningMode(warnings, referenceAssetIds);

  return (
    <div className={cn("flex flex-col gap-2", className)}>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={imageUrl} alt={alt} className="max-w-full rounded-lg border border-white/10" />
      {decided === "approved" ? (
        <>
          <StatusBadge status="approved" />
          <ReferenceModeBadge mode={mode} />
        </>
      ) : (
        <>
          <StatusBadge status="pending" />
          <ReferenceModeBadge mode={mode} />
          <AssetReviewControls
            showAvatarOption={allowAvatar}
            busy={busy}
            onApprove={(opts) => void approve(opts)}
            onReject={() => void reject()}
          />
        </>
      )}
    </div>
  );
}

// ─── Gallery ─────────────────────────────────────────────────

/**
 * Scope-filtered gallery of generated assets. Pending assets render as
 * previews with approve/reject actions (approve supports use_as_avatar for
 * character portraits and a reference role); rejected assets are hidden by
 * default (the backend excludes them) and can be revealed with "Show rejected".
 */
export function AssetGallery({
  filter,
  allowAvatar = false,
  onChanged,
  emptyMessage = "No images yet — generate a portrait or scene image to see it here.",
}: {
  filter: GeneratedAssetListFilter;
  allowAvatar?: boolean;
  onChanged?: () => void;
  emptyMessage?: string;
}) {
  const { notify } = useNotify();
  const qc = useQueryClient();
  const [showRejected, setShowRejected] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);

  const assetsQ = useQuery({
    queryKey: ["generated-assets", filter, showRejected],
    queryFn: () => imageApi.listAssets({ ...filter, include_rejected: showRejected }),
  });

  async function refresh() {
    await qc.invalidateQueries({ queryKey: ["generated-assets"] });
    onChanged?.();
  }

  async function approve(
    asset: GeneratedAsset,
    opts: { use_as_avatar: boolean; reference_status: ReferenceStatus },
  ) {
    if (busyId) return;
    setBusyId(asset.asset_id);
    try {
      await imageApi.approveAsset(asset.asset_id, opts);
      await refresh();
    } catch (e) {
      notify("error", `Approve failed: ${errorMessage(e)}`);
    } finally {
      setBusyId(null);
    }
  }

  async function reject(asset: GeneratedAsset) {
    if (busyId) return;
    setBusyId(asset.asset_id);
    try {
      await imageApi.rejectAsset(asset.asset_id);
      await refresh();
    } catch (e) {
      notify("error", `Reject failed: ${errorMessage(e)}`);
    } finally {
      setBusyId(null);
    }
  }

  const assets = assetsQ.data ?? [];

  return (
    <div className="flex flex-col gap-3">
      <label className="flex items-center gap-2 text-[11px] text-fg-muted">
        <input
          type="checkbox"
          className="h-3 w-3 accent-accent-primary"
          checked={showRejected}
          onChange={(e) => setShowRejected(e.target.checked)}
        />
        Show rejected
      </label>

      {assetsQ.isLoading ? (
        <div className="flex items-center gap-2 text-xs text-fg-muted">
          <Loader2 className="h-3.5 w-3.5 animate-spin" /> Loading images…
        </div>
      ) : assetsQ.isError ? (
        <div role="alert" className="text-xs text-red-300/80">
          Couldn't load images — check the backend and retry.
        </div>
      ) : assets.length === 0 ? (
        <div className="text-xs text-fg-muted">{emptyMessage}</div>
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {assets.map((a) => (
            <div key={a.asset_id} className="glass flex flex-col gap-2 rounded-xl p-3">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={imageApi.assetFileUrl(a.asset_id)}
                alt={`${a.asset_type} asset`}
                className="w-full rounded-lg border border-white/10 object-cover"
              />
              <div className="flex items-center gap-2">
                <StatusBadge status={a.approval_status} />
                {a.reference_status !== "none" && (
                  <span className="rounded-md border border-cyan-500/25 bg-cyan-500/10 px-2 py-0.5 text-[10px] capitalize text-cyan-300">
                    {a.reference_status} reference
                  </span>
                )}
              </div>
              <ReferenceModeBadge
                mode={deriveReferenceConditioningMode(a.prompt_warnings, a.reference_asset_ids)}
              />
              {a.approval_status === "pending" && (
                <AssetReviewControls
                  showAvatarOption={allowAvatar && a.asset_type === "portrait" && !!a.character_id}
                  busy={busyId === a.asset_id}
                  onApprove={(opts) => void approve(a, opts)}
                  onReject={() => void reject(a)}
                />
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
