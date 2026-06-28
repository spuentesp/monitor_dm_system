"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  BrainCircuit,
  Clock,
  Sparkles,
  BookOpen,
  Wand2,
  Library,
} from "lucide-react";
import { ingestApi } from "@/lib/api";
import { UploadCard } from "./UploadCard";
import { IngestionJobsList } from "./IngestionJobsList";
import { SourceLibrary } from "./SourceLibrary";
import { QuickStartPanel } from "./QuickStartPanel";
import { cn } from "@/lib/utils";
import { useState } from "react";
import { LIVE_JOB_STATUSES } from "./ingest-constants";
import { FORGE_KEYS } from "@/lib/query-keys";
import { useSystems } from "@/hooks/use-systems";
import { useIngestJobs } from "@/hooks/use-ingest-jobs";

type ForgeMode = "quick" | "lorebook";

export function IngestionDashboard() {
  const [mode, setMode] = useState<ForgeMode>("quick");
  const queryClient = useQueryClient();
  useSystems();

  const { jobs = [] } = useIngestJobs();


  const activeJobs = jobs.filter(j => LIVE_JOB_STATUSES.has(j.status));
  const hasActiveJobs = activeJobs.length > 0;

  return (
    <div className="flex flex-col h-full space-y-6">
      {/* Mode toggle */}
      <div className="flex items-center gap-2">
        {([
          { id: "quick" as const, label: "Quick Start", icon: Wand2, hint: "Seed → playable world" },
          { id: "lorebook" as const, label: "Lorebook Ingestion", icon: Library, hint: "PDF / docs → knowledge pack" },
        ]).map(({ id, label, icon: Icon, hint }) => (
          <button
            key={id}
            onClick={() => setMode(id)}
            title={hint}
            className={cn(
              "flex items-center gap-2 px-4 py-2 rounded-xl border text-sm font-medium transition-all",
              mode === id
                ? id === "quick"
                  ? "bg-purple-500/10 text-purple-300 border-purple-500/30"
                  : "bg-cyan-500/10 text-cyan-300 border-cyan-500/30"
                : "border-white/8 text-slate-500 hover:text-slate-300 hover:bg-white/4",
            )}
          >
            <Icon className="w-4 h-4" />
            {label}
          </button>
        ))}
        {hasActiveJobs && (
          <span className="flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-cyan-500/10 border border-cyan-500/20 text-[10px] text-cyan-400 animate-pulse ml-2">
            <BrainCircuit className="w-3 h-3" /> {activeJobs.length} Processing
          </span>
        )}
      </div>

      {mode === "quick" ? (
        <div className="flex-1 overflow-y-auto pr-2 custom-scrollbar">
          <QuickStartPanel />
        </div>
      ) : (
      <div className="grid grid-cols-1 xl:grid-cols-[400px_1fr] gap-6 flex-1 min-h-0">
        {/* Left Column: Actions & Activity */}
        <div className="flex flex-col space-y-6 overflow-y-auto pr-2 custom-scrollbar">
          <section className="shrink-0">
            <UploadCard />
          </section>

          <section className="flex-1 flex flex-col min-h-0">
            <div className="flex items-center justify-between mb-3 px-1">
              <h3 className="text-xs font-bold text-slate-500 uppercase tracking-widest flex items-center gap-2">
                <Clock className="w-3.5 h-3.5 text-slate-600" />
                Recent Activity
              </h3>
            </div>
            <div className="flex-1 min-h-0">
              <IngestionJobsList />
            </div>
          </section>
        </div>

        {/* Right Column: Library */}
        <div className="flex flex-col space-y-4 overflow-hidden">
          <div className="flex items-center justify-between px-1">
            <h3 className="text-xs font-bold text-slate-500 uppercase tracking-widest flex items-center gap-2">
              <BookOpen className="w-3.5 h-3.5 text-slate-600" />
              Book Library
            </h3>
          </div>
          
          <div className="flex-1 overflow-y-auto pr-2 custom-scrollbar">
            <SourceLibrary />
          </div>

          {/* Quick Tips / Help */}
          <div className="glass rounded-xl border border-amber-500/10 bg-amber-500/5 p-4 mt-auto">
            <div className="flex items-start gap-3">
              <Sparkles className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
              <div>
                <p className="text-[11px] font-bold text-amber-200 uppercase tracking-wider">Ingestion Tip</p>
                <p className="text-[11px] text-slate-400 leading-relaxed mt-1">
                  For best results with rulebooks, ensure "Core Math" is enabled in layers.
                  MONITOR uses multiple LLM passes to extract structured mechanics from complex PDF layouts.
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
      )}
    </div>
  );
}
