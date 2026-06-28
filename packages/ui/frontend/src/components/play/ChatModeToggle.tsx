"use client";

import { cn } from "@/lib/utils";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface ChatModeToggleProps {
  mode: "ic" | "ooc";
  onChange: (mode: "ic" | "ooc") => void;
  className?: string;
}

// ---------------------------------------------------------------------------
// ChatModeToggle
// ---------------------------------------------------------------------------

export function ChatModeToggle({ mode, onChange, className }: ChatModeToggleProps) {
  return (
    <div className={cn("flex items-center gap-1 p-0.5 rounded-lg bg-white/5 border border-white/10", className)}>
      <button
        onClick={() => onChange("ic")}
        aria-pressed={mode === "ic"}
        className={cn(
          "flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] font-medium transition-all",
          mode === "ic"
            ? "bg-emerald-500/15 text-emerald-300 shadow-sm"
            : "text-slate-500 hover:text-slate-300",
        )}
      >
        <span
          className={cn(
            "w-1.5 h-1.5 rounded-full transition-colors",
            mode === "ic" ? "bg-emerald-400" : "bg-slate-600",
          )}
        />
        IC
      </button>
      <button
        onClick={() => onChange("ooc")}
        aria-pressed={mode === "ooc"}
        className={cn(
          "flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] font-medium transition-all",
          mode === "ooc"
            ? "bg-amber-500/15 text-amber-300 shadow-sm"
            : "text-slate-500 hover:text-slate-300",
        )}
      >
        <span
          className={cn(
            "w-1.5 h-1.5 rounded-full transition-colors",
            mode === "ooc" ? "bg-amber-400" : "bg-slate-600",
          )}
        />
        OOC
      </button>
    </div>
  );
}