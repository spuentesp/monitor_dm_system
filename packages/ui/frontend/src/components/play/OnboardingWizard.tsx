"use client";

import { useState } from "react";
import Link from "next/link";
import { Sparkles, Loader2 } from "lucide-react";
import { forgeApi } from "@/lib/api";

/**
 * First-run on-ramp shown on the Home page when there are no sessions yet.
 * "Try the demo world" spins up the curated, LLM-free Millhaven world and a
 * bound session, then drops the player straight into Play.
 */
export function OnboardingWizard() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleDemo = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await forgeApi.demoWorld(true);
      if (res.session_id) {
        window.location.href = `/play?session=${res.session_id}`;
      } else {
        // World was created but no session bootstrapped — send them to Play setup.
        window.location.href = `/play?universe=${res.universe_id}`;
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not create the demo world.");
      setLoading(false);
    }
  };

  return (
    <div className="card-glass rounded-xl border border-white/5 p-5">
      <div className="flex items-center gap-2 text-cyan-300">
        <Sparkles className="w-4 h-4" />
        <h2 className="text-sm font-semibold tracking-wide">Welcome to Monitor</h2>
      </div>
      <p className="text-xs text-slate-400 mt-2 leading-relaxed">
        No sessions yet. Drop into a ready-made mystery — fog-bound Millhaven,
        where villagers vanish after dark — or forge your own world from a single
        sentence.
      </p>
      <div className="mt-4 flex flex-wrap items-center gap-2">
        <button
          onClick={handleDemo}
          disabled={loading}
          className="btn-cyber text-xs px-3 py-1.5 gap-1.5"
        >
          {loading ? (
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
          ) : (
            <Sparkles className="w-3.5 h-3.5" />
          )}
          {loading ? "Creating…" : "Try the demo world"}
        </button>
        <Link
          href="/forge"
          className="text-xs text-slate-400 hover:text-cyan-300 px-3 py-1.5"
        >
          Forge your own →
        </Link>
      </div>
      {error && <p className="text-xs text-red-400 mt-3">{error}</p>}
    </div>
  );
}
