"use client";

import { useRef, useState, useCallback, useEffect } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  FileText,
  Loader2,
  Sparkles,
  Archive,
  ChevronDown,
  Layers,
  Scroll,
  Swords,
  Wand2,
  CheckCircle2,
  X,
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { ingestApi } from "@/lib/api";
import { cn, formatBytes } from "@/lib/utils";
import { 
  SCAN_TYPES, 
  INGEST_TARGETS, 
  PROCESSING_LAYERS, 
  getLayersForTarget,
  type ScanType,
  type IngestTarget
} from "./ingest-constants";
import { FORGE_KEYS } from "@/lib/query-keys";

export function UploadCard() {
  const qc = useQueryClient();
  const inputRef = useRef<HTMLInputElement>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [dragging, setDragging] = useState(false);
  const [scanType, setScanType] = useState<ScanType>("setting_supplement");
  const [ingestTarget, setIngestTarget] = useState<IngestTarget>("everything");
  const [analysisLayers, setAnalysisLayers] = useState<string[]>(getLayersForTarget("everything", "setting_supplement"));
  const [layersExpanded, setLayersExpanded] = useState(false);
  const [uploadNotice, setUploadNotice] = useState<{ message: string; isError?: boolean } | null>(null);

  const upload = useMutation({
    mutationFn: ({ file, ingestNow }: { file: File; ingestNow: boolean }) =>
      ingestApi.uploadSource(file, {
        scan_type: scanType,
        analysis_layers: analysisLayers,
        ingest_now: ingestNow,
      }),
    onSuccess: (source, variables) => {
      qc.invalidateQueries({ queryKey: FORGE_KEYS.sources });
      qc.invalidateQueries({ queryKey: FORGE_KEYS.jobs });
      if (variables.ingestNow) {
        setUploadNotice({ message: "Scan started — check the Jobs list for progress." });
      } else {
        setUploadNotice({ message: "File saved to the Library. Re-ingest it later." });
      }
      setFiles([]);
      setTimeout(() => setUploadNotice(null), 5000);
    },
    onError: (err: any) => {
      setUploadNotice({ message: err.message || "Upload failed. Please try again.", isError: true });
    },
  });

  const applyFiles = (incoming: File[]) => {
    if (!incoming.length) return;
    // Validate client-side so bad files fail before a wasted upload + job.
    const ALLOWED = [".pdf", ".epub", ".txt", ".md", ".docx", ".html", ".htm"];
    const MAX_BYTES = 100 * 1024 * 1024; // 100MB
    const accepted: File[] = [];
    for (const f of incoming) {
      const ext = f.name.slice(f.name.lastIndexOf(".")).toLowerCase();
      if (!ALLOWED.includes(ext)) {
        setUploadNotice({ message: `Unsupported file type: ${ext || f.name}. Allowed: PDF, EPUB, TXT, MD, DOCX, HTML.`, isError: true });
        continue;
      }
      if (f.size === 0) {
        setUploadNotice({ message: `${f.name} is empty (0 bytes).`, isError: true });
        continue;
      }
      if (f.size > MAX_BYTES) {
        setUploadNotice({ message: `${f.name} is too large (${formatBytes(f.size)}). Max 100MB.`, isError: true });
        continue;
      }
      accepted.push(f);
    }
    if (accepted.length) setFiles(accepted);
  };

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    applyFiles(Array.from(e.dataTransfer.files));
  }, []);

  const hasFile = files.length > 0;

  return (
    <div className="glass rounded-2xl border border-white/5 overflow-hidden flex flex-col h-full bg-slate-950/20">
      <div className="p-4 border-b border-white/5 flex items-center justify-between bg-white/2">
        <h3 className="text-xs font-bold text-slate-100 uppercase tracking-widest flex items-center gap-2">
          <Sparkles className="w-3.5 h-3.5 text-cyan-400" />
          Ingestion Forge
        </h3>
        {hasFile && (
          <button onClick={() => setFiles([])} className="text-[10px] text-slate-500 hover:text-slate-300 flex items-center gap-1">
            <X className="w-3 h-3" /> Clear
          </button>
        )}
      </div>

      <div className="p-5 flex-1 flex flex-col space-y-5 overflow-y-auto min-h-0">
        <div className="space-y-3">
          <div className="flex items-center gap-2 px-1">
            <div className="w-4 h-4 rounded bg-cyan-500/20 text-cyan-400 flex items-center justify-center text-[9px] font-mono font-bold">1</div>
            <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Select Document</p>
          </div>
          <div
            onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDrop={handleDrop}
            onClick={() => !hasFile && inputRef.current?.click()}
            className={cn(
              "rounded-xl p-6 border-2 border-dashed text-center transition-all flex flex-col items-center justify-center min-h-[120px]",
              hasFile ? "border-cyan-500/20 bg-cyan-500/5" : dragging
                ? "border-cyan-500/60 bg-cyan-500/5 shadow-[0_0_30px_-10px_rgba(34,211,238,0.25)]"
                : "border-white/10 hover:border-cyan-500/30 hover:bg-white/2 cursor-pointer",
            )}
          >
            <input
              ref={inputRef}
              type="file"
              accept=".pdf,.epub,.txt,.md,.docx,.html,.htm"
              className="hidden"
              onChange={(e) => applyFiles(Array.from(e.target.files ?? []))}
            />
            {hasFile ? (
              <div className="space-y-1.5 w-full">
                {files.map((f) => (
                  <div key={f.name} className="flex items-center justify-center gap-2 text-sm text-cyan-300">
                    <FileText className="w-4 h-4 flex-shrink-0" />
                    <span className="truncate max-w-[200px] font-medium">{f.name}</span>
                    <span className="text-slate-600 text-xs flex-shrink-0">{formatBytes(f.size)}</span>
                  </div>
                ))}
                <p className="text-[10px] text-slate-500 mt-2">Ready to process. Configure below.</p>
              </div>
            ) : (
              <>
                <div className="w-10 h-10 rounded-lg bg-white/4 border border-white/8 flex items-center justify-center mb-2">
                  <FileText className={cn("w-5 h-5", dragging ? "text-cyan-400" : "text-slate-500")} />
                </div>
                <p className="text-xs font-medium text-slate-400">Drop a book, or browse</p>
                <p className="text-[10px] text-slate-600 mt-1 uppercase tracking-tighter">PDF · EPUB · DOCX · HTML · TXT · MD</p>
              </>
            )}
          </div>
        </div>

        <AnimatePresence>
          {hasFile && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              className="space-y-5 overflow-hidden border-t border-white/5 pt-5"
            >
              <div className="flex items-center gap-2 px-1">
                <div className="w-4 h-4 rounded bg-cyan-500/20 text-cyan-400 flex items-center justify-center text-[9px] font-mono font-bold">2</div>
                <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Configure Extraction</p>
              </div>

              <div className="space-y-2">
                <p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider opacity-60">Book Type</p>
                <div className="grid grid-cols-2 gap-2">
                  {SCAN_TYPES.map(({ value, label, icon: Icon, color }) => (
                    <button
                      key={value}
                      onClick={() => { setScanType(value); setAnalysisLayers(getLayersForTarget(ingestTarget, value)); }}
                      className={cn(
                        "flex items-center gap-2 px-2.5 py-2 rounded-lg border text-[11px] font-medium transition-all text-left",
                        scanType === value
                          ? "bg-white/8 border-white/20 text-slate-100 shadow-inner"
                          : "border-white/5 text-slate-500 hover:text-slate-300 hover:border-white/10",
                      )}
                    >
                      <Icon className={cn("w-3.5 h-3.5 shrink-0", scanType === value ? color : "text-slate-600")} />
                      <span className="truncate">{label}</span>
                    </button>
                  ))}
                </div>
              </div>

              <div className="space-y-2">
                <p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider opacity-60">Extraction Goal</p>
                <div className="flex flex-wrap gap-2">
                  {INGEST_TARGETS.map((target) => (
                    <button
                      key={target.id}
                      type="button"
                      onClick={() => { setIngestTarget(target.id); setAnalysisLayers(getLayersForTarget(target.id, scanType)); }}
                      className={cn(
                        "px-3 py-1.5 rounded-lg border text-[11px] font-medium transition-all",
                        ingestTarget === target.id
                          ? "bg-cyan-500/10 border-cyan-500/25 text-cyan-300 shadow-inner"
                          : "border-white/5 text-slate-500 hover:text-slate-300 hover:border-white/10",
                      )}
                    >
                      {target.label}
                    </button>
                  ))}
                </div>
              </div>

              <div className="space-y-2">
                <button
                  type="button"
                  onClick={() => setLayersExpanded((e) => !e)}
                  className="flex items-center gap-1.5 text-[10px] font-bold text-slate-500 uppercase tracking-wider hover:text-slate-300 transition-colors"
                >
                  <ChevronDown className={cn("w-3 h-3 transition-transform", layersExpanded && "rotate-[-90deg]")} />
                  Advanced Layers
                </button>
                <AnimatePresence initial={false}>
                  {layersExpanded && (
                    <motion.div
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: "auto", opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      className="overflow-hidden"
                    >
                      <div className="grid grid-cols-2 gap-2 pb-1">
                        {PROCESSING_LAYERS.map((layer) => {
                          const active = analysisLayers.includes(layer.id);
                          return (
                            <button
                              key={layer.id}
                              type="button"
                              onClick={() =>
                                setAnalysisLayers((prev) =>
                                  prev.includes(layer.id) ? prev.filter((v) => v !== layer.id) : [...prev, layer.id],
                                )
                              }
                              className={cn(
                                "px-2 py-1.5 rounded-lg border text-[10px] font-medium transition-all text-left",
                                active
                                  ? "bg-cyan-500/10 border-cyan-500/25 text-cyan-300"
                                  : "border-white/5 text-slate-500 hover:text-slate-300 hover:border-white/10",
                              )}
                            >
                              {layer.label}
                            </button>
                          );
                        })}
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        <AnimatePresence>
          {uploadNotice && (
            <motion.div
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              className={cn(
                "rounded-lg border px-3 py-2 text-[11px] flex items-center gap-2",
                uploadNotice.isError 
                  ? "border-red-500/20 bg-red-500/5 text-red-300" 
                  : "border-emerald-500/20 bg-emerald-500/5 text-emerald-300"
              )}
            >
              {uploadNotice.isError ? <X className="w-3.5 h-3.5 shrink-0" /> : <CheckCircle2 className="w-3.5 h-3.5 shrink-0" />}
              {uploadNotice.message}
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      <div className="p-4 bg-white/2 border-t border-white/5 flex gap-2">
        <button
          disabled={!hasFile || upload.isPending}
          onClick={() => upload.mutate({ file: files[0], ingestNow: true })}
          className="flex-1 btn-cyber py-2.5 text-xs font-bold justify-center disabled:opacity-40"
        >
          {upload.isPending ? (
            <><Loader2 className="w-3.5 h-3.5 animate-spin mr-2" /> Ingesting…</>
          ) : (
            <>
              <div className="w-4 h-4 rounded bg-white/20 text-white flex items-center justify-center text-[9px] font-mono font-bold mr-2">3</div>
              <Sparkles className="w-3.5 h-3.5 mr-2" /> Start Scan
            </>
          )}
        </button>
        <button
          disabled={!hasFile || upload.isPending}
          onClick={() => upload.mutate({ file: files[0], ingestNow: false })}
          title="Save file to library without scanning"
          className="w-12 btn-ghost justify-center py-2.5 disabled:opacity-40"
        >
          <Archive className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}
