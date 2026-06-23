"use client";

import { useCallback, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  FileImage,
  FileAudio,
  FileText,
  Upload,
  Trash2,
  Loader2,
  ExternalLink,
  X,
  ImageIcon,
  Music,
  File,
} from "lucide-react";
import { ingestApi } from "@/lib/api";
import type { BinaryAsset } from "@/lib/types";
import { cn, formatBytes, formatRelativeTime } from "@/lib/utils";

// ─── Asset type config ────────────────────────────────────────

const ASSET_TYPES = [
  { value: "image", label: "Image", icon: ImageIcon, color: "text-blue-400", accept: "image/*" },
  { value: "audio", label: "Audio", icon: Music, color: "text-purple-400", accept: "audio/*" },
  { value: "pdf", label: "PDF", icon: FileText, color: "text-amber-400", accept: "application/pdf" },
  { value: "other", label: "Other", icon: File, color: "text-slate-400", accept: "*/*" },
] as const;

function assetTypeIcon(type: string) {
  const t = ASSET_TYPES.find(a => a.value === type);
  if (!t) return <File className="w-4 h-4 text-slate-400" />;
  const Icon = t.icon;
  return <Icon className={cn("w-4 h-4", t.color)} />;
}

// ─── Props ────────────────────────────────────────────────────

interface AssetsPanelProps {
  sourceId?: string;
  universeId?: string;
}

// ─── Component ────────────────────────────────────────────────

export function AssetsPanel({ sourceId, universeId }: AssetsPanelProps) {
  const qc = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const [uploadType, setUploadType] = useState<string>("image");
  const [uploading, setUploading] = useState(false);

  const filter = {
    ...(sourceId ? { source_id: sourceId } : {}),
    ...(universeId ? { universe_id: universeId } : {}),
  };

  const assetsQuery = useQuery({
    queryKey: ["assets", filter],
    queryFn: () => ingestApi.listAssets(filter),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => ingestApi.deleteAsset(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["assets", filter] }),
  });

  const handleUpload = useCallback(async () => {
    const file = fileRef.current?.files?.[0];
    if (!file) return;

    setUploading(true);
    try {
      await ingestApi.uploadAsset(file, {
        source_id: sourceId,
        universe_id: universeId,
        asset_type: uploadType,
      });
      qc.invalidateQueries({ queryKey: ["assets", filter] });
      if (fileRef.current) fileRef.current.value = "";
    } catch (err) {
      console.error("Upload failed:", err);
    } finally {
      setUploading(false);
    }
  }, [sourceId, universeId, uploadType, qc, filter]);

  const assets = assetsQuery.data?.items ?? [];

  return (
    <div className="space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-slate-300 flex items-center gap-2">
          <FileImage className="w-4 h-4 text-blue-400" />
          Binary Assets
          <span className="text-xs text-slate-500">
            ({assetsQuery.data?.total ?? 0})
          </span>
        </h3>
      </div>

      {/* Upload row */}
      <div className="flex items-center gap-2">
        <select
          value={uploadType}
          onChange={e => setUploadType(e.target.value)}
          className="bg-bg-deep border border-slate-700 rounded px-2 py-1 text-xs text-slate-300 focus:border-tag-cyan focus:outline-none"
        >
          {ASSET_TYPES.map(t => (
            <option key={t.value} value={t.value}>{t.label}</option>
          ))}
        </select>
        <input
          ref={fileRef}
          type="file"
          className="hidden"
          accept={ASSET_TYPES.find(t => t.value === uploadType)?.accept ?? "*/*"}
          onChange={handleUpload}
        />
        <button
          onClick={() => fileRef.current?.click()}
          disabled={uploading}
          className={cn(
            "flex items-center gap-1.5 px-3 py-1 rounded text-xs font-medium transition-colors",
            "bg-tag-cyan/15 text-tag-cyan hover:bg-tag-cyan/25",
            uploading && "opacity-50 cursor-wait",
          )}
        >
          {uploading ? (
            <Loader2 className="w-3 h-3 animate-spin" />
          ) : (
            <Upload className="w-3 h-3" />
          )}
          {uploading ? "Uploading..." : "Upload"}
        </button>
      </div>

      {/* Asset list */}
      {assetsQuery.isLoading && (
        <div className="flex items-center gap-2 text-xs text-slate-500">
          <Loader2 className="w-3 h-3 animate-spin" /> Loading assets...
        </div>
      )}

      <AnimatePresence>
        {assets.map(asset => (
          <motion.div
            key={asset.id}
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, x: -20 }}
            className="group flex items-center gap-3 p-2 rounded-lg bg-slate-800/50 hover:bg-slate-800/80 transition-colors"
          >
            {/* Icon */}
            <div className="flex-shrink-0">
              {assetTypeIcon(asset.asset_type)}
            </div>

            {/* Info */}
            <div className="flex-1 min-w-0">
              <p className="text-xs text-slate-200 truncate">{asset.label}</p>
              <p className="text-[10px] text-slate-500">
                {asset.content_type} · {formatBytes(asset.size_bytes)} · {formatRelativeTime(asset.created_at)}
              </p>
            </div>

            {/* Actions */}
            <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
              {asset.presigned_url && (
                <a
                  href={asset.presigned_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="p-1 rounded hover:bg-slate-700 text-slate-400 hover:text-tag-cyan transition-colors"
                  title="Open"
                >
                  <ExternalLink className="w-3 h-3" />
                </a>
              )}
              <button
                onClick={() => deleteMutation.mutate(asset.id)}
                className="p-1 rounded hover:bg-slate-700 text-slate-400 hover:text-red-400 transition-colors"
                title="Delete"
              >
                <Trash2 className="w-3 h-3" />
              </button>
            </div>
          </motion.div>
        ))}
      </AnimatePresence>

      {assets.length === 0 && !assetsQuery.isLoading && (
        <p className="text-xs text-slate-600 text-center py-4">
          No assets yet. Upload an image, audio, or PDF file.
        </p>
      )}
    </div>
  );
}
