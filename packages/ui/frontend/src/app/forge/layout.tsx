"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { FlaskConical } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  FORGE_SECTIONS,
  isForgeSectionActive,
  type ForgeAccent,
} from "@/lib/forge-sections";

const ACCENT_CLASSES: Record<ForgeAccent, { active: string; icon: string }> = {
  cyan: {
    active: "bg-cyan-500/10 border-cyan-500/25 text-cyan-300",
    icon: "text-cyan-400",
  },
  purple: {
    active: "bg-purple-500/10 border-purple-500/25 text-purple-300",
    icon: "text-purple-400",
  },
  emerald: {
    active: "bg-emerald-500/10 border-emerald-500/25 text-emerald-300",
    icon: "text-emerald-400",
  },
};

export default function ForgeLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Section nav — mirrors the Sidebar idiom (cn + accent classes) */}
      <div className="flex-shrink-0 border-b border-white/5 glass-dark">
        <div className="flex items-center gap-1 px-4 py-2 overflow-x-auto">
          <div className="flex items-center gap-2 pr-3 mr-1 border-r border-white/10 flex-shrink-0">
            <FlaskConical className="w-4 h-4 text-cyan-400" />
            <span className="text-xs font-bold tracking-[0.18em] uppercase text-slate-400 whitespace-nowrap">
              Forge
            </span>
          </div>
          {FORGE_SECTIONS.map((section) => {
            const active = isForgeSectionActive(section, pathname);
            const ac = ACCENT_CLASSES[section.accent];
            const Icon = section.icon;
            return (
              <Link
                key={section.href}
                href={section.href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "relative flex items-center gap-2 px-3 py-1.5 rounded-lg border text-xs font-medium transition-all duration-200 whitespace-nowrap",
                  active
                    ? ac.active
                    : "border-transparent text-slate-500 hover:text-slate-200 hover:bg-white/4",
                )}
              >
                <Icon className={cn("w-3.5 h-3.5 flex-shrink-0", active ? ac.icon : "")} />
                {section.label}
              </Link>
            );
          })}
        </div>
      </div>

      {/* Section content */}
      <div className="flex-1 overflow-hidden flex flex-col">{children}</div>
    </div>
  );
}
