/**
 * Pure working-state readers for CombatPanel. Generic over whatever numeric
 * stats the game system exposes — extracted so the parsing is unit-testable.
 */

export function flattenStats(state: Record<string, unknown>): Record<string, number> {
  const out: Record<string, number> = {};
  for (const [rawKey, value] of Object.entries(state)) {
    const label = rawKey.replace(/_/g, " ");
    if (typeof value === "number") {
      out[label] = value;
    } else if (value && typeof value === "object" && !Array.isArray(value)) {
      const v = value as Record<string, unknown>;
      if (typeof v.current === "number") {
        out[label] = v.current;
      } else {
        for (const [k2, v2] of Object.entries(v)) {
          if (typeof v2 === "number") out[`${label} ${k2.replace(/_/g, " ")}`] = v2;
        }
      }
    }
  }
  return out;
}

export interface Progression {
  xp?: number;
  xpMax?: number;
  level?: number | string;
}

/** Pull an XP/level/progression view out of the working state, if present. */
export function readProgression(state: Record<string, unknown>): Progression | null {
  let xp: number | undefined;
  let xpMax: number | undefined;
  let level: number | string | undefined;

  for (const [rawKey, value] of Object.entries(state)) {
    const key = rawKey.toLowerCase();
    if (key.includes("xp") || key.includes("experience")) {
      if (typeof value === "number") xp = value;
      else if (value && typeof value === "object") {
        const v = value as Record<string, unknown>;
        if (typeof v.current === "number") xp = v.current;
        if (typeof v.max === "number") xpMax = v.max;
        if (typeof v.next === "number") xpMax = v.next;
      }
    }
    if (key === "level" || key.endsWith("_level")) {
      if (typeof value === "number" || typeof value === "string") level = value;
    }
  }
  if (xp === undefined && level === undefined) return null;
  return { xp, xpMax, level };
}
