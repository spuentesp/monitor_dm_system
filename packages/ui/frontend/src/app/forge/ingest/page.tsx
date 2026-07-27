"use client";

import { useState } from "react";
import { FileImage, Sparkles } from "lucide-react";
import { IngestionDashboard } from "@/components/forge/ingest/IngestionDashboard";
import { AssetsPanel } from "@/components/forge/AssetsPanel";
import { PipelineHealthChip } from "@/components/forge/PipelineHealthChip";
import { cn } from "@/lib/utils";

// ─── Ingest Studio (F1-1) ─────────────────────────────────────
// Extracted from the old /forge hub: upload, sources, ingestion jobs (SSE)
// and Quick Start come from IngestionDashboard (UploadCard +
// IngestionJobsList + QuickStartPanel); asset management from AssetsPanel.

type IngestTab = "sources" | "assets";

export default function IngestStudioPage() {
  const [tab, setTab] = useState<IngestTab>("sources");

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <div className="flex items-center gap-1 px-6 py-3 border-b border-white/5 flex-shrink-0">
        {([
          { id: "sources" as const, label: "Sources", icon: Sparkles },
          { id: "assets" as const,  label: "Assets",  icon: FileImage },
        ]).map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className={cn(
              "flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium transition-all",
              tab === id
                ? "bg-cyan-500/10 text-cyan-300 border border-cyan-500/25"
                : "text-slate-500 hover:text-slate-300 border border-transparent",
            )}
          >
            <Icon className="w-3.5 h-3.5" />
            {label}
          </button>
        ))}
        <div className="flex-1" />
        <PipelineHealthChip />
      </div>

      {tab === "sources" ? (
        <div className="flex-1 overflow-y-auto px-6 py-6 custom-scrollbar">
          <IngestionDashboard />
        </div>
      ) : (
        <div className="flex-1 overflow-auto p-4">
          <AssetsPanel />
        </div>
      )}
    </div>
  );
}
