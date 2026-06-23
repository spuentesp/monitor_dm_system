import { Plus, Pencil, Trash2, Link2, Tag } from "lucide-react";
import type { LucideIcon } from "lucide-react";

/**
 * Pure change-type → icon/colour mapping for the Q-10 audit trail (HistoryTab).
 * Extracted so the branching logic is unit-testable without rendering.
 */

export function changeIcon(changeType: string): LucideIcon {
  if (changeType.startsWith("created") || changeType.includes("added")) return Plus;
  if (changeType.startsWith("deleted") || changeType.includes("removed")) return Trash2;
  if (changeType.includes("relationship")) return Link2;
  if (changeType.includes("state_tag")) return Tag;
  return Pencil;
}

export function changeColor(changeType: string): string {
  if (changeType.startsWith("created") || changeType.includes("added")) return "text-emerald-400";
  if (changeType.startsWith("deleted") || changeType.includes("removed")) return "text-rose-400";
  if (changeType.includes("retcon")) return "text-amber-400";
  return "text-cyan-400";
}
