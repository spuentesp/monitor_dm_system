"use client";

import { Fragment } from "react";
import { ChevronRight, ClipboardList, Flag, Mic } from "lucide-react";
import { cn } from "@/lib/utils";

export type GmStep = "prep" | "run" | "wrap";

const STEPS: Array<{ id: GmStep; label: string; icon: typeof Mic }> = [
  { id: "prep", label: "Prep", icon: ClipboardList },
  { id: "run", label: "Run", icon: Mic },
  { id: "wrap", label: "Wrap-up", icon: Flag },
];

const STEP_STORAGE_PREFIX = "monitor.gm.step.";

/** localStorage key for the step remembered for a universe ("-" = none yet). */
export function gmStepStorageKey(universeId: string | null): string {
  return `${STEP_STORAGE_PREFIX}${universeId ?? "-"}`;
}

/** Read the persisted step for a universe. "wrap" is transient and never stored. */
export function readStoredGmStep(universeId: string | null): GmStep | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(gmStepStorageKey(universeId));
    return raw === "prep" || raw === "run" ? raw : null;
  } catch {
    return null;
  }
}

/** Persist the step for a universe; storage failures are ignored. */
export function writeStoredGmStep(universeId: string | null, step: GmStep): void {
  if (typeof window === "undefined") return;
  if (step === "wrap") return; // transient — only opens the wrap-up modal
  try {
    window.localStorage.setItem(gmStepStorageKey(universeId), step);
  } catch {
    // localStorage unavailable (private mode / quota) — the step still works in-memory.
  }
}

/**
 * Prep → Run → Wrap-up stepper shown atop /gm. "wrap" is an action that opens
 * the wrap-up modal rather than a resting view; prep/run are persisted per
 * universe by the page via readStoredGmStep/writeStoredGmStep.
 */
export function GmStepper({
  step,
  onStepChange,
  wrapDisabled,
}: {
  step: GmStep;
  onStepChange: (step: GmStep) => void;
  wrapDisabled?: boolean;
}) {
  return (
    <nav aria-label="Session flow" className="flex items-center gap-1">
      {STEPS.map(({ id, label, icon: Icon }, i) => (
        <Fragment key={id}>
          {i > 0 && <ChevronRight className="w-3 h-3 text-slate-700 flex-shrink-0" aria-hidden />}
          <button
            type="button"
            data-testid={`gm-step-${id}`}
            onClick={() => onStepChange(id)}
            disabled={id === "wrap" && wrapDisabled}
            aria-current={step === id ? "step" : undefined}
            title={id === "wrap" && wrapDisabled ? "Select a universe first" : undefined}
            className={cn(
              "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all border max-xl:min-h-11",
              step === id
                ? "bg-emerald-500/10 text-emerald-300 border-emerald-500/25"
                : "text-slate-500 hover:text-slate-300 border-transparent hover:bg-white/4",
              id === "wrap" && wrapDisabled && "opacity-40 cursor-not-allowed",
            )}
          >
            <Icon className="w-3.5 h-3.5" />
            {label}
          </button>
        </Fragment>
      ))}
    </nav>
  );
}
