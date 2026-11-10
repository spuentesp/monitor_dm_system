"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Flag, Loader2, Rocket } from "lucide-react";
import { chatApi, universesApi } from "@/lib/api";
import { lightRpApi, type GraduatePrepareResult, type GraduateResult } from "@/lib/lightRpApi";
import { useNotify } from "@/components/NotificationProvider";
import { errorMessage } from "@/lib/errors";
import type { Session, StandaloneCharacter } from "@/lib/types";

/**
 * "Start a campaign with this character" — hands the character, persona and
 * memories to the guided start (Phase 2) in a chosen universe.
 *
 * Flow: pick a universe → the guided start's ways-to-begin appear (WorldSeed
 * options + session_zero's question) → pick or describe a start → the
 * campaign session opens with the character bound and the play console is
 * opened on it (``/play?session=…``).
 */
export function GraduateDialog({
  character,
  personaId,
  onGraduated,
  onClose,
}: {
  character: StandaloneCharacter;
  personaId?: string | null;
  onGraduated: (session: Session) => void;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const router = useRouter();
  const { notify } = useNotify();
  const [universeId, setUniverseId] = useState("");
  const [prepared, setPrepared] = useState<GraduatePrepareResult | null>(null);
  const [answer, setAnswer] = useState("");
  const [preparing, setPreparing] = useState(false);

  const universesQ = useQuery({
    queryKey: ["universes", "all"],
    queryFn: () => universesApi.listUniverses(),
  });

  useEffect(() => {
    if (!universeId && universesQ.data?.length) {
      setUniverseId(universesQ.data[0].id);
    }
  }, [universesQ.data, universeId]);

  async function prepare() {
    if (!universeId) return;
    setPreparing(true);
    try {
      // Cross-component call: graduation hands off to the guided start's own
      // entry points (WorldSeed + session_zero) server-side.
      const result = await lightRpApi.graduatePrepare(character.id, { universe_id: universeId });
      setPrepared(result);
    } catch (e) {
      notify("error", `Couldn't prepare the campaign: ${errorMessage(e)}`);
    } finally {
      setPreparing(false);
    }
  }

  const startMutation = useMutation({
    mutationFn: async (): Promise<GraduateResult> =>
      lightRpApi.graduateToCampaign(character.id, {
        universe_id: universeId,
        persona_character_id: personaId ?? null,
        start_answer: answer.trim() || "surprise me",
        start_options: prepared?.start_options ?? [],
        question_text: prepared?.question ?? "",
      }),
    onSuccess: async (result) => {
      await qc.invalidateQueries({ queryKey: ["light-rp-memories", character.id] });
      // Cross-component call: open the guided-start campaign session with the
      // exact payload graduation assembled (character + persona + premise).
      const session = await chatApi.createSession(
        result.session_create as Parameters<typeof chatApi.createSession>[0],
      );
      notify(
        "success",
        `Campaign started with ${character.name} — ${result.memories_carried} memories carried over.`,
      );
      onGraduated(session);
      // Land in the play console on the new guided-start session.
      router.push(`/play?session=${session.id}`);
    },
    onError: (e) => notify("error", `Graduation failed: ${errorMessage(e)}`),
  });

  return (
    <div className="flex flex-col gap-4 p-4">
      {!prepared ? (
        <>
          <p className="text-sm text-fg-secondary">
            Pick the universe for your campaign with <strong>{character.name}</strong>. Their memories
            of you come along.
          </p>
          {universesQ.isLoading ? (
            <div className="flex items-center gap-2 text-sm text-fg-muted">
              <Loader2 className="h-4 w-4 animate-spin" /> Loading universes…
            </div>
          ) : (
            <select
              className="input-cyber"
              value={universeId}
              onChange={(e) => setUniverseId(e.target.value)}
              aria-label="Campaign universe"
            >
              {(universesQ.data ?? []).map((u) => (
                <option key={u.id} value={u.id}>
                  {u.name}
                </option>
              ))}
            </select>
          )}
          <button
            type="button"
            className="btn-cyber justify-center"
            disabled={!universeId || preparing}
            onClick={() => void prepare()}
          >
            {preparing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Flag className="h-4 w-4" />}
            {preparing ? "Preparing…" : "Continue"}
          </button>
        </>
      ) : (
        <>
          <p className="text-sm text-fg-secondary">{prepared.question}</p>
          <div className="flex flex-wrap gap-2">
            {prepared.start_options.map((option, i) => {
              const label = String(option.title || option.location || option.option_id || `Option ${i + 1}`);
              return (
                <button
                  key={String(option.option_id ?? i)}
                  type="button"
                  className={answer === label ? "btn-cyber px-3 py-1.5 text-xs" : "btn-ghost px-3 py-1.5 text-xs"}
                  onClick={() => setAnswer(label)}
                >
                  {label}
                </button>
              );
            })}
            <button
              type="button"
              className={answer === "surprise me" ? "btn-cyber px-3 py-1.5 text-xs" : "btn-ghost px-3 py-1.5 text-xs"}
              onClick={() => setAnswer("surprise me")}
            >
              Surprise me
            </button>
          </div>
          <textarea
            className="input-cyber min-h-[64px] resize-none"
            placeholder="…or describe your own way in"
            value={answer === "surprise me" ? "" : answer}
            onChange={(e) => setAnswer(e.target.value)}
          />
          <div className="flex gap-2">
            <button type="button" className="btn-ghost px-3 py-2 text-sm" onClick={() => setPrepared(null)}>
              Back
            </button>
            <button
              type="button"
              className="btn-cyber flex-1 justify-center"
              disabled={startMutation.isPending}
              onClick={() => startMutation.mutate()}
            >
              {startMutation.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Rocket className="h-4 w-4" />
              )}
              Start campaign
            </button>
          </div>
          <button type="button" className="btn-ghost justify-center text-xs" onClick={onClose}>
            Not now
          </button>
        </>
      )}
    </div>
  );
}
