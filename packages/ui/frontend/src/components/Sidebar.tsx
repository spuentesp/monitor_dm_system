"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import {
  Activity,
  BookOpen,
  Camera,
  ChevronLeft,
  ChevronRight,
  ClipboardList,
  Compass,
  FlaskConical,
  Gamepad2,
  Globe2,
  History,
  Network,
  Settings,
  Sparkles,
  Users,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { ConnectionStatus } from "@/components/ConnectionStatus";
import { ModeSwitcher } from "@/components/ModeSwitcher";
import { WorldPicker } from "@/components/WorldPicker";

// ─── Navigation structure ──────────────────────────────────────

const NAV_GROUPS = [
  {
    id: "modes",
    label: "Modes",
    items: [
      { href: "/architect", icon: Compass,   label: "World Architect", sub: "Build multiverses & worlds",  accent: "purple" },
      { href: "/play",      icon: Gamepad2,  label: "Play",           sub: "Solo RPG session",            accent: "cyan"   },
      { href: "/characters", icon: Users,    label: "Characters",     sub: "Roster & conversatory",       accent: "purple" },
      { href: "/gm",        icon: ClipboardList, label: "GM Assistant",   sub: "Rules, dice & session log",  accent: "emerald" },
    ],
  },
  {
    id: "build",
    label: "Build",
    items: [
      { href: "/search",    icon: Sparkles,      label: "Search",      sub: "Semantic canon search",    accent: "cyan"   },
      { href: "/worlds",     icon: Globe2,       label: "Worlds",      sub: "Graph, worlds & entities", accent: "purple" },
      { href: "/explorer",  icon: Network,       label: "Explorer",    sub: "Q-11 entity graph drill-down", accent: "cyan" },
      { href: "/snapshots", icon: Camera,        label: "Snapshots",   sub: "World state history",       accent: "cyan"   },
      { href: "/history",   icon: History,       label: "History",     sub: "Q-10 canon audit trail",   accent: "purple" },
      { href: "/forge",      icon: FlaskConical,  label: "World Forge", sub: "Packs & sources",          accent: "cyan"   },
      { href: "/systems",    icon: BookOpen,      label: "Systems",     sub: "RPG rules",                accent: "purple" },
    ],
  },
  {
    id: "system",
    label: "System",
    items: [
      { href: "/settings", icon: Settings, label: "Settings", sub: "LLM, agents & databases", accent: "emerald" },
    ],
  },
] as const;

type Accent = "cyan" | "purple" | "emerald";

const ACCENT_CLASSES: Record<Accent, { active: string; icon: string; indicator: string }> = {
  cyan: {
    active: "bg-cyan-500/10 border-cyan-500/25 text-cyan-300",
    icon: "text-cyan-400",
    indicator: "bg-cyan-500",
  },
  purple: {
    active: "bg-purple-500/10 border-purple-500/25 text-purple-300",
    icon: "text-purple-400",
    indicator: "bg-purple-500",
  },
  emerald: {
    active: "bg-emerald-500/10 border-emerald-500/25 text-emerald-300",
    icon: "text-emerald-400",
    indicator: "bg-emerald-500",
  },
};

// ─── Component ────────────────────────────────────────────────

export function Sidebar() {
  const [collapsed, setCollapsed] = useState(false);
  const pathname = usePathname();

  return (
    <motion.nav
      animate={{ width: collapsed ? 60 : 224 }}
      initial={false}
      transition={{ type: "spring", stiffness: 320, damping: 32 }}
      className="glass flex-shrink-0 flex flex-col h-full border-r border-white/5 z-10 relative overflow-hidden"
    >
      {/* Logo */}
      <div className="flex items-center gap-3 px-3.5 py-5 border-b border-white/5 overflow-hidden flex-shrink-0">
        <div className="flex-shrink-0 w-8 h-8 rounded-lg bg-cyan-500/10 border border-cyan-500/25 flex items-center justify-center shadow-cyan-glow">
          <Activity className="w-4 h-4 text-cyan-400" />
        </div>
        <AnimatePresence mode="wait">
          {!collapsed && (
            <motion.div
              initial={{ opacity: 0, x: -8 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -8 }}
              transition={{ duration: 0.15 }}
              className="overflow-hidden"
            >
              <div className="text-xs font-bold text-neon-cyan tracking-[0.2em] whitespace-nowrap">
                MONITOR
              </div>
              <div className="text-[10px] text-slate-600 whitespace-nowrap tracking-wide">
                Narrative AI
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Navigation groups */}
      <div className="flex-1 py-2 px-2 overflow-y-auto overflow-x-hidden space-y-1">
        {NAV_GROUPS.map((group, gi) => (
          <div key={group.id} className={cn(gi > 0 && "pt-1")}>
            {/* Section divider + label */}
            <div className={cn(
              "flex items-center gap-2 px-2 mb-0.5 overflow-hidden",
              gi > 0 ? "mt-1 pt-1 border-t border-white/5" : "",
            )}>
              <AnimatePresence mode="wait">
                {!collapsed ? (
                  <motion.span
                    key="label"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    transition={{ duration: 0.12 }}
                    className="text-[9px] font-semibold tracking-[0.18em] uppercase text-slate-600 whitespace-nowrap"
                  >
                    {group.label}
                  </motion.span>
                ) : (
                  <motion.div
                    key="dot"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    className="w-full flex justify-center"
                  >
                    <div className="w-3 h-px bg-white/10" />
                  </motion.div>
                )}
              </AnimatePresence>
            </div>

            {group.items.map(({ href, icon: Icon, label, sub, accent }) => {
              const active = pathname === href || pathname.startsWith(href + "/");
              const ac = ACCENT_CLASSES[accent as Accent];
              return (
                <Link
                  key={href}
                  href={href}
                  aria-current={active ? "page" : undefined}
                  className="block"
                >
                  <motion.div
                    whileHover={{ x: collapsed ? 0 : 2 }}
                    className={cn(
                      "relative flex items-center gap-3 px-2.5 py-2 rounded-lg border transition-all duration-200 overflow-hidden",
                      active
                        ? ac.active
                        : "border-transparent text-slate-400 hover:text-slate-200 hover:bg-white/4",
                    )}
                  >
                    {active && (
                      <motion.div
                        layoutId="sidebar-indicator"
                        className={cn(
                          "absolute left-0 top-2 bottom-2 w-0.5 rounded-full",
                          ac.indicator,
                        )}
                      />
                    )}

                    <Icon className={cn("w-4 h-4 flex-shrink-0", active ? ac.icon : "")} />

                    <AnimatePresence mode="wait">
                      {!collapsed && (
                        <motion.div
                          initial={{ opacity: 0 }}
                          animate={{ opacity: 1 }}
                          exit={{ opacity: 0 }}
                          transition={{ duration: 0.12 }}
                          className="min-w-0"
                        >
                          <div className="text-sm font-medium leading-tight whitespace-nowrap">
                            {label}
                          </div>
                          <div className="text-[10px] text-slate-600 whitespace-nowrap mt-0.5">
                            {sub}
                          </div>
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </motion.div>
                </Link>
              );
            })}
          </div>
        ))}
      </div>

      {/* Footer */}
      <div className="border-t border-white/5 px-2 py-3 space-y-1 flex-shrink-0">
        <AnimatePresence>
          {!collapsed && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="px-2.5 pb-1"
            >
              <div className="text-[10px] text-slate-700 font-mono">v0.1.0-dev</div>
            </motion.div>
          )}
        </AnimatePresence>
        <WorldPicker collapsed={collapsed} />
        <ModeSwitcher collapsed={collapsed} />
        <ConnectionStatus />
        <button
          onClick={() => setCollapsed((c) => !c)}
          className="w-full flex items-center justify-center p-2 rounded-lg text-slate-600 hover:text-cyan-400 hover:bg-cyan-500/5 transition-all duration-150"
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {collapsed ? <ChevronRight className="w-4 h-4" /> : <ChevronLeft className="w-4 h-4" />}
        </button>
      </div>
    </motion.nav>
  );
}

