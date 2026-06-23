/**
 * Pure working-state → display-chip projection for the Play console.
 * Generic over arbitrary game-system stats/tags; capped for display.
 * Extracted so the projection is unit-testable without rendering.
 */

export interface WorkingStateChip {
  label: string;
  value: string;
  kind: "stat" | "tag";
}

export function workingStateChips(state: Record<string, unknown>): WorkingStateChip[] {
  const chips: WorkingStateChip[] = [];
  for (const [rawKey, value] of Object.entries(state)) {
    const label = rawKey.replace(/_/g, " ");
    if (typeof value === "number" || typeof value === "string") {
      chips.push({ label, value: String(value), kind: "stat" });
    } else if (Array.isArray(value)) {
      for (const item of value.slice(0, 6)) {
        chips.push({ label: String(item).replace(/_/g, " "), value: "", kind: "tag" });
      }
    } else if (value && typeof value === "object") {
      const v = value as Record<string, unknown>;
      if (typeof v.current === "number" && typeof v.max === "number") {
        chips.push({ label, value: `${v.current}/${v.max}`, kind: "stat" });
      } else {
        for (const [k2, v2] of Object.entries(v).slice(0, 6)) {
          if (typeof v2 === "number" || typeof v2 === "string") {
            chips.push({ label: `${label} ${k2.replace(/_/g, " ")}`, value: String(v2), kind: "stat" });
          }
        }
      }
    }
  }
  return chips.slice(0, 14);
}
