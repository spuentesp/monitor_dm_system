"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { motion, AnimatePresence } from "framer-motion";
import { BookOpen, ChevronDown, Loader2 } from "lucide-react";
import { entitiesApi } from "@/lib/api";
import type { RPGSystem } from "@/lib/types";
import { cn } from "@/lib/utils";

// One expandable rule. Lives outside the parent render so its open/closed
// state is a real component state (hooks inside system.rules.map() used to
// change the hook count between renders and crash the panel).
function RuleRow({ rule }: { rule: RPGSystem["rules"][number] }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="group glass-dark rounded-xl border border-white/5 overflow-hidden">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full px-3 py-2.5 cursor-pointer flex items-center justify-between"
      >
        <span className="text-xs font-medium text-slate-200">{rule.name}</span>
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-slate-600 bg-white/5 px-1.5 py-0.5 rounded">{rule.rule_type}</span>
          <ChevronDown className={cn("w-3.5 h-3.5 text-slate-600 transition-transform duration-200", open && "rotate-[-180deg]")} />
        </div>
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="px-3 pb-3 space-y-1.5">
              {rule.description && <p className="text-xs text-slate-400 leading-relaxed">{rule.description}</p>}
              {rule.formula && <code className="block text-xs font-mono text-emerald-300 bg-emerald-500/5 rounded px-2 py-1">{rule.formula}</code>}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

export function RulesPanel({ systemId }: { systemId: string | null }) {
  const { data: system, isLoading } = useQuery({
    queryKey: ["system-detail", systemId],
    queryFn: () => entitiesApi.getSystem(systemId!),
    enabled: Boolean(systemId),
  });

  if (!systemId) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center space-y-2 px-4">
        <BookOpen className="w-8 h-8 text-slate-700" />
        <p className="text-xs text-slate-600">Select an RPG system to see rules reference</p>
      </div>
    );
  }
  if (isLoading) return <div className="flex items-center justify-center h-full"><Loader2 className="w-5 h-5 text-slate-600 animate-spin" /></div>;
  if (!system) return <div className="p-4 text-xs text-slate-600">System not found.</div>;

  return (
    <div className="overflow-y-auto h-full px-4 py-4 space-y-5">
      {/* Core mechanic */}
      {system.core_mechanic && (
        <section className="space-y-2">
          <h3 className="text-[10px] font-bold tracking-widest uppercase text-emerald-400">Core Mechanic</h3>
          <div className="glass-dark rounded-xl border border-white/5 p-3 space-y-1.5">
            {system.core_mechanic.formula && <p className="text-xs font-mono text-slate-300">{system.core_mechanic.formula}</p>}
            {system.core_mechanic.description && <p className="text-xs text-slate-500 leading-relaxed">{system.core_mechanic.description}</p>}
            <div className="flex gap-3 text-[10px] text-slate-600">
              {system.core_mechanic.success_type && <span>Success: {system.core_mechanic.success_type}</span>}
              {system.core_mechanic.target_number != null && <span>Target: {system.core_mechanic.target_number}</span>}
            </div>
          </div>
        </section>
      )}

      {/* Attributes */}
      {system.attributes.length > 0 && (
        <section className="space-y-2">
          <h3 className="text-[10px] font-bold tracking-widest uppercase text-cyan-400">Attributes</h3>
          <div className="grid grid-cols-2 gap-1.5">
            {system.attributes.map((a) => (
              <div key={a.name} className="glass-dark rounded-lg border border-white/5 px-2.5 py-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold text-slate-200">{a.abbreviation ?? a.name}</span>
                  {a.min_value != null && a.max_value != null && (
                    <span className="text-[10px] text-slate-600">{a.min_value}–{a.max_value}</span>
                  )}
                </div>
                {a.description && <p className="text-[10px] text-slate-600 mt-0.5 leading-relaxed truncate">{a.description}</p>}
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Resources */}
      {system.resources.length > 0 && (
        <section className="space-y-2">
          <h3 className="text-[10px] font-bold tracking-widest uppercase text-purple-400">Resources</h3>
          <div className="space-y-1">
            {system.resources.map((r) => (
              <div key={r.name} className="glass-dark rounded-lg border border-white/5 px-2.5 py-2 flex items-center justify-between">
                <span className="text-xs font-medium text-slate-200">{r.name}</span>
                <div className="text-[10px] text-slate-600 space-x-2">
                  {r.max_value != null && <span>Max {r.max_value}</span>}
                  {r.recovers_on && <span>Recovers: {r.recovers_on}</span>}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Rules */}
      {system.rules.length > 0 && (
        <section className="space-y-2">
          <h3 className="text-[10px] font-bold tracking-widest uppercase text-amber-400">Rules</h3>
          <div className="space-y-2">
            {system.rules.map((r) => (
              <RuleRow key={r.name} rule={r} />
            ))}
          </div>
        </section>
      )}

      {system.description && (
        <section className="space-y-2">
          <h3 className="text-[10px] font-bold tracking-widest uppercase text-slate-600">About</h3>
          <p className="text-xs text-slate-500 leading-relaxed">{system.description}</p>
        </section>
      )}
    </div>
  );
}
