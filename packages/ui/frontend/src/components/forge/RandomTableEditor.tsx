"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Dice5,
  Loader2,
  Plus,
  RefreshCw,
  Search,
  Trash2,
  X,
  ChevronDown,
  Save,
} from "lucide-react";
import { randomTablesApi } from "@/lib/api";
import type { RandomTable, RandomTableEntry, RandomTableType } from "@/lib/types";
import { cn } from "@/lib/utils";

// ═══════════════════════════════════════════════════════════════
//  Table type badge config
// ═══════════════════════════════════════════════════════════════

const TABLE_TYPE_CONFIG: Record<string, { label: string; icon: string; color: string; bg: string; border: string }> = {
  encounter: { label: "Encounter", icon: "⚔️", color: "text-red-300", bg: "bg-red-500/10", border: "border-red-500/20" },
  loot: { label: "Loot", icon: "💎", color: "text-amber-300", bg: "bg-amber-500/10", border: "border-amber-500/20" },
  name: { label: "Name", icon: "📛", color: "text-cyan-300", bg: "bg-cyan-500/10", border: "border-cyan-500/20" },
  trait: { label: "Trait", icon: "🎭", color: "text-purple-300", bg: "bg-purple-500/10", border: "border-purple-500/20" },
  weather: { label: "Weather", icon: "🌤️", color: "text-blue-300", bg: "bg-blue-500/10", border: "border-blue-500/20" },
  rumor: { label: "Rumor", icon: "🗣️", color: "text-emerald-300", bg: "bg-emerald-500/10", border: "border-emerald-500/20" },
  npc: { label: "NPC", icon: "👤", color: "text-cyan-300", bg: "bg-cyan-500/10", border: "border-cyan-500/20" },
  event: { label: "Event", icon: "⚡", color: "text-amber-300", bg: "bg-amber-500/10", border: "border-amber-500/20" },
  location: { label: "Location", icon: "📍", color: "text-emerald-300", bg: "bg-emerald-500/10", border: "border-emerald-500/20" },
  complication: { label: "Complication", icon: "⚠️", color: "text-orange-300", bg: "bg-orange-500/10", border: "border-orange-500/20" },
  custom: { label: "Custom", icon: "🔧", color: "text-slate-300", bg: "bg-slate-500/10", border: "border-slate-500/20" },
};

function getTableTypeConfig(type: string) {
  return TABLE_TYPE_CONFIG[type] ?? TABLE_TYPE_CONFIG.custom;
}

// ═══════════════════════════════════════════════════════════════
//  Entry Row (editable)
// ═══════════════════════════════════════════════════════════════

function EntryRow({
  entry,
  index,
  onChange,
  onRemove,
}: {
  entry: RandomTableEntry;
  index: number;
  onChange: (index: number, entry: RandomTableEntry) => void;
  onRemove: (index: number) => void;
}) {
  return (
    <div className="flex items-center gap-2 group">
      <div className="flex items-center gap-1 flex-shrink-0">
        <input
          type="number"
          value={entry.min_roll}
          onChange={(e) => onChange(index, { ...entry, min_roll: parseInt(e.target.value, 10) || 1 })}
          className="input-cyber py-0.5 text-[10px] w-10 text-center"
          min={1}
        />
        <span className="text-[10px] text-slate-600">–</span>
        <input
          type="number"
          value={entry.max_roll}
          onChange={(e) => onChange(index, { ...entry, max_roll: parseInt(e.target.value, 10) || 1 })}
          className="input-cyber py-0.5 text-[10px] w-10 text-center"
          min={1}
        />
      </div>
      <input
        value={entry.value}
        onChange={(e) => onChange(index, { ...entry, value: e.target.value })}
        className="input-cyber py-0.5 text-xs flex-1"
        placeholder="Result text..."
      />
      <button
        onClick={() => onRemove(index)}
        className="text-slate-700 hover:text-red-400 transition-colors opacity-0 group-hover:opacity-100"
      >
        <X className="w-3 h-3" />
      </button>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
//  Table Detail / Editor
// ═══════════════════════════════════════════════════════════════

function TableEditor({
  table,
  onClose,
}: {
  table: RandomTable;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [entries, setEntries] = useState<RandomTableEntry[]>(table.entries);
  const [name, setName] = useState(table.name);
  const [rollResult, setRollResult] = useState<any>(null);

  const updateMutation = useMutation({
    mutationFn: () =>
      randomTablesApi.update(table.table_id, {
        name,
        entries: entries.map((e) => ({
          min_roll: e.min_roll,
          max_roll: e.max_roll,
          value: e.value,
          weight: e.weight,
          subtable_id: e.subtable_id,
        })),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["random-tables"] });
    },
  });

  const rollMutation = useMutation({
    mutationFn: () => randomTablesApi.roll(table.table_id),
    onSuccess: (data) => setRollResult(data),
  });

  const handleEntryChange = (index: number, entry: RandomTableEntry) => {
    setEntries((prev) => {
      const next = [...prev];
      next[index] = entry;
      return next;
    });
  };

  const handleEntryRemove = (index: number) => {
    setEntries((prev) => prev.filter((_, i) => i !== index));
  };

  const handleAddEntry = () => {
    const maxRoll = entries.length > 0 ? Math.max(...entries.map((e) => e.max_roll)) : 0;
    setEntries((prev) => [
      ...prev,
      { min_roll: maxRoll + 1, max_roll: maxRoll + 1, value: "", weight: null, subtable_id: null, conditions: null },
    ]);
  };

  const config = getTableTypeConfig(table.table_type);

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-white/5 flex-shrink-0">
        <div className="flex items-center gap-2">
          <span className="text-lg">{config.icon}</span>
          <div>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="text-sm font-semibold text-slate-200 bg-transparent border-none focus:outline-none focus:border-b focus:border-cyan-500/30 w-48"
            />
            <div className="flex items-center gap-2 mt-0.5">
              <span className={cn("text-[10px] px-1.5 py-0.5 rounded border", config.color, config.bg, config.border)}>
                {config.label}
              </span>
              <span className="text-[10px] text-slate-600 font-mono">{table.dice_formula}</span>
              {table.weighted && <span className="text-[10px] text-amber-500">Weighted</span>}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-1.5">
          <button
            onClick={() => rollMutation.mutate()}
            disabled={rollMutation.isPending}
            className="btn-cyber text-xs py-1 px-3"
          >
            {rollMutation.isPending ? <Loader2 className="w-3 h-3 animate-spin" /> : <Dice5 className="w-3 h-3" />}
            Roll
          </button>
          <button
            onClick={() => updateMutation.mutate()}
            disabled={updateMutation.isPending}
            className="btn-ghost text-xs py-1 px-2"
          >
            {updateMutation.isPending ? <Loader2 className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />}
          </button>
          <button onClick={onClose} aria-label="Close" className="btn-ghost text-xs py-1 px-2">
            <X className="w-3 h-3" />
          </button>
        </div>
      </div>

      {/* Roll result */}
      <AnimatePresence>
        {rollResult && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            className="px-4 py-2 border-b border-white/5 flex-shrink-0"
          >
            <div className="glass-dark rounded-xl border border-cyan-500/20 bg-cyan-500/5 p-3">
              <div className="flex items-center justify-between">
                <span className="text-xs text-cyan-400 font-medium">Roll Result</span>
                <span className="text-xs font-mono text-slate-300">
                  Rolled {rollResult.roll ?? "?"} on {table.dice_formula}
                </span>
              </div>
              <p className="text-sm text-slate-200 mt-1">{rollResult.entry?.value ?? "No result"}</p>
              {rollResult.sub_results && rollResult.sub_results.length > 0 && (
                <div className="mt-2 space-y-1">
                  {rollResult.sub_results.map((sr: any, i: number) => (
                    <div key={i} className="text-xs text-slate-400 flex items-center gap-1.5">
                      <ChevronDown className="w-3 h-3" />
                      <span className="font-mono">{sr.roll}</span> → {sr.entry?.value}
                    </div>
                  ))}
                </div>
              )}
              <button
                onClick={() => setRollResult(null)}
                className="text-[10px] text-slate-600 hover:text-slate-400 mt-1"
              >
                Dismiss
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Description */}
      {table.description && (
        <div className="px-4 py-2 border-b border-white/5 flex-shrink-0">
          <p className="text-xs text-slate-500 leading-relaxed">{table.description}</p>
        </div>
      )}

      {/* Entries */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-2">
        <div className="flex items-center justify-between mb-2">
          <span className="text-[10px] font-bold tracking-widest uppercase text-slate-500">
            Entries ({entries.length})
          </span>
          <button onClick={handleAddEntry} className="btn-ghost text-[10px] py-0.5 px-2">
            <Plus className="w-3 h-3" /> Add Entry
          </button>
        </div>
        <div className="space-y-1.5">
          {entries.map((entry, i) => (
            <EntryRow
              key={i}
              entry={entry}
              index={i}
              onChange={handleEntryChange}
              onRemove={handleEntryRemove}
            />
          ))}
        </div>
        {entries.length === 0 && (
          <div className="text-center py-6">
            <Dice5 className="w-6 h-6 text-slate-700 mx-auto mb-2" />
            <p className="text-xs text-slate-600">No entries yet. Add one to get started.</p>
          </div>
        )}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
//  Random Table Browser (main export)
// ═══════════════════════════════════════════════════════════════

interface RandomTableBrowserProps {
  universeId: string | null;
}

export function RandomTableBrowser({ universeId }: RandomTableBrowserProps) {
  const [search, setSearch] = useState("");
  const [filterType, setFilterType] = useState<string | null>(null);
  const [selectedTable, setSelectedTable] = useState<RandomTable | null>(null);
  const queryClient = useQueryClient();

  const { data: listData, isLoading, refetch } = useQuery({
    queryKey: ["random-tables", universeId, filterType],
    queryFn: () => randomTablesApi.list(universeId ?? undefined, filterType ?? undefined),
    enabled: true,
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => randomTablesApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["random-tables"] });
      if (selectedTable) setSelectedTable(null);
    },
  });

  const tables = listData?.tables ?? [];
  const filtered = search
    ? tables.filter((t) =>
        t.name.toLowerCase().includes(search.toLowerCase()) ||
        t.description.toLowerCase().includes(search.toLowerCase())
      )
    : tables;

  // If a table is selected, show the editor
  if (selectedTable) {
    return (
      <TableEditor
        table={selectedTable}
        onClose={() => setSelectedTable(null)}
      />
    );
  }

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Toolbar */}
      <div className="flex items-center gap-2 px-4 py-2 border-b border-white/5 flex-shrink-0">
        <Dice5 className="w-3.5 h-3.5 text-amber-400 flex-shrink-0" />
        <span className="text-xs font-semibold text-slate-300 flex-1">Random Tables</span>
        <button onClick={() => refetch()} className="btn-ghost text-xs py-0.5 px-2">
          <RefreshCw className="w-3 h-3" />
        </button>
      </div>

      {/* Search + filter */}
      <div className="px-4 py-2 space-y-2 border-b border-white/5 flex-shrink-0">
        <div className="relative">
          <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3 h-3 text-slate-600" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search tables..."
            className="input-cyber pl-7 py-1 text-xs w-full"
          />
        </div>
        <div className="flex flex-wrap gap-1">
          {["all", "encounter", "loot", "name", "trait", "weather", "rumor", "npc", "event", "custom"].map((type) => (
            <button
              key={type}
              onClick={() => setFilterType(type === "all" ? null : type)}
              className={cn(
                "text-[10px] px-2 py-0.5 rounded-lg border transition-all",
                (type === "all" ? !filterType : filterType === type)
                  ? "bg-amber-500/15 text-amber-300 border-amber-500/30"
                  : "text-slate-500 border-white/5 hover:text-slate-300"
              )}
            >
              {type === "all" ? "All" : (TABLE_TYPE_CONFIG[type]?.label ?? type)}
            </button>
          ))}
        </div>
      </div>

      {/* Table list */}
      <div className="flex-1 overflow-y-auto px-3 py-3 space-y-2">
        {isLoading && (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="w-5 h-5 text-slate-600 animate-spin" />
          </div>
        )}
        {!isLoading && filtered.length === 0 && (
          <div className="text-center py-8">
            <Dice5 className="w-8 h-8 text-slate-700 mx-auto mb-2" />
            <p className="text-xs text-slate-600">
              {universeId ? "No random tables found" : "Select a universe to see tables"}
            </p>
          </div>
        )}
        {filtered.map((table) => {
          const config = getTableTypeConfig(table.table_type);
          return (
            <button
              key={table.table_id}
              onClick={() => setSelectedTable(table)}
              className="w-full text-left glass-dark rounded-xl border border-white/5 p-3 space-y-1.5 hover:border-white/10 hover:bg-white/2 transition-all"
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="text-sm">{config.icon}</span>
                  <span className="text-xs font-semibold text-slate-200 truncate">{table.name}</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <span className={cn("text-[10px] px-1.5 py-0.5 rounded border", config.color, config.bg, config.border)}>
                    {config.label}
                  </span>
                  <button
                    onClick={(e) => { e.stopPropagation(); deleteMutation.mutate(table.table_id); }}
                    className="text-slate-600 hover:text-red-400 transition-colors"
                  >
                    <Trash2 className="w-3 h-3" />
                  </button>
                </div>
              </div>
              {table.description && (
                <p className="text-[11px] text-slate-500 leading-relaxed line-clamp-1">{table.description}</p>
              )}
              <div className="flex items-center gap-3 text-[10px] text-slate-600">
                <span className="font-mono">{table.dice_formula}</span>
                <span>{table.entries.length} entries</span>
                {table.weighted && <span className="text-amber-500">Weighted</span>}
              </div>
            </button>
          );
        })}
      </div>

      {/* Footer */}
      <div className="px-4 py-2 border-t border-white/5 flex-shrink-0 text-[10px] text-slate-700">
        {filtered.length} table{filtered.length !== 1 ? "s" : ""} · {listData?.total ?? 0} total
      </div>
    </div>
  );
}