"use client";

import { useState } from "react";
import Link from "next/link";
import { ClipboardList, Dices, Mic, BookOpen, X } from "lucide-react";

export const TOUR_DISMISS_KEY = "monitor.gm.tour.v1";

export function isTourDismissed(): boolean {
  if (typeof window === "undefined") return false;
  try {
    return window.localStorage.getItem(TOUR_DISMISS_KEY) === "dismissed";
  } catch {
    return false;
  }
}

export function dismissTour(): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(TOUR_DISMISS_KEY, "dismissed");
  } catch {
    // storage unavailable — the tour will show again next visit
  }
}

/**
 * First-run state: no universe selected yet. Instead of a wall of empty
 * panels, walk the GM through the three things that make the assistant work.
 * Deliberately does not list universe names (the selector above owns those).
 */
export function FirstRunGuide() {
  return (
    <div
      data-testid="first-run-guide"
      className="flex-1 overflow-y-auto flex flex-col items-center justify-center text-center space-y-5 px-6 py-8"
    >
      <div className="space-y-1.5">
        <ClipboardList className="w-8 h-8 text-emerald-400 mx-auto" />
        <h2 className="text-sm font-bold text-slate-200">Set up your table</h2>
        <p className="text-xs text-slate-500 max-w-sm">
          GM Assistant works against a world. Pick one to unlock the recorder,
          dice, rules and prep panels.
        </p>
      </div>
      <ol className="space-y-2 text-left max-w-sm w-full">
        {[
          "Pick a world in the universe selector in the header — or create one in Forge.",
          "Choose the RPG system your table plays; the Rules panel follows it.",
          "Stay on Run and use the Session Recorder to log what happens at the table.",
        ].map((step, i) => (
          <li key={i} className="flex items-start gap-2 text-xs text-slate-400">
            <span className="flex-shrink-0 w-5 h-5 rounded-full bg-emerald-500/15 text-emerald-300 text-[10px] font-bold flex items-center justify-center">
              {i + 1}
            </span>
            <span className="leading-relaxed">{step}</span>
          </li>
        ))}
      </ol>
      <Link
        href="/forge"
        className="btn-cyber text-xs px-4 py-2 inline-flex items-center gap-1.5"
      >
        Create a world in Forge
      </Link>
    </div>
  );
}

/**
 * Small dismissible first-use tour card (dice, rules lookup, recorder).
 * Dismissal is remembered in localStorage; storage failures just mean the
 * card shows again next visit.
 */
export function FirstUseTour() {
  const [dismissed, setDismissed] = useState<boolean>(() => isTourDismissed());
  if (dismissed) return null;

  const dismiss = () => {
    dismissTour();
    setDismissed(true);
  };

  const items = [
    { icon: Dices, text: "Dice roller on the right — quick dice or an expression like 2d6+3. Press r to jump to it." },
    { icon: BookOpen, text: "Rules lookup on the left — follows your selected world's RPG system." },
    { icon: Mic, text: "Session recorder in the center — log what happens at the table. Press n for a scratchpad note, j/k to step through entries." },
  ];

  return (
    <div
      data-testid="first-use-tour"
      className="mx-6 my-3 rounded-xl border border-cyan-500/20 bg-cyan-500/5 px-4 py-3 flex-shrink-0"
      role="note"
    >
      <div className="flex items-start gap-3">
        <div className="flex-1 space-y-1.5 min-w-0">
          <p className="text-xs font-bold text-slate-200">New to GM Assistant?</p>
          <ul className="space-y-1">
            {items.map(({ icon: Icon, text }) => (
              <li key={text} className="flex items-start gap-2 text-[11px] text-slate-400">
                <Icon className="w-3 h-3 text-cyan-400 flex-shrink-0 mt-0.5" />
                <span>{text}</span>
              </li>
            ))}
          </ul>
        </div>
        <button
          type="button"
          onClick={dismiss}
          aria-label="Dismiss tour"
          className="flex-shrink-0 rounded-lg border border-white/10 p-1.5 text-slate-500 hover:text-slate-200 hover:bg-white/5 transition-all max-xl:min-h-11 max-xl:min-w-11"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  );
}
