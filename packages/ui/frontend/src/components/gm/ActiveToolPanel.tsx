"use client";

import { PrepToTablePanel } from "@/components/gm/PrepToTablePanel";
import { TableLookupsPanel } from "@/components/gm/TableLookupsPanel";
import { CombatPanel } from "@/components/gm/CombatPanel";
import { SessionLogPanel } from "@/components/gm/SessionLogPanel";
import { AskTheWorldPanel } from "@/components/gm/AskTheWorldPanel";
import { PlotHooksPanel } from "@/components/gm/PlotHooksPanel";
import { ThreadsPanel } from "@/components/gm/ThreadsPanel";
import { ContradictionsPanel } from "@/components/gm/ContradictionsPanel";
import { SessionPrepPanel } from "@/components/gm/SessionPrepPanel";
import { HandoutsPanel } from "@/components/gm/HandoutsPanel";

export type GmToolPanelId =
  | "prep-table"
  | "lookups"
  | "combat"
  | "session-log"
  | "ask-world"
  | "hooks"
  | "threads"
  | "contradictions"
  | "session-prep"
  | "handouts";

/**
 * Renders the body of the active GM tool panel. Shared by the desktop tools
 * column and the narrow single-panel view so panel wiring lives in one place.
 */
export function ActiveToolPanel({
  panelId,
  universeId,
  systemId,
}: {
  panelId: GmToolPanelId | null;
  universeId: string | null;
  systemId: string | null;
}) {
  switch (panelId) {
    case "prep-table":
      return <PrepToTablePanel universeId={universeId} />;
    case "lookups":
      return <TableLookupsPanel universeId={universeId} systemId={systemId} />;
    case "combat":
      return <CombatPanel universeId={universeId} systemId={systemId} />;
    case "session-log":
      return <SessionLogPanel universeId={universeId} />;
    case "ask-world":
      return <AskTheWorldPanel universeId={universeId} />;
    case "hooks":
      return <PlotHooksPanel universeId={universeId} />;
    case "threads":
      return <ThreadsPanel universeId={universeId} />;
    case "contradictions":
      return <ContradictionsPanel universeId={universeId} />;
    case "session-prep":
      return <SessionPrepPanel universeId={universeId} />;
    case "handouts":
      return <HandoutsPanel universeId={universeId} />;
    default:
      return null;
  }
}
