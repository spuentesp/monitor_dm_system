"use client";

import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  ChevronDown,
  ChevronUp,
  Dices,
  Loader2,
  Skull,
  Swords,
  HelpCircle,
} from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, gmApi, storiesApi } from "@/lib/api";
import {
  gmCombatApi,
  type CombatantCreate,
  type CombatSessionState,
  type ConditionExplanation,
} from "@/lib/gm-combat-api";
import { errorMessage } from "@/lib/errors";
import { uuid } from "@/lib/uuid";
import { cn } from "@/lib/utils";

/**
 * Combat tracker (CF-9): start → initiative → rounds with damage/conditions →
 * end, without leaving the /gm page. State is ephemeral server-side session
 * state keyed by (universe, session); ending stages ProposedChange items for
 * the CF-8 queue (casualties + GM-typed world effects). Dice for damage/heal
 * roll server-side through the existing POST /gm/roll.
 */

interface DraftRow {
  key: string;
  name: string;
  side: "pc" | "enemy";
  hp: string;
  maxHp: string;
}

const EMPTY_ROW = (): DraftRow => ({ key: uuid(), name: "", side: "enemy", hp: "", maxHp: "" });

const DICE_RE = /^(\d+)?d(\d+)([+-]\d+)?$/;

function sessionKey(universeId: string): string {
  return `monitor.gm.combatSession:${universeId}`;
}

export function CombatPanel({
  universeId,
  systemId,
}: {
  universeId: string | null;
  systemId?: string | null;
}) {
  const qc = useQueryClient();
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [rows, setRows] = useState<DraftRow[]>([EMPTY_ROW()]);
  const [storyId, setStoryId] = useState("");
  const [error, setError] = useState<string | null>(null);

  // Tracker view state
  const [initiativeDraft, setInitiativeDraft] = useState<Record<string, string>>({});
  const [narrate, setNarrate] = useState(false);
  const [narration, setNarration] = useState<string | null>(null);
  const [rollDrafts, setRollDrafts] = useState<Record<string, string>>({});
  const [conditionDrafts, setConditionDrafts] = useState<Record<string, string>>({});
  const [worldEffects, setWorldEffects] = useState("");
  const [explanation, setExplanation] = useState<{
    combatantId: string;
    condition: string;
    detail: ConditionExplanation;
  } | null>(null);
  const [endResult, setEndResult] = useState<{
    proposalIds: string[];
    proposalErrors: string[];
    summary: string | null;
  } | null>(null);

  // Restore the stored session for this universe (if any).
  useEffect(() => {
    if (!universeId) {
      setSessionId(null);
      return;
    }
    setSessionId(localStorage.getItem(sessionKey(universeId)));
  }, [universeId]);

  const { data: state, isLoading, error: stateError } = useQuery({
    queryKey: ["gm-combat", universeId, sessionId],
    queryFn: () => gmCombatApi.get(universeId!, sessionId!),
    enabled: !!universeId && !!sessionId,
    retry: false,
  });

  const missingEncounter =
    !!stateError && stateError instanceof ApiError && stateError.status === 404;

  // A stored session with no server-side state: forget it and show Start.
  useEffect(() => {
    if (missingEncounter && universeId) {
      localStorage.removeItem(sessionKey(universeId));
      setSessionId(null);
    }
  }, [missingEncounter, universeId]);

  const { data: stories } = useQuery({
    queryKey: ["stories", universeId],
    queryFn: () => storiesApi.listStories({ universe_id: universeId!, limit: 100 }),
    enabled: !!universeId,
  });
  useEffect(() => {
    const list = stories?.stories ?? [];
    if (!storyId && list.length > 0) setStoryId(list[0].id);
    if (storyId && list.length > 0 && !list.some((s) => s.id === storyId)) {
      setStoryId(list[0].id);
    }
  }, [stories, storyId]);

  const start = useMutation({
    mutationFn: (combatants: CombatantCreate[]) =>
      gmCombatApi.start({
        universe_id: universeId!,
        session_id: uuid(),
        combatants,
        story_id: storyId || null,
      }),
    onSuccess: (created) => {
      localStorage.setItem(sessionKey(universeId!), created.session_id);
      setSessionId(created.session_id);
      setRows([EMPTY_ROW()]);
      setError(null);
      setEndResult(null);
      setNarration(null);
      qc.invalidateQueries({ queryKey: ["gm-combat"] });
    },
    onError: (e) => setError(errorMessage(e)),
  });

  const setInitiative = useMutation({
    mutationFn: () =>
      gmCombatApi.setInitiative(sessionId!, {
        universe_id: universeId!,
        entries: (state?.combatants ?? []).flatMap((c) => {
          const raw = (initiativeDraft[c.id] ?? "").trim();
          if (!raw) return [];
          const value = Number(raw);
          if (Number.isNaN(value)) return [];
          return [{ combatant_id: c.id, initiative: value }];
        }),
        narrate,
      }),
    onSuccess: (res) => {
      setNarration(res.narration);
      qc.setQueryData(["gm-combat", universeId, sessionId], res.state);
    },
    onError: (e) => setError(errorMessage(e)),
  });

  const patchCombatant = useMutation({
    mutationFn: ({ combatantId, ...patch }: { combatantId: string } & Record<string, unknown>) =>
      gmCombatApi.updateCombatant(sessionId!, combatantId, {
        universe_id: universeId!,
        ...patch,
      }),
    onSuccess: (updated) => {
      qc.setQueryData(["gm-combat", universeId, sessionId], updated);
      setError(null);
    },
    onError: (e) => setError(errorMessage(e)),
  });

  const nextRound = useMutation({
    mutationFn: () => gmCombatApi.nextRound(sessionId!, universeId!),
    onSuccess: (updated) => {
      qc.setQueryData(["gm-combat", universeId, sessionId], updated);
      setNarration(null);
    },
    onError: (e) => setError(errorMessage(e)),
  });

  const endEncounter = useMutation({
    mutationFn: () =>
      gmCombatApi.end(sessionId!, {
        universe_id: universeId!,
        story_id: storyId || null,
        world_effects: worldEffects
          .split("\n")
          .map((l) => l.trim())
          .filter(Boolean),
      }),
    onSuccess: (res) => {
      qc.setQueryData(["gm-combat", universeId, sessionId], res.state);
      setEndResult({
        proposalIds: res.proposal_ids,
        proposalErrors: res.proposal_errors,
        summary: res.summary,
      });
      setWorldEffects("");
    },
    onError: (e) => setError(errorMessage(e)),
  });

  const explain = useMutation({
    mutationFn: ({ combatantId, condition }: { combatantId: string; condition: string }) =>
      gmCombatApi.explainCondition({
        universe_id: universeId!,
        condition,
        system_id: systemId ?? null,
      }),
    onSuccess: (detail, vars) =>
      setExplanation({ combatantId: vars.combatantId, condition: vars.condition, detail }),
    onError: (e) => setError(errorMessage(e)),
  });

  const rollAndPatch = async (
    combatantId: string,
    mode: "damage" | "heal",
  ): Promise<void> => {
    const raw = (rollDrafts[combatantId] ?? "").trim();
    if (!raw) return;
    let amount: number;
    if (DICE_RE.test(raw)) {
      const roll = await gmApi.rollDice(raw.toLowerCase().replace(/\s/g, ""));
      amount = roll.total;
    } else {
      amount = Number(raw);
      if (Number.isNaN(amount) || amount <= 0) {
        setError(`'${raw}' is not a dice expression or positive number`);
        return;
      }
    }
    setRollDrafts((d) => ({ ...d, [combatantId]: "" }));
    await patchCombatant.mutateAsync({
      combatantId,
      hp_delta: mode === "damage" ? -amount : amount,
    });
  };

  const draftTotal = useMemo(
    () => rows.reduce((n, r) => n + (Number(r.hp) > 0 && Number(r.maxHp) > 0 ? 1 : 0), 0),
    [rows],
  );

  if (!universeId) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 p-6 text-center">
        <Swords className="h-8 w-8 text-slate-700" />
        <p className="text-xs text-slate-600">Select a universe to run an encounter</p>
      </div>
    );
  }

  // ------------------------------------------------------------------
  // Start view: no live encounter
  // ------------------------------------------------------------------
  if (!sessionId || missingEncounter || (!state && !isLoading)) {
    return (
      <div className="flex h-full flex-col overflow-hidden">
        <div className="flex items-center gap-2 px-4 py-3 border-b border-white/5">
          <Swords className="h-3.5 w-3.5 text-emerald-400" />
          <span className="text-xs font-semibold flex-1">Combat — new encounter</span>
          <select
            value={storyId}
            onChange={(e) => setStoryId(e.target.value)}
            className="input-cyber py-1 text-xs min-w-[120px]"
            title="Story scope for end-of-encounter proposals"
          >
            <option value="">No story…</option>
            {(stories?.stories ?? []).map((s) => (
              <option key={s.id} value={s.id}>
                {s.title}
              </option>
            ))}
          </select>
          <button
            onClick={() => start.mutate(buildCombatants(rows))}
            disabled={start.isPending || draftTotal === 0}
            className={cn(
              "btn-cyber text-xs py-1 px-3",
              (start.isPending || draftTotal === 0) && "opacity-40 cursor-not-allowed",
            )}
            title={draftTotal === 0 ? "Add at least one combatant with HP" : "Start encounter"}
          >
            {start.isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : <Swords className="h-3 w-3" />}
            Start
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
          {error && <p className="text-[10px] text-red-400">{error}</p>}
          <p className="text-[10px] text-slate-500">
            Add the combatants for tonight&apos;s encounter. Ending the fight stages casualty and
            world-effect proposals in the Canon Review queue (CF-8).
          </p>
          {rows.map((row, i) => (
            <div key={row.key} className="glass-dark rounded-xl border border-white/5 p-2.5 space-y-2">
              <div className="flex items-center gap-1.5">
                <input
                  value={row.name}
                  onChange={(e) => updateRow(rows, setRows, i, { name: e.target.value })}
                  placeholder="Name (e.g. Mira, Goblin Boss)"
                  className="input-cyber flex-1 py-1 text-xs"
                />
                <select
                  value={row.side}
                  onChange={(e) =>
                    updateRow(rows, setRows, i, { side: e.target.value as DraftRow["side"] })
                  }
                  className="input-cyber py-1 text-xs"
                >
                  <option value="enemy">Enemy</option>
                  <option value="pc">PC</option>
                </select>
                <button
                  onClick={() => setRows(rows.filter((_, j) => j !== i))}
                  aria-label="Remove combatant"
                  className="text-slate-600 hover:text-red-400 text-xs px-1"
                >
                  ✕
                </button>
              </div>
              <div className="flex items-center gap-1.5">
                <input
                  value={row.hp}
                  onChange={(e) => updateRow(rows, setRows, i, { hp: e.target.value })}
                  placeholder="HP"
                  inputMode="numeric"
                  className="input-cyber w-16 py-1 text-xs"
                />
                <span className="text-[10px] text-slate-600">/</span>
                <input
                  value={row.maxHp}
                  onChange={(e) => updateRow(rows, setRows, i, { maxHp: e.target.value })}
                  placeholder="Max"
                  inputMode="numeric"
                  className="input-cyber w-16 py-1 text-xs"
                />
              </div>
            </div>
          ))}
          <button
            onClick={() => setRows([...rows, EMPTY_ROW()])}
            className="w-full rounded-lg border border-dashed border-white/10 py-1.5 text-[10px] text-slate-500 hover:text-slate-300"
          >
            + Add combatant
          </button>
        </div>
      </div>
    );
  }

  if (isLoading || !state) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="h-5 w-5 animate-spin text-slate-600" />
      </div>
    );
  }

  // ------------------------------------------------------------------
  // Tracker view: live encounter
  // ------------------------------------------------------------------
  const ordered = orderCombatants(state);
  const resolved = state.status === "resolved";

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <div className="flex items-center gap-2 px-4 py-3 border-b border-white/5">
        <Swords className="h-3.5 w-3.5 text-emerald-400" />
        <span className="text-xs font-semibold flex-1">
          Round {state.round}
          <span
            className={cn(
              "ml-2 text-[9px] uppercase tracking-wider",
              resolved ? "text-slate-500" : "text-emerald-400",
            )}
          >
            {state.status}
          </span>
        </span>
        {!resolved && (
          <>
            <button
              onClick={() => nextRound.mutate()}
              disabled={nextRound.isPending}
              className="btn-cyber text-xs py-1 px-2"
              title="Advance to the next round"
            >
              {nextRound.isPending ? (
                <Loader2 className="h-3 w-3 animate-spin" />
              ) : (
                <ChevronDown className="h-3 w-3" />
              )}
              Round
            </button>
            <button
              onClick={() => endEncounter.mutate()}
              disabled={endEncounter.isPending}
              className="btn-cyber text-xs py-1 px-2"
              title="End the encounter and stage world effects"
            >
              {endEncounter.isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : <Skull className="h-3 w-3" />}
              End
            </button>
          </>
        )}
        {!resolved && (
          <button
            onClick={() => {
              localStorage.removeItem(sessionKey(universeId));
              setSessionId(null);
              setEndResult(null);
              setNarration(null);
            }}
            aria-label="Abandon encounter"
            className="text-slate-600 hover:text-red-400 text-[10px]"
            title="Abandon and start over (does not stage proposals)"
          >
            ✕
          </button>
        )}
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
        {error && <p className="text-[10px] text-red-400">{error}</p>}

        {endResult && (
          <div className="glass-dark rounded-xl border border-emerald-500/20 p-2.5 space-y-1">
            <p className="text-[10px] font-semibold text-emerald-300">Encounter ended</p>
            {endResult.summary && (
              <p className="text-[11px] text-slate-300 leading-relaxed">{endResult.summary}</p>
            )}
            {endResult.proposalIds.length > 0 && (
              <p className="text-[10px] text-slate-400">
                {endResult.proposalIds.length} proposal(s) staged in the Canon Review queue.
              </p>
            )}
            {endResult.proposalErrors.map((err, i) => (
              <p key={i} className="text-[10px] text-amber-300">
                not staged: {err}
              </p>
            ))}
          </div>
        )}

        {narration && (
          <p className="text-[11px] italic text-slate-400 border-l-2 border-emerald-500/40 pl-2">
            {narration}
          </p>
        )}

        {!resolved && (
          <div className="glass-dark rounded-xl border border-white/5 p-2.5 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-[10px] uppercase tracking-wider text-slate-500 font-bold">
                Initiative
              </span>
              <label className="flex items-center gap-1 text-[10px] text-slate-500">
                <input
                  type="checkbox"
                  checked={narrate}
                  onChange={(e) => setNarrate(e.target.checked)}
                  className="h-3 w-3 accent-emerald-400"
                />
                narrate
              </label>
            </div>
            {ordered.map((c) => (
              <div key={c.id} className="flex items-center gap-1.5">
                <span className="text-[11px] text-slate-300 flex-1 truncate">{c.name}</span>
                <input
                  value={initiativeDraft[c.id] ?? ""}
                  onChange={(e) =>
                    setInitiativeDraft((d) => ({ ...d, [c.id]: e.target.value }))
                  }
                  placeholder="init"
                  inputMode="numeric"
                  className="input-cyber w-14 py-0.5 text-[10px]"
                  aria-label={`Initiative for ${c.name}`}
                />
              </div>
            ))}
            <button
              onClick={() => setInitiative.mutate()}
              disabled={setInitiative.isPending}
              className="w-full btn-cyber text-xs py-1"
            >
              {setInitiative.isPending ? (
                <Loader2 className="h-3 w-3 animate-spin mx-auto" />
              ) : (
                "Set order"
              )}
            </button>
          </div>
        )}

        {ordered.map((c) => (
          <div
            key={c.id}
            className={cn(
              "glass-dark rounded-xl border p-2.5 space-y-2",
              c.dead ? "border-red-500/30 opacity-70" : "border-white/5",
            )}
          >
            <div className="flex items-center gap-1.5">
              <span className={cn("text-xs font-semibold flex-1", c.dead ? "text-red-400 line-through" : "text-slate-200")}>
                {c.name}
              </span>
              <span className="text-[9px] uppercase tracking-wider text-slate-600">{c.side}</span>
              <span
                className={cn(
                  "text-[11px] font-mono",
                  c.hp === 0 ? "text-red-400" : c.hp <= c.max_hp / 4 ? "text-amber-300" : "text-emerald-300",
                )}
              >
                {c.hp}/{c.max_hp}
                {c.temp_hp > 0 && <span className="text-cyan-300"> +{c.temp_hp}t</span>}
              </span>
              {c.initiative !== null && (
                <span className="text-[9px] font-mono text-slate-500">init {c.initiative}</span>
              )}
            </div>

            {c.concentration && (
              <p className="text-[10px] text-cyan-300/90">concentration: {c.concentration}</p>
            )}

            {c.conditions.length > 0 && (
              <div className="flex flex-wrap gap-1">
                {c.conditions.map((cond) => (
                  <button
                    key={cond}
                    onClick={() => explain.mutate({ combatantId: c.id, condition: cond })}
                    className="group inline-flex items-center gap-0.5 text-[9px] bg-purple-500/10 text-purple-300 px-1.5 py-0.5 rounded hover:bg-purple-500/20"
                    title="What does this condition do?"
                  >
                    {cond}
                    <HelpCircle className="h-2.5 w-2.5 opacity-50 group-hover:opacity-100" />
                  </button>
                ))}
              </div>
            )}

            {explanation?.combatantId === c.id && (
              <div className="rounded bg-black/30 border border-white/5 p-1.5 space-y-0.5">
                <p className="text-[9px] uppercase tracking-wider text-slate-500">
                  {explanation.detail.condition} · {explanation.detail.source}
                </p>
                <p className="text-[10px] text-slate-300 leading-relaxed">
                  {explanation.detail.description}
                </p>
                {explanation.detail.ends_when && (
                  <p className="text-[9px] text-slate-500">ends: {explanation.detail.ends_when}</p>
                )}
              </div>
            )}

            {!resolved && (
              <>
                <div className="flex items-center gap-1.5">
                  <input
                    value={rollDrafts[c.id] ?? ""}
                    onChange={(e) =>
                      setRollDrafts((d) => ({ ...d, [c.id]: e.target.value }))
                    }
                    placeholder="1d8+3 or 5"
                    className="input-cyber flex-1 py-1 text-[10px] font-mono"
                    aria-label={`Damage or heal amount for ${c.name}`}
                  />
                  <button
                    onClick={() => rollAndPatch(c.id, "damage")}
                    className="text-[10px] px-2 py-1 rounded border border-red-500/30 text-red-300 hover:bg-red-500/10"
                    title="Apply as damage (rolls dice server-side)"
                  >
                    Dmg
                  </button>
                  <button
                    onClick={() => rollAndPatch(c.id, "heal")}
                    className="text-[10px] px-2 py-1 rounded border border-emerald-500/30 text-emerald-300 hover:bg-emerald-500/10"
                    title="Apply as healing (rolls dice server-side)"
                  >
                    Heal
                  </button>
                </div>

                <div className="flex items-center gap-1.5">
                  <input
                    value={conditionDrafts[c.id] ?? ""}
                    onChange={(e) =>
                      setConditionDrafts((d) => ({ ...d, [c.id]: e.target.value }))
                    }
                    onKeyDown={(e) => {
                      if (e.key !== "Enter") return;
                      const v = (conditionDrafts[c.id] ?? "").trim();
                      if (!v) return;
                      setConditionDrafts((d) => ({ ...d, [c.id]: "" }));
                      patchCombatant.mutate({ combatantId: c.id, conditions_add: [v] });
                    }}
                    placeholder="add condition…"
                    className="input-cyber flex-1 py-1 text-[10px]"
                    aria-label={`Add condition to ${c.name}`}
                  />
                  <label className="flex items-center gap-1 text-[9px] text-slate-500">
                    <input
                      type="checkbox"
                      checked={c.unconscious}
                      onChange={(e) =>
                        patchCombatant.mutate({ combatantId: c.id, unconscious: e.target.checked })
                      }
                      className="h-3 w-3 accent-amber-400"
                    />
                    unconc.
                  </label>
                  <label className="flex items-center gap-1 text-[9px] text-slate-500">
                    <input
                      type="checkbox"
                      checked={c.dead}
                      onChange={(e) =>
                        patchCombatant.mutate({ combatantId: c.id, dead: e.target.checked })
                      }
                      className="h-3 w-3 accent-red-500"
                    />
                    dead
                  </label>
                </div>

                {c.conditions.length > 0 && (
                  <div className="flex flex-wrap gap-1">
                    {c.conditions.map((cond) => (
                      <button
                        key={`rm-${cond}`}
                        onClick={() =>
                          patchCombatant.mutate({ combatantId: c.id, conditions_remove: [cond] })
                        }
                        className="text-[9px] bg-purple-500/10 text-purple-400 px-1.5 py-0.5 rounded hover:bg-red-500/20 hover:text-red-300"
                        title="Remove condition"
                      >
                        {cond} ✕
                      </button>
                    ))}
                  </div>
                )}
              </>
            )}
          </div>
        ))}

        {!resolved && (
          <div className="glass-dark rounded-xl border border-white/5 p-2.5 space-y-1.5">
            <span className="text-[10px] uppercase tracking-wider text-slate-500 font-bold">
              Aftermath (one per line)
            </span>
            <textarea
              value={worldEffects}
              onChange={(e) => setWorldEffects(e.target.value)}
              placeholder={"The goblin warband swears vengeance\nThe guard captain owes the party a favor"}
              className="input-cyber w-full h-16 resize-none text-[10px] font-mono"
            />
            <p className="text-[9px] text-slate-600">
              Staged as Canon Review proposals when the encounter ends.
            </p>
          </div>
        )}
      </div>

      {patchCombatant.isError && (
        <div className="px-4 py-2 border-t border-white/5">
          <AlertTriangle className="h-3 w-3 text-amber-400 inline mr-1" />
          <span className="text-[10px] text-amber-300">{errorMessage(patchCombatant.error)}</span>
        </div>
      )}
      <div className="px-4 py-2 border-t border-white/5 flex items-center gap-2 text-[9px] text-slate-600">
        <Dices className="h-3 w-3" />
        Damage/heal dice roll on the server via /gm/roll
      </div>
    </div>
  );
}

function buildCombatants(rows: DraftRow[]): CombatantCreate[] {
  return rows.flatMap((r) => {
    const hp = Number(r.hp);
    const maxHp = Number(r.maxHp);
    if (!r.name.trim() || Number.isNaN(hp) || Number.isNaN(maxHp) || maxHp <= 0) return [];
    return [
      {
        name: r.name.trim(),
        side: r.side,
        hp: Math.max(0, hp),
        max_hp: maxHp,
      },
    ];
  });
}

function updateRow(
  rows: DraftRow[],
  setRows: (r: DraftRow[]) => void,
  i: number,
  patch: Partial<DraftRow>,
): void {
  setRows(rows.map((row, j) => (j === i ? { ...row, ...patch } : row)));
}

/** Server already sorts on set_initiative; keep a stable, sensible display order. */
function orderCombatants(state: CombatSessionState) {
  if (state.turn_order.length === 0) return state.combatants;
  const byId = new Map(state.combatants.map((c) => [c.id, c]));
  const ordered = state.turn_order.flatMap((id) => {
    const c = byId.get(id);
    return c ? [c] : [];
  });
  const inOrder = new Set(ordered.map((c) => c.id));
  return [...ordered, ...state.combatants.filter((c) => !inOrder.has(c.id))];
}
