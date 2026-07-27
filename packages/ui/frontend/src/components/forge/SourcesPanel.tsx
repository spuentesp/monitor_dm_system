"use client";

import { useState } from "react";
import { 
  Sparkles, 
  PackageCheck, 
  BrainCircuit, 
  BookOpen,
  Plus
} from "lucide-react";
import { cn } from "@/lib/utils";
import { AnimatePresence, motion } from "framer-motion";
import { IngestionDashboard } from "./ingest/IngestionDashboard";
import { PackLibrary } from "./ingest/PackLibrary";

const FORGE_TABS = [
  { id: "ingest", label: "Source Ingestion", icon: Sparkles },
  { id: "packs",  label: "Pack Library",     icon: PackageCheck },
] as const;

type ForgeTab = (typeof FORGE_TABS)[number]["id"];

export function SourcesPanel({ onOpenPack }: { onOpenPack?: (packId: string) => void }) {
  const [activeTab, setActiveTab] = useState<ForgeTab>("ingest");

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Tab Navigation */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-white/5 bg-slate-950/20">
        <div className="flex items-center gap-1 p-1 bg-white/5 rounded-xl border border-white/5">
          {FORGE_TABS.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              onClick={() => setActiveTab(id)}
              className={cn(
                "flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-bold transition-all",
                activeTab === id
                  ? "bg-cyan-500/10 text-cyan-400 shadow-[0_0_15px_-5px_rgba(34,211,238,0.3)]"
                  : "text-slate-500 hover:text-slate-300"
              )}
            >
              <Icon className="w-3.5 h-3.5" />
              {label}
            </button>
          ))}
        </div>

        {activeTab === "packs" && (
          <div className="flex items-center gap-2">
             <p className="text-[10px] text-slate-500 uppercase tracking-widest font-medium mr-2 hidden sm:block">
               Refined Knowledge
             </p>
          </div>
        )}
      </div>

      {/* Main Content Area */}
      <div className="flex-1 overflow-hidden">
        <AnimatePresence mode="wait">
          <motion.div
            key={activeTab}
            initial={{ opacity: 0, x: 10 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -10 }}
            transition={{ duration: 0.2 }}
            className="h-full overflow-y-auto px-6 py-6 custom-scrollbar"
          >
            {activeTab === "ingest" ? (
              <IngestionDashboard />
            ) : (
              <div className="max-w-6xl mx-auto">
                <div className="mb-6">
                  <h2 className="text-xl font-bold text-slate-100">Knowledge Packs</h2>
                  <p className="text-sm text-slate-500 mt-1">
                    Manage extracted lore and mechanics. Apply them to your universes to build the world graph.
                  </p>
                </div>
                <PackLibrary onOpenPack={onOpenPack} />
              </div>
            )}
          </motion.div>
        </AnimatePresence>
      </div>
    </div>
  );
}
