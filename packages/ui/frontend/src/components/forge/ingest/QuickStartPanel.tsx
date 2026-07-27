"use client";

import { QuickSeedForm } from "@/components/forge/worlds/QuickSeedForm";

/**
 * Ingest Studio mount of the quick-seed world builder (F1-3a).
 * The form body lives in components/forge/worlds/QuickSeedForm.tsx so the
 * /forge/worlds/new wizard can embed the same UI.
 */
export function QuickStartPanel() {
  return <QuickSeedForm />;
}
