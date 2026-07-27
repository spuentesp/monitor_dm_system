/**
 * Shared confidence-tier definition for every canon review surface (F2-3).
 *
 * The backend does not define confidence tiers anywhere (checked
 * packages/ui/backend + data-layer), so the boundary is a frontend
 * convention. CanonReviewPanel used medium=0.6 while /forge/review used
 * medium=0.7; 0.7 is kept as canonical — it matches the pack review page,
 * which is the surface where triage-by-confidence matters most.
 */

export interface ConfidenceTier {
  min: number;
  label: string;
  color: string;
  bg: string;
}

export const CONFIDENCE_TIERS = {
  high: { min: 0.9, label: "High", color: "text-emerald-400", bg: "bg-emerald-500/20" },
  medium: { min: 0.7, label: "Medium", color: "text-amber-400", bg: "bg-amber-500/20" },
  low: { min: 0, label: "Low", color: "text-red-400", bg: "bg-red-500/20" },
} as const;

export function getConfidenceTier(confidence: number): ConfidenceTier {
  if (confidence >= CONFIDENCE_TIERS.high.min) return CONFIDENCE_TIERS.high;
  if (confidence >= CONFIDENCE_TIERS.medium.min) return CONFIDENCE_TIERS.medium;
  return CONFIDENCE_TIERS.low;
}
