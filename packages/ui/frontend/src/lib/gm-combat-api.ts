// CF-9 — session combat tracker API client.
// Separate from lib/api.ts (shared surface) so the combat flow can land
// without touching the shared client; reuses its `req` helper.

import { req } from "@/lib/api";

export interface CombatantState {
  id: string;
  name: string;
  side: "pc" | "ally" | "enemy" | "neutral";
  hp: number;
  max_hp: number;
  temp_hp: number;
  initiative: number | null;
  conditions: string[];
  dead: boolean;
  unconscious: boolean;
  concentration: string | null;
  notes: string;
  entity_id: string | null;
}

export interface CombatSessionState {
  universe_id: string;
  session_id: string;
  status: "initializing" | "initiative" | "active" | "paused" | "resolved";
  round: number;
  turn_order: string[];
  combatants: CombatantState[];
  story_id: string | null;
  scene_id: string | null;
  started_at: string;
  ended_at: string | null;
}

export interface CombatantCreate {
  name: string;
  side?: CombatantState["side"];
  hp: number;
  max_hp: number;
  temp_hp?: number;
  conditions?: string[];
  notes?: string;
  entity_id?: string | null;
}

export interface CombatInitiativeEntry {
  combatant_id: string;
  initiative: number;
  tiebreak?: number;
}

export interface CombatInitiativeResponse {
  state: CombatSessionState;
  narration: string | null;
}

export interface CombatEndResponse {
  state: CombatSessionState;
  proposal_ids: string[];
  proposal_errors: string[];
  summary: string | null;
}

export interface ConditionExplanation {
  condition: string;
  source: string;
  description: string;
  mechanical_effects: string[];
  ends_when: string | null;
}

export interface CombatantPatch {
  hp?: number | null;
  hp_delta?: number | null;
  temp_hp?: number | null;
  conditions_add?: string[];
  conditions_remove?: string[];
  dead?: boolean | null;
  unconscious?: boolean | null;
  concentration?: string | null;
  notes?: string | null;
}

export const gmCombatApi = {
  /** Start (or restart) the encounter for (universe, session). */
  start: (body: {
    universe_id: string;
    session_id: string;
    combatants: CombatantCreate[];
    story_id?: string | null;
    scene_id?: string | null;
  }) => req<CombatSessionState>("/gm/combat/start", { method: "POST", body: JSON.stringify(body) }),

  /** Live encounter state; 404 (ApiError) when none exists. */
  get: (universeId: string, sessionId: string) =>
    req<CombatSessionState>(`/gm/combat/${encodeURIComponent(sessionId)}`, {
      query: { universe_id: universeId },
    }),

  setInitiative: (
    sessionId: string,
    body: { universe_id: string; entries: CombatInitiativeEntry[]; narrate?: boolean },
  ) =>
    req<CombatInitiativeResponse>(`/gm/combat/${encodeURIComponent(sessionId)}/initiative`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  updateCombatant: (sessionId: string, combatantId: string, body: { universe_id: string } & CombatantPatch) =>
    req<CombatSessionState>(
      `/gm/combat/${encodeURIComponent(sessionId)}/combatant/${encodeURIComponent(combatantId)}`,
      { method: "PATCH", body: JSON.stringify(body) },
    ),

  nextRound: (sessionId: string, universeId: string) =>
    req<CombatSessionState>(`/gm/combat/${encodeURIComponent(sessionId)}/next-round`, {
      method: "POST",
      body: JSON.stringify({ universe_id: universeId }),
    }),

  end: (
    sessionId: string,
    body: { universe_id: string; story_id?: string | null; scene_id?: string | null; world_effects?: string[] },
  ) =>
    req<CombatEndResponse>(`/gm/combat/${encodeURIComponent(sessionId)}/end`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  explainCondition: (body: { universe_id: string; condition: string; system_id?: string | null }) =>
    req<ConditionExplanation>("/gm/combat/condition-explain", {
      method: "POST",
      body: JSON.stringify(body),
    }),
};
