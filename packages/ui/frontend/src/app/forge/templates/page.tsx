"use client";

import { useState } from "react";
import { BookOpen, Dice5 } from "lucide-react";
import { TemplateBrowser } from "@/components/forge/TemplateBrowser";
import { TemplateInstantiator } from "@/components/forge/TemplateInstantiator";
import { RandomTableBrowser } from "@/components/forge/RandomTableEditor";
import { useWorldContext } from "@/lib/world-context";
import type { EntityTemplate } from "@/lib/types";
import { cn } from "@/lib/utils";

// ─── Templates & Tables (F3-2) ────────────────────────────────
// EntityTemplate authoring + random tables, moved out of the
// pack-detail tabs into their own Forge section.

type Section = "templates" | "tables";

export default function ForgeTemplatesPage() {
  const { universeId } = useWorldContext();
  const [section, setSection] = useState<Section>("templates");
  const [instantiatingTemplate, setInstantiatingTemplate] = useState<EntityTemplate | null>(null);

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Section switcher */}
      <div className="flex items-center gap-2 px-4 py-2 border-b border-white/5 flex-shrink-0">
        <button
          onClick={() => setSection("templates")}
          className={cn(
            "flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border transition-all",
            section === "templates"
              ? "bg-cyan-500/15 text-cyan-300 border-cyan-500/30"
              : "text-slate-500 border-white/5 hover:text-slate-300",
          )}
        >
          <BookOpen className="w-3.5 h-3.5" /> Entity Templates
        </button>
        <button
          onClick={() => setSection("tables")}
          className={cn(
            "flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border transition-all",
            section === "tables"
              ? "bg-amber-500/15 text-amber-300 border-amber-500/30"
              : "text-slate-500 border-white/5 hover:text-slate-300",
          )}
        >
          <Dice5 className="w-3.5 h-3.5" /> Random Tables
        </button>
        {!universeId && (
          <span className="text-[10px] text-slate-600 ml-auto">
            No active world — showing all universes. Pick a world in the sidebar to create.
          </span>
        )}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-hidden">
        {section === "templates" ? (
          <TemplateBrowser
            universeId={universeId}
            onInstantiate={(template) => setInstantiatingTemplate(template)}
          />
        ) : (
          <RandomTableBrowser universeId={universeId} />
        )}
      </div>

      {/* Instantiate modal */}
      {instantiatingTemplate && (
        <TemplateInstantiator
          template={instantiatingTemplate}
          open={!!instantiatingTemplate}
          onClose={() => setInstantiatingTemplate(null)}
          onCreated={() => setInstantiatingTemplate(null)}
        />
      )}
    </div>
  );
}
