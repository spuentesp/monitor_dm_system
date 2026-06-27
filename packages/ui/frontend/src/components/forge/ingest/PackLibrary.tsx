"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  PackageCheck,
  Loader2,
  Trash2,
  Archive,
  BookOpen,
  Sparkles,
  Globe,
  Plus,
  ChevronDown,
  ChevronUp,
  Users,
  Search,
  AlertTriangle,
  CheckSquare,
  Square,
  GitMerge,
  Download,
  Upload,
  Copy,
  Scissors,
  X,
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { ingestApi, universesApi } from "@/lib/api";
import type { KnowledgePack, Multiverse, Universe } from "@/lib/types";
import { cn, formatRelativeTime } from "@/lib/utils";
import { StatusBadge } from "./StatusBadge";
import { DialogFooter, DialogShell } from "@/components/DialogShell";
import { FORGE_KEYS, UNIVERSE_KEYS } from "@/lib/query-keys";
import { errorMessage } from "@/lib/errors";

export function PackLibrary({ onOpenPack }: { onOpenPack?: (packId: string) => void }) {
  const qc = useQueryClient();
  const [searchTerm, setSearchTerm] = useState("");
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [applyingId, setApplyingId] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<{ pack: KnowledgePack; hard: boolean } | null>(null);
  const [confirmCanonize, setConfirmCanonize] = useState<{ 
    pack: KnowledgePack; 
    mvId: string; 
    uniId: string; 
    newName?: string;
    newSystem?: string;
  } | null>(null);
  
  const [newWorldName, setNewWorldName] = useState<Record<string, string>>({});
  const [newWorldSystem, setNewWorldSystem] = useState<Record<string, string>>({});
  const [targetMvId, setTargetMvId] = useState<Record<string, string>>({});
  const [targetUniId, setTargetUniId] = useState<Record<string, string>>({});
  const [applyError, setApplyError] = useState<string | null>(null);
  const [applySuccess, setApplySuccess] = useState<string | null>(null);

  const { data: packs = [], isLoading } = useQuery<KnowledgePack[]>({
    queryKey: FORGE_KEYS.packs,
    queryFn: () => ingestApi.listPacks(),
    refetchInterval: (query) => {
      // Poll faster if any pack is canonizing
      const anyCanonizing = query.state.data?.some(p => p.status === "canonizing");
      return anyCanonizing ? 2000 : 10000;
    },
  });

  const { data: multiverses = [] } = useQuery<Multiverse[]>({
    queryKey: UNIVERSE_KEYS.multiverses,
    queryFn: universesApi.listMultiverses,
  });

  // Fetch universes for the currently selected multiverse of the applying pack
  const activeMvId = applyingId ? targetMvId[applyingId] : undefined;
  const { data: universes = [] } = useQuery<Universe[]>({
    queryKey: UNIVERSE_KEYS.universes(activeMvId),
    queryFn: () => universesApi.listUniverses(activeMvId),
    enabled: !!activeMvId,
  });

  const canonize = useMutation({
    mutationFn: (payload: { packId: string; mvId?: string; uniId?: string; newName?: string; newSystem?: string }) =>
      ingestApi.canonizePack(payload.packId, {
        multiverse_id: payload.mvId,
        universe_id: payload.uniId === "NEW" ? undefined : payload.uniId,
        new_setting_name: payload.uniId === "NEW" ? payload.newName : undefined,
        new_setting_system: payload.uniId === "NEW" ? payload.newSystem : undefined,
      }),
    onSuccess: (data, variables) => {
      qc.invalidateQueries({ queryKey: FORGE_KEYS.packs });
      setApplyingId(null);
      setConfirmCanonize(null);
      setApplySuccess(`Successfully applied to ${variables.newName || "universe"}.`);
      setApplyError(null);
      
      // Clear success message after 5s
      setTimeout(() => setApplySuccess(null), 5000);
    },
    onError: (err: any) => {
      setApplyError(err.message || "Failed to apply pack.");
    }
  });

  const deletePack = useMutation({
    mutationFn: ({ id, hard }: { id: string; hard: boolean }) =>
      ingestApi.deletePack(id, hard),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["forge-packs"] });
      setConfirmDelete(null);
    },
  });

  // ── Batch pack operations (T-061) ─────────────────────────────────────
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [opError, setOpError] = useState<string | null>(null);
  const [sliceFor, setSliceFor] = useState<KnowledgePack | null>(null);

  const toggleSelected = (id: string) =>
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  const clearSelection = () => setSelectedIds(new Set());

  const refreshPacks = () => qc.invalidateQueries({ queryKey: FORGE_KEYS.packs });

  const mergeMut = useMutation({
    mutationFn: (ids: string[]) => ingestApi.mergePacks({ pack_ids: ids }),
    onSuccess: () => { refreshPacks(); clearSelection(); },
    onError: (e: unknown) => setOpError(errorMessage(e) ?? "Merge failed."),
  });

  const cloneMut = useMutation({
    mutationFn: (id: string) => ingestApi.clonePack(id, { with_lineage: true }),
    onSuccess: () => { refreshPacks(); clearSelection(); },
    onError: (e: unknown) => setOpError(errorMessage(e) ?? "Clone failed."),
  });

  const importMut = useMutation({
    mutationFn: (envelope: { schema_version: string; exported_at: string; pack: object }) =>
      ingestApi.importPack(envelope),
    onSuccess: () => refreshPacks(),
    onError: (e: unknown) => setOpError(errorMessage(e) ?? "Import failed."),
  });

  const sliceMut = useMutation({
    mutationFn: (body: { id: string; name: string; entity_indices: number[]; axiom_indices: number[]; lore_indices: number[] }) =>
      ingestApi.slicePack(body.id, {
        name: body.name,
        entity_indices: body.entity_indices,
        axiom_indices: body.axiom_indices,
        lore_indices: body.lore_indices,
        with_lineage: true,
      }),
    onSuccess: () => { refreshPacks(); setSliceFor(null); },
    onError: (e: unknown) => setOpError(errorMessage(e) ?? "Slice failed."),
  });

  const exportSelected = async () => {
    setOpError(null);
    for (const id of selectedIds) {
      try {
        const blob = await ingestApi.exportPack(id);
        const pack = packs.find((p) => p.id === id);
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `${(pack?.name ?? id).replace(/[^\w.-]+/g, "_")}.pack.json`;
        a.click();
        URL.revokeObjectURL(url);
      } catch (e) {
        setOpError(errorMessage(e) ?? `Export failed for ${id}.`);
      }
    }
  };

  const onImportFile = async (file: File) => {
    setOpError(null);
    try {
      const envelope = JSON.parse(await file.text());
      if (!envelope?.pack) throw new Error("Not a pack export (missing 'pack').");
      importMut.mutate(envelope);
    } catch (e) {
      setOpError(errorMessage(e) ?? "Could not read pack file.");
    }
  };

  const filteredPacks = packs.filter(p =>
    p.name.toLowerCase().includes(searchTerm.toLowerCase()) || 
    (p.system_name ?? "").toLowerCase().includes(searchTerm.toLowerCase())
  );

  if (isLoading && packs.length === 0) {
    return <div className="flex items-center justify-center py-12 text-slate-500 gap-2"><Loader2 className="w-5 h-5 animate-spin" /> Loading packs…</div>;
  }

  if (packs.length === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-white/5 p-12 text-center text-slate-600">
        <PackageCheck className="w-8 h-8 mx-auto mb-3 opacity-20" />
        <p className="text-xs">No knowledge packs yet. Ingest a source to generate one.</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {applySuccess && (
        <motion.div 
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          className="p-3 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-xs text-emerald-400 flex items-center gap-2"
        >
          <PackageCheck className="w-4 h-4" />
          {applySuccess}
        </motion.div>
      )}
      {applyError && (
        <motion.div 
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          className="p-3 rounded-xl bg-red-500/10 border border-red-500/20 text-xs text-red-400 flex items-center gap-2"
        >
          <AlertTriangle className="w-4 h-4" />
          {applyError}
        </motion.div>
      )}

      {opError && (
        <div className="p-3 rounded-xl bg-red-500/10 border border-red-500/20 text-xs text-red-400 flex items-center justify-between gap-2">
          <span className="flex items-center gap-2"><AlertTriangle className="w-4 h-4" /> {opError}</span>
          <button onClick={() => setOpError(null)} className="text-red-300 hover:text-red-200"><X className="w-3.5 h-3.5" /></button>
        </div>
      )}

      <div className="flex items-center gap-2">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
          <input
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder="Search packs…"
            className="w-full bg-white/2 border border-white/5 rounded-xl pl-10 pr-4 py-2 text-sm text-slate-200 focus:outline-none focus:border-cyan-500/30"
          />
        </div>
        <label className="btn-ghost text-xs gap-1.5 cursor-pointer whitespace-nowrap" title="Import a pack from a .pack.json export">
          {importMut.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Upload className="w-3.5 h-3.5" />}
          Import
          <input
            type="file"
            accept="application/json,.json"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) onImportFile(f);
              e.target.value = "";
            }}
          />
        </label>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {filteredPacks.map((pack) => {
          const isExpanded = expandedId === pack.id;
          const isApplying = applyingId === pack.id;
          const isLocked = pack.status === "draft";

          return (
            <motion.div
              key={pack.id}
              layout
              className={cn(
                "glass rounded-xl border border-white/5 flex flex-col transition-all",
                isLocked ? "opacity-60 bg-amber-500/[0.02]" : "hover:border-white/10"
              )}
            >
              <div className="p-4 space-y-3">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex items-start gap-2 min-w-0">
                    <button
                      onClick={() => toggleSelected(pack.id)}
                      className={cn(
                        "mt-0.5 transition-colors",
                        selectedIds.has(pack.id) ? "text-cyan-400" : "text-slate-600 hover:text-slate-400"
                      )}
                      title={selectedIds.has(pack.id) ? "Deselect" : "Select for batch ops"}
                    >
                      {selectedIds.has(pack.id) ? <CheckSquare className="w-4 h-4" /> : <Square className="w-4 h-4" />}
                    </button>
                    <div className="min-w-0">
                      <h4 className="text-sm font-bold text-slate-200 truncate">{pack.name}</h4>
                      <p className="text-[10px] text-slate-600 mt-0.5 uppercase tracking-tighter">
                        {pack.pack_type} {pack.system_name && <>· <span className="text-emerald-500/70">{pack.system_name}</span></>}
                      </p>
                    </div>
                  </div>
                  <StatusBadge status={pack.status} />
                </div>

                <div className="grid grid-cols-3 gap-2 py-1">
                  {[
                    ["Axioms", pack.axiom_count, "text-cyan-400"],
                    ["Entities", pack.entity_count, "text-purple-400"],
                    ["Lore", pack.lore_fact_count, "text-amber-400"],
                  ].map(([l, v, c]) => (
                    <div key={l} className="text-center">
                      <p className={cn("text-xs font-mono font-bold", c)}>{v}</p>
                      <p className="text-[8px] text-slate-600 uppercase font-bold tracking-tighter">{l}</p>
                    </div>
                  ))}
                </div>

                <div className="flex items-center gap-2 pt-2 border-t border-white/5">
                  <button
                    onClick={() => onOpenPack?.(pack.id)}
                    disabled={isLocked}
                    className="flex-1 btn-cyber py-1.5 text-[10px] font-bold justify-center"
                  >
                    <BookOpen className="w-3 h-3 mr-1.5" /> Editor
                  </button>
                  {!isLocked && (pack.status === "ready" || pack.status === "canonizing") && (
                    <button
                      onClick={() => {
                        setApplyingId(isApplying ? null : pack.id);
                        setApplyError(null);
                        setApplySuccess(null);
                      }}
                      disabled={pack.status === "canonizing"}
                      className={cn(
                        "flex-1 btn-cyber py-1.5 text-[10px] font-bold justify-center",
                        pack.status === "canonizing" 
                          ? "opacity-50 cursor-not-allowed"
                          : "bg-emerald-500/10 border-emerald-500/20 text-emerald-400 hover:bg-emerald-500/20"
                      )}
                    >
                      <Sparkles className="w-3 h-3 mr-1.5" /> 
                      {pack.status === "canonizing" ? "Canonizing..." : "Apply"}
                    </button>
                  )}
                  <button
                    onClick={() => setExpandedId(isExpanded ? null : pack.id)}
                    className="p-1.5 rounded-lg hover:bg-white/5 text-slate-500 transition-colors"
                  >
                    {isExpanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                  </button>
                </div>
              </div>

              <AnimatePresence>
                {isExpanded && (
                  <motion.div
                    initial={{ height: 0 }}
                    animate={{ height: "auto" }}
                    exit={{ height: 0 }}
                    className="overflow-hidden border-t border-white/5 bg-black/20"
                  >
                    <div className="p-3 space-y-3">
                      <div className="space-y-1">
                        <p className="text-[9px] font-bold text-slate-500 uppercase tracking-widest">Recent Axioms</p>
                        {pack.axioms.slice(0, 2).map((a, i) => (
                          <div key={i} className="text-[10px] text-slate-400 flex gap-2">
                            <span className="text-cyan-500">•</span>
                            <span className="truncate italic">{a.statement}</span>
                          </div>
                        ))}
                      </div>
                      <div className="flex items-center justify-between text-[10px] text-slate-600">
                        <span>Created {formatRelativeTime(pack.created_at)}</span>
                        <div className="flex gap-2">
                          <button
                            onClick={() => setConfirmDelete({ pack, hard: false })}
                            className="hover:text-red-400 transition-colors"
                          >
                            Archive
                          </button>
                        </div>
                      </div>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>

              <AnimatePresence>
                {isApplying && (
                  <motion.div
                    initial={{ height: 0 }}
                    animate={{ height: "auto" }}
                    exit={{ height: 0 }}
                    className="overflow-hidden border-t border-white/5 bg-emerald-500/[0.02]"
                  >
                    <div className="p-4 space-y-4">
                      <div className="space-y-4">
                        <div className="flex items-center justify-between">
                          <p className="text-[10px] font-bold text-emerald-400 uppercase tracking-widest flex items-center gap-2">
                            <Globe className="w-3 h-3" /> Apply to Multiverse
                          </p>
                        </div>
                        
                        <div className="space-y-3">
                          <div className="space-y-1.5">
                            <label className="text-[9px] text-slate-500 uppercase font-bold tracking-wider">Step 1: Select Multiverse</label>
                            <select
                              value={targetMvId[pack.id] ?? ""}
                              onChange={(e) => {
                                setTargetMvId({ ...targetMvId, [pack.id]: e.target.value });
                                setTargetUniId({ ...targetUniId, [pack.id]: "" });
                              }}
                              className="w-full bg-slate-900 border border-white/10 rounded-lg px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-emerald-500/30"
                            >
                              <option value="">— Select Multiverse —</option>
                              {multiverses.map(mv => <option key={mv.id} value={mv.id}>{mv.name}</option>)}
                            </select>
                          </div>

                          {targetMvId[pack.id] && (
                            <motion.div 
                              initial={{ opacity: 0, y: -10 }}
                              animate={{ opacity: 1, y: 0 }}
                              className="space-y-3"
                            >
                              <div className="space-y-1.5">
                                <label className="text-[9px] text-slate-500 uppercase font-bold tracking-wider">Step 2: Choose Target Universe</label>
                                <select
                                  value={targetUniId[pack.id] ?? ""}
                                  onChange={(e) => setTargetUniId({ ...targetUniId, [pack.id]: e.target.value })}
                                  className="w-full bg-slate-900 border border-white/10 rounded-lg px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-emerald-500/30"
                                >
                                  <option value="">— Select Universe —</option>
                                  {universes.map(uni => <option key={uni.id} value={uni.id}>{uni.name}</option>)}
                                  <option value="NEW">+ Create New World in Multiverse</option>
                                </select>
                              </div>

                              {targetUniId[pack.id] === "NEW" && (
                                <motion.div
                                  initial={{ opacity: 0, x: -10 }}
                                  animate={{ opacity: 1, x: 0 }}
                                  className="space-y-3 p-3 rounded-lg bg-black/40 border border-white/5"
                                >
                                  <div className="space-y-1.5">
                                    <label className="text-[9px] text-slate-500 uppercase font-bold tracking-wider">New World Name</label>
                                    <input
                                      value={newWorldName[pack.id] ?? ""}
                                      onChange={(e) => setNewWorldName({ ...newWorldName, [pack.id]: e.target.value })}
                                      placeholder="Enter unique name..."
                                      className="input-cyber w-full text-xs"
                                      autoFocus
                                    />
                                  </div>
                                  <div className="space-y-1.5">
                                    <label className="text-[9px] text-slate-500 uppercase font-bold tracking-wider">Game System</label>
                                    <input
                                      value={newWorldSystem[pack.id] ?? pack.system_name ?? ""}
                                      onChange={(e) => setNewWorldSystem({ ...newWorldSystem, [pack.id]: e.target.value })}
                                      placeholder="e.g. D&D 5e, Cyberpunk RED..."
                                      className="input-cyber w-full text-xs"
                                    />
                                  </div>
                                </motion.div>
                              )}
                            </motion.div>
                          )}
                        </div>
                      </div>

                      <div className="flex gap-2 pt-2">
                        <button
                          disabled={
                            !targetMvId[pack.id] || 
                            !targetUniId[pack.id] || 
                            (targetUniId[pack.id] === "NEW" && !newWorldName[pack.id])
                          }
                          onClick={() => {
                            const uniId = targetUniId[pack.id];
                            const universe = universes.find(u => u.id === uniId);
                            setConfirmCanonize({
                              pack,
                              mvId: targetMvId[pack.id],
                              uniId: uniId, // Pass "NEW" or actual uniId. Fixes TS error and flow logic.
                              newName: uniId === "NEW" ? newWorldName[pack.id] : universe?.name,
                              newSystem: uniId === "NEW" ? (newWorldSystem[pack.id] ?? pack.system_name ?? "") : undefined
                            });
                          }}
                          className="flex-1 btn-cyber py-2 text-xs font-bold justify-center border-emerald-500/30 text-emerald-400 disabled:opacity-30 disabled:grayscale"
                        >
                          <PackageCheck className="w-3.5 h-3.5 mr-2" />
                          Review & Apply
                        </button>
                        <button
                          onClick={() => setApplyingId(null)}
                          className="px-4 btn-ghost text-xs"
                        >
                          Cancel
                        </button>
                      </div>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </motion.div>
          );
        })}
      </div>

      {confirmDelete && (
        <DialogShell
          title={confirmDelete.hard ? "Permanently Delete Pack" : "Archive Pack"}
          icon={confirmDelete.hard ? Trash2 : Archive}
          iconClassName={confirmDelete.hard ? "text-red-400" : "text-amber-400"}
          onClose={() => setConfirmDelete(null)}
          maxWidthClassName="max-w-sm"
          footer={
            <DialogFooter>
              <button className="btn-ghost text-xs" onClick={() => setConfirmDelete(null)}>Cancel</button>
              <button
                className={cn(
                  "px-4 py-2 rounded-lg text-xs font-bold transition-colors",
                  confirmDelete.hard
                    ? "bg-red-500/20 text-red-300 hover:bg-red-500/30 border border-red-500/25"
                    : "bg-amber-500/20 text-amber-300 hover:bg-amber-500/30 border border-amber-500/25",
                )}
                onClick={() => deletePack.mutate({ id: confirmDelete.pack.id, hard: confirmDelete.hard })}
              >
                {confirmDelete.hard ? "Delete Permanently" : "Archive"}
              </button>
            </DialogFooter>
          }
        >
          <div className="p-4 space-y-3 text-sm text-slate-400">
            <p>
              {confirmDelete.hard
                ? <>Are you sure you want to permanently delete <strong className="text-slate-200">{confirmDelete.pack.name}</strong>? This cannot be undone.</>
                : <>Archive <strong className="text-slate-200">{confirmDelete.pack.name}</strong>? It will be hidden from the library.</>
              }
            </p>
          </div>
        </DialogShell>
      )}

      {confirmCanonize && (
        <DialogShell
          title="Apply Knowledge Pack"
          icon={Sparkles}
          iconClassName="text-emerald-400"
          onClose={() => setConfirmCanonize(null)}
          maxWidthClassName="max-w-md"
          footer={
            <DialogFooter>
              <button className="btn-ghost text-xs" onClick={() => setConfirmCanonize(null)}>Cancel</button>
              <button
                disabled={canonize.isPending}
                className="bg-emerald-500/20 text-emerald-300 hover:bg-emerald-500/30 border border-emerald-500/25 px-4 py-2 rounded-lg text-xs font-bold transition-all flex items-center gap-2"
                onClick={() => canonize.mutate({
                  packId: confirmCanonize.pack.id,
                  mvId: confirmCanonize.mvId,
                  uniId: confirmCanonize.uniId,
                  newName: confirmCanonize.newName,
                  newSystem: confirmCanonize.newSystem
                })}
              >
                {canonize.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <PackageCheck className="w-3.5 h-3.5" />}
                Confirm & Commit
              </button>
            </DialogFooter>
          }
        >
          <div className="p-4 space-y-4 text-sm text-slate-400">
            <p>
              You are about to apply <strong className="text-slate-200">{confirmCanonize.pack.name}</strong> to:
            </p>
            <div className="bg-white/5 rounded-xl p-4 border border-white/5 space-y-2">
              <div className="flex justify-between items-center">
                <span className="text-[10px] uppercase font-bold text-slate-500">Multiverse</span>
                <span className="text-slate-200">{multiverses.find(m => m.id === confirmCanonize.mvId)?.name}</span>
              </div>
              <div className="flex justify-between items-center border-t border-white/5 pt-2">
                <span className="text-[10px] uppercase font-bold text-slate-500">Universe</span>
                <span className="text-emerald-400">{confirmCanonize.newName} {confirmCanonize.uniId === "NEW" ? "(New)" : ""}</span>
              </div>
              {confirmCanonize.newSystem && (
                <div className="flex justify-between items-center border-t border-white/5 pt-2">
                  <span className="text-[10px] uppercase font-bold text-slate-500">System</span>
                  <span className="text-slate-200">{confirmCanonize.newSystem}</span>
                </div>
              )}
            </div>
            <p className="text-xs italic text-slate-500">
              This will commit {confirmCanonize.pack.entity_count} entities and {confirmCanonize.pack.lore_fact_count} lore facts to the world graph.
            </p>
          </div>
        </DialogShell>
      )}

      {/* Floating batch action bar (T-061) */}
      <AnimatePresence>
        {selectedIds.size > 0 && (
          <motion.div
            initial={{ opacity: 0, y: 40 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 40 }}
            className="fixed bottom-6 left-1/2 -translate-x-1/2 z-40 flex items-center gap-2 glass rounded-2xl border border-white/10 bg-slate-900/90 px-4 py-2.5 shadow-2xl"
          >
            <span className="text-xs font-bold text-cyan-400 mr-1">{selectedIds.size} selected</span>
            <button
              onClick={() => mergeMut.mutate([...selectedIds])}
              disabled={selectedIds.size < 2 || mergeMut.isPending}
              className="btn-ghost text-xs gap-1.5 disabled:opacity-30"
              title={selectedIds.size < 2 ? "Select 2+ packs to merge" : "Merge selected packs"}
            >
              {mergeMut.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <GitMerge className="w-3.5 h-3.5" />} Merge
            </button>
            <button onClick={exportSelected} className="btn-ghost text-xs gap-1.5" title="Export selected packs to JSON">
              <Download className="w-3.5 h-3.5" /> Export
            </button>
            <button
              onClick={() => cloneMut.mutate([...selectedIds][0])}
              disabled={selectedIds.size !== 1 || cloneMut.isPending}
              className="btn-ghost text-xs gap-1.5 disabled:opacity-30"
              title={selectedIds.size !== 1 ? "Select exactly 1 pack to clone" : "Clone pack"}
            >
              {cloneMut.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Copy className="w-3.5 h-3.5" />} Clone
            </button>
            <button
              onClick={() => setSliceFor(packs.find((p) => p.id === [...selectedIds][0]) ?? null)}
              disabled={selectedIds.size !== 1}
              className="btn-ghost text-xs gap-1.5 disabled:opacity-30"
              title={selectedIds.size !== 1 ? "Select exactly 1 pack to slice" : "Slice a subset into a new pack"}
            >
              <Scissors className="w-3.5 h-3.5" /> Slice
            </button>
            <div className="w-px h-5 bg-white/10" />
            <button onClick={clearSelection} className="btn-ghost text-xs gap-1.5" title="Clear selection">
              <X className="w-3.5 h-3.5" /> Clear
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      {sliceFor && (
        <SliceDialog
          pack={sliceFor}
          pending={sliceMut.isPending}
          onClose={() => setSliceFor(null)}
          onSlice={(name, entity_indices, axiom_indices, lore_indices) =>
            sliceMut.mutate({ id: sliceFor.id, name, entity_indices, axiom_indices, lore_indices })
          }
        />
      )}
    </div>
  );
}

function SliceDialog({
  pack,
  pending,
  onClose,
  onSlice,
}: {
  pack: KnowledgePack;
  pending: boolean;
  onClose: () => void;
  onSlice: (name: string, entityIdx: number[], axiomIdx: number[], loreIdx: number[]) => void;
}) {
  const [name, setName] = useState(`${pack.name} (slice)`);
  const [entityIdx, setEntityIdx] = useState<Set<number>>(new Set());
  const [axiomIdx, setAxiomIdx] = useState<Set<number>>(new Set());
  const [loreIdx, setLoreIdx] = useState<Set<number>>(new Set());

  const toggle = (set: Set<number>, setter: (s: Set<number>) => void, i: number) => {
    const next = new Set(set);
    if (next.has(i)) next.delete(i); else next.add(i);
    setter(next);
  };
  const total = entityIdx.size + axiomIdx.size + loreIdx.size;

  const Section = ({
    label, items, set, setter, color,
  }: { label: string; items: string[]; set: Set<number>; setter: (s: Set<number>) => void; color: string }) => (
    <div className="space-y-1.5">
      <p className="text-[9px] font-bold text-slate-500 uppercase tracking-widest">{label} ({set.size}/{items.length})</p>
      <div className="max-h-32 overflow-y-auto space-y-1 pr-1">
        {items.length === 0 && <p className="text-[10px] text-slate-600 italic">none</p>}
        {items.map((txt, i) => (
          <button
            key={i}
            onClick={() => toggle(set, setter, i)}
            className="w-full flex items-start gap-2 text-left text-[10px] hover:bg-white/5 rounded px-1.5 py-1"
          >
            {set.has(i) ? <CheckSquare className={cn("w-3 h-3 mt-0.5 flex-shrink-0", color)} /> : <Square className="w-3 h-3 mt-0.5 flex-shrink-0 text-slate-600" />}
            <span className="text-slate-300 truncate">{txt}</span>
          </button>
        ))}
      </div>
    </div>
  );

  return (
    <DialogShell
      title="Slice Pack"
      icon={Scissors}
      iconClassName="text-cyan-400"
      onClose={onClose}
      maxWidthClassName="max-w-lg"
      footer={
        <DialogFooter>
          <button className="btn-ghost text-xs" onClick={onClose}>Cancel</button>
          <button
            disabled={pending || total === 0 || !name.trim()}
            className="bg-cyan-500/20 text-cyan-300 hover:bg-cyan-500/30 border border-cyan-500/25 px-4 py-2 rounded-lg text-xs font-bold transition-all flex items-center gap-2 disabled:opacity-30"
            onClick={() => onSlice(name.trim(), [...entityIdx], [...axiomIdx], [...loreIdx])}
          >
            {pending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Scissors className="w-3.5 h-3.5" />}
            Slice {total} item{total === 1 ? "" : "s"}
          </button>
        </DialogFooter>
      }
    >
      <div className="p-4 space-y-4">
        <div className="space-y-1.5">
          <label className="text-[9px] text-slate-500 uppercase font-bold tracking-wider">New Pack Name</label>
          <input value={name} onChange={(e) => setName(e.target.value)} className="input-cyber w-full text-xs" />
        </div>
        <Section label="Entities" color="text-purple-400" set={entityIdx} setter={setEntityIdx}
          items={pack.entity_archetypes.map((e) => e.name || "(unnamed)")} />
        <Section label="Axioms" color="text-cyan-400" set={axiomIdx} setter={setAxiomIdx}
          items={pack.axioms.map((a) => a.statement)} />
        <Section label="Lore Facts" color="text-amber-400" set={loreIdx} setter={setLoreIdx}
          items={pack.lore_facts.map((l) => l.statement || "(fact)")} />
      </div>
    </DialogShell>
  );
}
