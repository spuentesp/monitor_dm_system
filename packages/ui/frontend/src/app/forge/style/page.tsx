"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { BookOpen, Library, Palette, Tags } from "lucide-react";
import { ToneTab } from "@/components/forge/style/ToneTab";
import { LibrariesPanel } from "@/components/forge/style/LibrariesPanel";
import { TagDefinitionsPanel } from "@/components/forge/style/TagDefinitionsPanel";
import { LorebookPanel } from "@/components/forge/style/LorebookPanel";
import { cn } from "@/lib/utils";

// ─── Style (F3-4) ───────────────────────────────────────────
// Tone profiles/libraries/tags + lorebook management. Profiles mounts the
// ToneTab lifted from /settings (F3-4.1 / F1-5a); Libraries (F3-4.2), Tags
// (F3-4.3) and Lorebook (F3-4.4) are real panels.

const STYLE_TABS = [
  { id: "profiles", label: "Profiles", icon: Palette },
  { id: "libraries", label: "Libraries", icon: Library },
  { id: "tags", label: "Tags", icon: Tags },
  { id: "lorebook", label: "Lorebook", icon: BookOpen },
] as const;

type StyleTab = (typeof STYLE_TABS)[number]["id"];

export default function ForgeStylePage() {
  const [tab, setTab] = useState<StyleTab>("profiles");

  return (
    <div className="flex flex-col h-full">
      {/* Tabs */}
      <div className="flex items-center px-6 pt-5 pb-0 gap-1 border-b border-white/5 flex-shrink-0">
        {STYLE_TABS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className={cn(
              "flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-all",
              tab === id
                ? "border-cyan-500 text-cyan-300"
                : "border-transparent text-slate-500 hover:text-slate-300",
            )}
          >
            <Icon className="w-3.5 h-3.5" />
            {label}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-6 py-5">
        <AnimatePresence mode="wait">
          <motion.div
            key={tab}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
          >
            {tab === "profiles" && <ToneTab />}
            {tab === "libraries" && <LibrariesPanel />}
            {tab === "tags" && <TagDefinitionsPanel />}
            {tab === "lorebook" && <LorebookPanel />}
          </motion.div>
        </AnimatePresence>
      </div>
    </div>
  );
}
