"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  FileText,
  Loader2,
  RefreshCw,
  Trash2,
  Search,
  PackageCheck,
  AlertTriangle,
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { ingestApi } from "@/lib/api";
import type { Source, IngestJob } from "@/lib/types";
import { cn, formatRelativeTime } from "@/lib/utils";
import { StatusBadge } from "./StatusBadge";
import { DialogFooter, DialogShell } from "@/components/DialogShell";
import { SCAN_TYPES, INGEST_TARGETS, getLayersForTarget, type ScanType, type IngestTarget, mergeJobsSafely } from "./ingest-constants";
import { FORGE_KEYS } from "@/lib/query-keys";

export function SourceLibrary() {
  const qc = useQueryClient();
  const [searchTerm, setSearchTerm] = useState("");
  const [confirmDelete, setConfirmDelete] = useState<Source | null>(null);
  const [rescanItem, setRescanItem] = useState<Source | null>(null);
  const [scanType, setScanType] = useState<string>("setting_supplement");
  const [ingestTarget, setIngestTarget] = useState<string>("everything");
  const [errorNotice, setErrorNotice] = useState<string | null>(null);

  const { data: sources = [], isLoading } = useQuery<Source[]>({
    queryKey: FORGE_KEYS.sources,
    queryFn: ingestApi.listSources,
  });

  const { data: jobs = [] } = useQuery<IngestJob[]>({
    queryKey: FORGE_KEYS.jobs,
    queryFn: async () => {
      const incoming = await ingestApi.listJobs();
      const prev = qc.getQueryData<IngestJob[]>(FORGE_KEYS.jobs);
      return mergeJobsSafely(prev, incoming);
    },
    staleTime: 5000,
    refetchInterval: 5000,
  });

  const deleteSource = useMutation({
    mutationFn: (id: string) => ingestApi.deleteSource(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: FORGE_KEYS.sources });
      qc.invalidateQueries({ queryKey: FORGE_KEYS.jobs });
      setConfirmDelete(null);
    },
  });

  const rescanSource = useMutation({
    mutationFn: (variables: { sourceId: string; scanType: string; target: string }) =>
      ingestApi.rescanSource(variables.sourceId, {
        scan_type: variables.scanType,
        analysis_layers: getLayersForTarget(variables.target as IngestTarget, variables.scanType as ScanType),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: FORGE_KEYS.jobs });
      qc.invalidateQueries({ queryKey: FORGE_KEYS.sources });
      setRescanItem(null);
      setErrorNotice(null);
    },
    onError: (err: any) => {
      setErrorNotice(err.message || "Failed to start rescan.");
    },
  });

  const sourcePacks = useMemo(() => {
    const map: Record<string, string[]> = {};
    for (const job of jobs) {
      if (job.pack_id && ["completed", "partial"].includes(job.status) && job.source_id) {
        (map[job.source_id] ??= []).push(job.pack_id);
      }
    }
    return map;
  }, [jobs]);

  const filteredSources = sources.filter(s => 
    s.title.toLowerCase().includes(searchTerm.toLowerCase()) || 
    s.filename.toLowerCase().includes(searchTerm.toLowerCase())
  );

  if (isLoading && sources.length === 0) {
    return <div className="flex items-center justify-center py-12 text-slate-500 gap-2"><Loader2 className="w-5 h-5 animate-spin" /> Loading library…</div>;
  }

  return (
    <div className="space-y-4">
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
        <input
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          placeholder="Search library…"
          className="w-full bg-white/2 border border-white/5 rounded-xl pl-10 pr-4 py-2.5 text-sm text-slate-200 focus:outline-none focus:border-cyan-500/30 transition-colors"
        />
      </div>

      <div className="glass rounded-xl border border-white/5 overflow-hidden bg-slate-950/20">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-white/5 text-slate-500 text-left bg-white/2">
              <th className="px-4 py-3 font-bold uppercase tracking-tighter">Document</th>
              <th className="px-4 py-3 font-bold uppercase tracking-tighter">Status</th>
              <th className="px-4 py-3 font-bold uppercase tracking-tighter">Results</th>
              <th className="px-4 py-3 font-bold uppercase tracking-tighter w-10" />
            </tr>
          </thead>
          <tbody className="divide-y divide-white/5">
            {filteredSources.length === 0 ? (
              <tr>
                <td colSpan={4} className="px-4 py-12 text-center text-slate-600">
                  {searchTerm ? "No documents match your search." : "Your library is empty."}
                </td>
              </tr>
            ) : (
              filteredSources.map((s) => {
                const isLocked = s.status === "processing";
                return (
                  <tr key={s.id} className={cn("transition-colors", isLocked ? "bg-amber-500/[0.02]" : "hover:bg-white/2")}>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-3">
                        <div className="w-8 h-8 rounded bg-white/5 flex items-center justify-center flex-shrink-0">
                          <FileText className="w-4 h-4 text-slate-500" />
                        </div>
                        <div className="min-w-0">
                          <div className="text-slate-200 font-medium truncate max-w-[200px]">{s.title}</div>
                          <div className="text-slate-600 text-[10px] mt-0.5">{s.filename} · {formatRelativeTime(s.uploaded_at)}</div>
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge status={s.status} />
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex flex-wrap gap-1.5">
                        {(sourcePacks[s.id] ?? []).map((pid) => (
                          <a
                            key={pid}
                            href={`/forge?pack=${pid}`}
                            className="flex items-center gap-1 px-1.5 py-0.5 rounded border border-cyan-500/20 text-cyan-400 bg-cyan-500/5 hover:bg-cyan-500/10 transition-colors text-[10px]"
                          >
                            <PackageCheck className="w-2.5 h-2.5" /> Pack
                          </a>
                        ))}
                        {s.entity_count > 0 && (
                          <span className="text-[10px] text-slate-500 flex items-center gap-1">
                            <span className="font-mono font-bold text-slate-400">{s.entity_count}</span> entities
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center justify-end gap-1">
                        <button
                          onClick={() => setConfirmDelete(s)}
                          disabled={isLocked || deleteSource.isPending}
                          className="p-1.5 rounded-lg text-slate-600 hover:text-red-400 transition-colors disabled:opacity-30"
                          title="Remove from Library"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                        <button
                          onClick={() => setRescanItem(s)}
                          disabled={isLocked || rescanSource.isPending}
                          className="p-1.5 rounded-lg text-slate-600 hover:text-cyan-400 transition-colors disabled:opacity-30"
                          title="Re-scan"
                        >
                          <RefreshCw className={cn("w-3.5 h-3.5", rescanSource.isPending && "animate-spin")} />
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {rescanItem && (
        <DialogShell
          title="Re-scan Source"
          icon={RefreshCw}
          onClose={() => setRescanItem(null)}
          maxWidthClassName="max-w-md"
          footer={
            <DialogFooter>
              <button className="btn-ghost text-xs" onClick={() => setRescanItem(null)}>Cancel</button>
              <button
                disabled={rescanSource.isPending}
                className="btn-cyber px-4 py-2 text-xs font-bold"
                onClick={() => rescanSource.mutate({
                  sourceId: rescanItem.id,
                  scanType,
                  target: ingestTarget
                })}
              >
                {rescanSource.isPending ? "Starting..." : "Start Re-scan"}
              </button>
            </DialogFooter>
          }
        >
          <div className="p-4 space-y-4">
            {errorNotice && (
              <div className="p-2 rounded bg-red-500/10 border border-red-500/20 text-[10px] text-red-300 flex items-center gap-2">
                <AlertTriangle className="w-3 h-3 shrink-0" />
                {errorNotice}
              </div>
            )}
            <p className="text-sm text-slate-400">Configure extraction for <strong className="text-slate-200">{rescanItem.title}</strong>:</p>
            
            <div className="space-y-2">
              <p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Book Type</p>
              <div className="grid grid-cols-2 gap-2">
                {SCAN_TYPES.map(({ value, label }) => (
                  <button
                    key={value}
                    onClick={() => setScanType(value)}
                    className={cn(
                      "px-2.5 py-2 rounded-lg border text-[11px] font-medium transition-all text-left",
                      scanType === value
                        ? "bg-white/8 border-white/20 text-slate-100"
                        : "border-white/5 text-slate-500 hover:text-slate-300 hover:border-white/10",
                    )}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>

            <div className="space-y-2">
              <p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Extraction Goal</p>
              <div className="flex flex-wrap gap-2">
                {INGEST_TARGETS.map((target) => (
                  <button
                    key={target.id}
                    onClick={() => setIngestTarget(target.id)}
                    className={cn(
                      "px-3 py-1.5 rounded-lg border text-[11px] font-medium transition-all",
                      ingestTarget === target.id
                        ? "bg-cyan-500/10 border-cyan-500/25 text-cyan-300"
                        : "border-white/5 text-slate-500 hover:text-slate-300 hover:border-white/10",
                    )}
                  >
                    {target.label}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </DialogShell>
      )}

      {confirmDelete && (
        <DialogShell
          title="Remove Source"
          icon={AlertTriangle}
          iconClassName="text-red-400"
          onClose={() => setConfirmDelete(null)}
          maxWidthClassName="max-w-sm"
          footer={
            <DialogFooter>
              <button className="btn-ghost text-xs" onClick={() => setConfirmDelete(null)}>Cancel</button>
              <button
                className="bg-red-500/20 text-red-300 hover:bg-red-500/30 border border-red-500/25 px-4 py-2 rounded-lg text-xs font-bold transition-colors"
                onClick={() => deleteSource.mutate(confirmDelete.id)}
              >
                Remove from Library
              </button>
            </DialogFooter>
          }
        >
          <div className="p-4 space-y-3 text-sm text-slate-400">
            <p>Are you sure you want to remove <strong className="text-slate-200">{confirmDelete.title}</strong>?</p>
            <p className="text-xs text-slate-500 italic">This will delete the original file and all associated ingestion job records.</p>
          </div>
        </DialogShell>
      )}
    </div>
  );
}
