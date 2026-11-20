import { chatApi, entitiesApi, universesApi } from "@/lib/api";
import type { RPGSystem, Session, Universe } from "@/lib/types";

export type QuickStartPayload = Parameters<typeof chatApi.createSession>[0];

/**
 * Build a one-click Quick start session payload with the same defaults the
 * advanced SetupPanel starts from:
 *
 * - first available universe (Quick start cannot ask, so it picks the first)
 * - first rules system (SetupPanel auto-selects systems[0] the same way)
 * - tone "dramatic", narrative (no dice) play, Autonomous GM mode
 * - no bound character — Session Zero creates one
 *
 * Throws when the account has no universe yet (there is nothing to bind a
 * session to).
 */
export async function buildQuickStartPayload(): Promise<QuickStartPayload> {
  const [universes, systems] = await Promise.all([
    universesApi.listUniverses(),
    // Systems are optional: fall back to the server default when the
    // catalog can't be read rather than failing the whole quick start.
    entitiesApi.listSystems().catch(() => [] as RPGSystem[]),
  ]);
  const universe: Universe | undefined = universes[0];
  if (!universe) {
    throw new Error("No worlds yet — create a world before starting a campaign.");
  }
  const system = systems[0];
  return {
    title: `New ${universe.name} campaign`,
    mode: "autonomous_gm",
    tone: "dramatic",
    play_mode: "narrative",
    multiverse_id: universe.multiverse_id ?? null,
    multiverse_label: null,
    universe_id: universe.id,
    universe_label: universe.name,
    system_id: system?.id ?? null,
    system_label: system?.name ?? null,
  };
}

/** Create the Quick start session and return it (caller navigates/activates). */
export async function createQuickStartSession(): Promise<Session> {
  return chatApi.createSession(await buildQuickStartPayload());
}
