"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  ClipboardList,
  Compass,
  Gamepad2,
  Globe2,
  MessageSquare,
  Sparkles,
  Terminal,
} from "lucide-react";
import { chatApi, universesApi } from "@/lib/api";
import { PLAY_KEYS, UNIVERSE_KEYS } from "@/lib/query-keys";
import { OnboardingWizard } from "@/components/play/OnboardingWizard";
import type { Session, Universe } from "@/lib/types";
import { cn, formatRelativeTime } from "@/lib/utils";

const MODES = [
  {
    href: "/play",
    icon: Gamepad2,
    title: "Play",
    blurb: "Solo roleplay with an autonomous GM — dice, oracle, canon memory.",
    accent: "cyan",
  },
  {
    href: "/architect",
    icon: Compass,
    title: "World Architect",
    blurb: "Build worlds conversationally or from ingested source books.",
    accent: "purple",
  },
  {
    href: "/gm",
    icon: ClipboardList,
    title: "GM Assistant",
    blurb: "Recaps, plot hooks, contradiction checks and canon review.",
    accent: "emerald",
  },
] as const;

const ACCENT: Record<string, { border: string; icon: string }> = {
  cyan: {
    border: "hover:border-cyan-500/40",
    icon: "text-cyan-400 bg-cyan-500/10 border-cyan-500/20",
  },
  purple: {
    border: "hover:border-purple-500/40",
    icon: "text-purple-400 bg-purple-500/10 border-purple-500/20",
  },
  emerald: {
    border: "hover:border-emerald-500/40",
    icon: "text-emerald-400 bg-emerald-500/10 border-emerald-500/20",
  },
};

export default function Home() {
  const sessionsQ = useQuery({
    queryKey: PLAY_KEYS.sessions,
    queryFn: () => chatApi.listSessions(),
  });
  const universesQ = useQuery({
    queryKey: UNIVERSE_KEYS.universes(),
    queryFn: () => universesApi.listUniverses(),
  });

  const sessions: Session[] = (sessionsQ.data ?? [])
    .slice()
    .sort((a, b) => (b.updated_at ?? "").localeCompare(a.updated_at ?? ""))
    .slice(0, 5);
  const universes: Universe[] = universesQ.data ?? [];

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-5xl mx-auto px-8 py-10 space-y-10">
        {/* Hero */}
        <div className="space-y-2">
          <div className="flex items-center gap-2 text-xs uppercase tracking-[0.2em] text-slate-600">
            <Sparkles className="w-3.5 h-3.5 text-cyan-400" />
            Multi-Ontology Narrative Intelligence
          </div>
          <h1 className="text-3xl font-bold text-slate-100">MONITOR</h1>
          <p className="text-sm text-slate-500 max-w-xl">
            Persistent worlds, an autonomous game master, and a co-pilot for
            human GMs — everything you play becomes canon.
          </p>
        </div>

        {/* Mode cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {MODES.map(({ href, icon: Icon, title, blurb, accent }) => {
            const ac = ACCENT[accent];
            return (
              <Link
                key={href}
                href={href}
                className={cn(
                  "card-glass rounded-xl border border-white/5 p-5 transition-all duration-200",
                  ac.border,
                )}
              >
                <div
                  className={cn(
                    "w-9 h-9 rounded-lg border flex items-center justify-center mb-3",
                    ac.icon,
                  )}
                >
                  <Icon className="w-4 h-4" />
                </div>
                <div className="text-sm font-semibold text-slate-100">{title}</div>
                <p className="mt-1 text-xs text-slate-500 leading-relaxed">{blurb}</p>
              </Link>
            );
          })}
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Continue playing */}
          <section className="space-y-3">
            <h2 className="text-xs uppercase tracking-wider text-slate-600 flex items-center gap-2">
              <MessageSquare className="w-3.5 h-3.5" /> Continue playing
            </h2>
            {sessionsQ.isLoading ? (
              <div className="text-xs text-slate-600">Loading sessions…</div>
            ) : sessions.length === 0 ? (
              <OnboardingWizard />
            ) : (
              <div className="space-y-2">
                {sessions.map((s) => (
                  <Link
                    key={s.id}
                    href={`/play?session=${s.id}`}
                    className="card-glass rounded-xl border border-white/5 hover:border-cyan-500/30 px-4 py-3 flex items-center justify-between gap-3 transition-all"
                  >
                    <div className="min-w-0">
                      <div className="text-sm text-slate-200 truncate">{s.title}</div>
                      <div className="text-[11px] text-slate-600 capitalize">
                        {(s.mode ?? "").replace(/_/g, " ")}
                        {s.universe_label ? ` · ${s.universe_label}` : ""}
                      </div>
                    </div>
                    <span className="text-[11px] text-slate-600 flex-shrink-0">
                      {s.updated_at ? formatRelativeTime(s.updated_at) : ""}
                    </span>
                  </Link>
                ))}
              </div>
            )}
          </section>

          {/* Worlds */}
          <section className="space-y-3">
            <h2 className="text-xs uppercase tracking-wider text-slate-600 flex items-center gap-2">
              <Globe2 className="w-3.5 h-3.5" /> Your worlds
            </h2>
            {universesQ.isLoading ? (
              <div className="text-xs text-slate-600">Loading worlds…</div>
            ) : universes.length === 0 ? (
              <div className="card-glass rounded-xl border border-white/5 p-4 space-y-2">
                <p className="text-xs text-slate-500">
                  No worlds yet. Build one in the{" "}
                  <Link href="/architect" className="text-purple-400 hover:underline">
                    World Architect
                  </Link>
                  , or seed the demo from a terminal:
                </p>
                <div className="flex items-center gap-2 rounded-lg bg-black/40 border border-white/5 px-3 py-2 font-mono text-[11px] text-slate-400">
                  <Terminal className="w-3 h-3 flex-shrink-0" />
                  uv run python scripts/demo_millhaven.py
                </div>
              </div>
            ) : (
              <div className="space-y-2">
                {universes.slice(0, 5).map((u) => (
                  <Link
                    key={u.id}
                    href={`/explorer?universe=${u.id}`}
                    className="card-glass rounded-xl border border-white/5 hover:border-purple-500/30 px-4 py-3 flex items-center justify-between gap-3 transition-all"
                  >
                    <div className="min-w-0">
                      <div className="text-sm text-slate-200 truncate">{u.name}</div>
                      {u.genre && (
                        <div className="text-[11px] text-slate-600">{u.genre}</div>
                      )}
                    </div>
                    <span className="text-[11px] text-slate-600">explore →</span>
                  </Link>
                ))}
                <Link
                  href="/worlds"
                  className="block text-[11px] text-slate-500 hover:text-slate-300 px-1"
                >
                  All worlds →
                </Link>
              </div>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}
