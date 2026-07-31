"use client";

import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Loader2, Plus } from "lucide-react";
import { entitiesApi, universesApi, chatApi } from "@/lib/api";
import { useSystems } from "@/hooks/use-systems";
import { PLAY_KEYS, UNIVERSE_KEYS } from "@/lib/query-keys";
import type { Character, PlaytestBenchmark, StandaloneCharacter } from "@/lib/types";
import { cn } from "@/lib/utils";

const TONES = ["dramatic", "grim", "horror", "heroic", "mystery", "adventure"] as const;
type Tone = typeof TONES[number];

const TONE_DESCRIPTIONS: Record<Tone, string> = {
  dramatic: "Baroque, weighty, personal stakes",
  grim: "Terse, industrial, cosmic dread",
  horror: "Dread through omission, slow tension",
  heroic: "Elevated, mythic, earned hope",
  mystery: "Layered, rationed, careful",
  adventure: "Kinetic, immediate, punchy",
};

const MODE_LABEL: Record<string, string> = {
  autonomous_gm: "Autonomous GM",
  gm_assistant: "GM Assistant",
  world_architect: "World Architect",
};

export interface SetupPayload {
  title: string;
  mode: "autonomous_gm" | "gm_assistant";
  tone: string;
  story_premise?: string | null;
  play_mode?: string;
  multiverse_id?: string | null;
  multiverse_label?: string | null;
  universe_id?: string | null;
  universe_label?: string | null;
  character_id?: string | null;
  speaker_character_id?: string | null;
  persona_id?: string | null;
  controlled_character_ids?: string[];
  system_id?: string | null;
  system_label?: string | null;
  benchmark_id?: string | null;
  benchmark_label?: string | null;
  speaker_label?: string | null;
}

export interface SetupPanelProps {
  isPending: boolean;
  initialMultiverseId?: string | null;
  initialUniverseId?: string | null;
  onCreate: (payload: SetupPayload) => void;
}

export function SetupPanel({
  isPending,
  initialMultiverseId,
  initialUniverseId,
  onCreate,
}: SetupPanelProps) {
  const [title, setTitle] = useState("New Story");
  const [storyPremise, setStoryPremise] = useState("");
  const [mode, setMode] = useState<"autonomous_gm" | "gm_assistant">("autonomous_gm");
  // Play style — freeform (no dice) is the default front door; tabletop opt-in.
  const [playMode, setPlayMode] = useState<"narrative" | "dice_game_system">("narrative");
  const [tone, setTone] = useState<Tone>("dramatic");
  const [speakerLabel, setSpeakerLabel] = useState("");
  const [selectedMvId, setSelectedMvId] = useState<string>(initialMultiverseId ?? "");
  const [selectedUniverseId, setSelectedUniverseId] = useState<string>(initialUniverseId ?? "");
  const [selectedSystemId, setSelectedSystemId] = useState<string>("");
  const [selectedCharacterId, setSelectedCharacterId] = useState<string>("");
  const [selectedPersonaId, setSelectedPersonaId] = useState<string>("");
  const [selectedBenchmarkId, setSelectedBenchmarkId] = useState<string>("");

  const { data: multiverses = [], isLoading: multiversesLoading } = useQuery({
    queryKey: UNIVERSE_KEYS.multiverses,
    queryFn: universesApi.listMultiverses,
  });

  const { data: universes = [], isLoading: universesLoading } = useQuery({
    queryKey: PLAY_KEYS.universes(selectedMvId),
    queryFn: () => universesApi.listUniverses(selectedMvId || undefined),
    enabled: !!selectedMvId,
  });

  const { data: systems = [], isLoading: systemsLoading } = useSystems();

  const { data: benchmarks = [], isLoading: benchmarksLoading } = useQuery<PlaytestBenchmark[]>({
    queryKey: PLAY_KEYS.benchmarks,
    queryFn: chatApi.listBenchmarks,
  });

  const { data: characters = [], isLoading: charactersLoading } = useQuery<Character[]>({
    queryKey: PLAY_KEYS.characters(selectedSystemId),
    queryFn: () => entitiesApi.listCharacters(selectedSystemId),
    enabled: !!selectedSystemId,
  });

  const { data: personas = [], isLoading: personasLoading } = useQuery<StandaloneCharacter[]>({
    queryKey: PLAY_KEYS.personas,
    queryFn: () => entitiesApi.listStandaloneCharacters({ limit: 100 }),
  });

  useEffect(() => {
    if (!selectedMvId && multiverses[0]?.id) {
      setSelectedMvId(multiverses[0].id);
    }
  }, [multiverses, selectedMvId]);

  useEffect(() => {
    if (universes.length > 0 && !universes.some((u) => u.id === selectedUniverseId)) {
      setSelectedUniverseId(universes[0].id);
    }
    if (universes.length === 0) {
      setSelectedUniverseId("");
    }
  }, [universes, selectedUniverseId]);

  useEffect(() => {
    if (!selectedBenchmarkId && !selectedSystemId && systems[0]?.id) {
      setSelectedSystemId(systems[0].id);
    }
  }, [systems, selectedSystemId, selectedBenchmarkId]);

  useEffect(() => {
    if (characters.length === 0) {
      setSelectedCharacterId("");
    }
    // We no longer auto-select the first character — the player must
    // explicitly pick a saved PC or opt into creating one. This keeps
    // "selected" meaning "deliberate" in the backend session payload.
  }, [characters, selectedCharacterId]);

  const selectedMv = multiverses.find((mv) => mv.id === selectedMvId);
  const selectedUniverse = universes.find((u) => u.id === selectedUniverseId);
  const selectedSystem = systems.find((s) => s.id === selectedSystemId);
  const selectedCharacter = characters.find((c) => c.id === selectedCharacterId);
  const selectedPersona = personas.find((p) => p.id === selectedPersonaId);
  const selectedBenchmark = benchmarks.find((b) => b.benchmark_id === selectedBenchmarkId);

  useEffect(() => {
    if (!selectedBenchmark) return;
    if (selectedBenchmark.session_title) setTitle(selectedBenchmark.session_title);
    if (selectedBenchmark.tone && TONES.includes(selectedBenchmark.tone as Tone)) {
      setTone(selectedBenchmark.tone as Tone);
    }
    if (selectedBenchmark.mode === "gm_assistant" || selectedBenchmark.mode === "autonomous_gm") {
      setMode(selectedBenchmark.mode);
    }
    setSelectedSystemId(selectedBenchmark.resolved_system_id ?? "");
  }, [selectedBenchmark]);

  useEffect(() => {
    if (selectedCharacter) {
      setSpeakerLabel(selectedCharacter.name);
    }
  }, [selectedCharacter]);

  useEffect(() => {
    // A Controlled PC already has mechanics in this world and jumps straight
    // to active play server-side, bypassing Session Zero entirely -- so a
    // persona selection would be stored but never actually used. Only drive
    // the speaker label from the persona when no Controlled PC is chosen.
    if (selectedPersona && !selectedCharacterId) {
      setSpeakerLabel(selectedPersona.name);
    }
  }, [selectedPersona, selectedCharacterId]);

  return (
    <div className="glass rounded-2xl border border-cyan-500/15 p-5 space-y-5">
      <div>
        <p className="section-label">P-18 / P-19</p>
        <h2 className="text-lg font-semibold text-slate-100 mt-1">Start a playable session</h2>
        <p className="text-sm text-slate-500 mt-1 leading-relaxed">
          Choose a setting (`Multiverse`), a persistent timeline (`Universe`), and who is speaking. Then continue setup and play through chat with MONITOR.
        </p>
      </div>

      <div className="rounded-xl border border-cyan-500/20 bg-cyan-500/5 px-4 py-3 text-xs text-cyan-100 space-y-1.5">
        <div className="font-medium text-cyan-300">Benchmark testbed moved to Settings</div>
        <p className="leading-relaxed text-cyan-50/85">
          Launch and compare benchmark flows from{" "}
          <code className="font-mono text-cyan-200">Settings → Benchmark Testbed</code>.
          Benchmark sessions opened there will still show their notes and probes inside the play console.
        </p>
      </div>

      <div className="space-y-3">
        <label className="block text-xs text-slate-500">Session title</label>
        <input
          className="input-cyber w-full"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Ashes of Temeria"
        />
      </div>

      <div className="space-y-2">
        <label htmlFor="setup-story-premise" className="block text-xs text-slate-500">
          Story premise (optional)
        </label>
        <textarea
          id="setup-story-premise"
          className="input-cyber w-full min-h-[4.5rem] resize-y"
          value={storyPremise}
          onChange={(e) => setStoryPremise(e.target.value)}
          placeholder="A heist against a rival Prince, no combat. Or: survival horror, focus on isolation."
        />
        <p className="text-[10px] text-slate-500">
          A hard steering constraint on the opening scene — leave blank to let the GM set the scene freely.
        </p>
      </div>

      <div className="space-y-2">
        <label className="block text-xs text-slate-500">Mode</label>
        <div className="flex flex-wrap gap-2">
          {(["autonomous_gm", "gm_assistant"] as const).map((value) => (
            <button
              key={value}
              onClick={() => setMode(value)}
              className={cn(
                "px-3 py-1.5 rounded-lg text-xs font-medium border transition-all duration-150",
                mode === value
                  ? "bg-cyan-500/15 text-cyan-300 border-cyan-500/35"
                  : "bg-white/4 text-slate-400 border-white/8 hover:bg-white/8 hover:text-slate-200",
              )}
            >
              {MODE_LABEL[value]}
            </button>
          ))}
        </div>
      </div>

      <div className="space-y-2">
        <label className="block text-xs text-slate-500">Play style</label>
        <div className="flex flex-wrap gap-2">
          {([
            ["narrative", "Freeform", "Pure story — no dice"],
            ["dice_game_system", "Tabletop", "Dice when it matters"],
          ] as const).map(([value, label, hint]) => (
            <button
              key={value}
              onClick={() => setPlayMode(value)}
              title={hint}
              className={cn(
                "px-3 py-1.5 rounded-lg text-xs font-medium border transition-all duration-150",
                playMode === value
                  ? "bg-cyan-500/15 text-cyan-300 border-cyan-500/35"
                  : "bg-white/4 text-slate-400 border-white/8 hover:bg-white/8 hover:text-slate-200",
              )}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className="space-y-2">
        <label className="block text-xs text-slate-500">Narrative tone</label>
        <div className="flex flex-wrap gap-2">
          {TONES.map((value) => (
            <button
              key={value}
              onClick={() => setTone(value)}
              title={TONE_DESCRIPTIONS[value]}
              className={cn(
                "px-3 py-1.5 rounded-lg text-xs font-medium border transition-all duration-150 capitalize",
                tone === value
                  ? "bg-purple-500/15 text-purple-300 border-purple-500/35"
                  : "bg-white/4 text-slate-400 border-white/8 hover:bg-white/8 hover:text-slate-200",
              )}
            >
              {value}
            </button>
          ))}
        </div>
        {tone && (
          <p className="text-[10px] text-slate-600 italic">{TONE_DESCRIPTIONS[tone as Tone] ?? ""}</p>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="space-y-2">
          <label className="block text-xs text-slate-500">Setting / Multiverse</label>
          <select
            className="input-cyber w-full"
            value={selectedMvId}
            onChange={(e) => setSelectedMvId(e.target.value)}
            disabled={multiversesLoading}
          >
            <option value="">Select a setting</option>
            {multiverses.map((mv) => (
              <option key={mv.id} value={mv.id}>
                {mv.name}
              </option>
            ))}
          </select>
        </div>

        <div className="space-y-2">
          <label className="block text-xs text-slate-500">Universe / Timeline</label>
          <select
            className="input-cyber w-full"
            value={selectedUniverseId}
            onChange={(e) => setSelectedUniverseId(e.target.value)}
            disabled={!selectedMvId || universesLoading}
          >
            <option value="">Select a universe</option>
            {universes.map((universe) => (
              <option key={universe.id} value={universe.id}>
                {universe.name}
              </option>
            ))}
          </select>
          {selectedMvId && !universesLoading && universes.length === 0 && (
            <p className="text-[10px] text-amber-400">
              No universes in this setting yet. Create one from the Worlds page first.
            </p>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="space-y-2">
          <label htmlFor="setup-rules-system" className="block text-xs text-slate-500">Rules system</label>
          <select
            id="setup-rules-system"
            className="input-cyber w-full"
            value={selectedSystemId}
            onChange={(e) => setSelectedSystemId(e.target.value)}
            disabled={systemsLoading}
          >
            <option value="">Select a system</option>
            {systems.map((system) => (
              <option key={system.id} value={system.id}>
                {system.name}
              </option>
            ))}
          </select>
        </div>

        <div className="space-y-2">
          <label htmlFor="setup-controlled-pc" className="block text-xs text-slate-500">Controlled PC (optional)</label>
          <select
            id="setup-controlled-pc"
            className="input-cyber w-full"
            value={selectedCharacterId}
            onChange={(e) => setSelectedCharacterId(e.target.value)}
            disabled={!selectedSystemId || charactersLoading}
          >
            <option value="">Create a new character in Session Zero</option>
            {characters.map((character) => (
              <option key={character.id} value={character.id}>
                {character.name}
              </option>
            ))}
          </select>
          {selectedSystemId && !charactersLoading && characters.length === 0 && (
            <p className="text-[10px] text-slate-500">
              No existing characters found for this system yet.
            </p>
          )}
          <p className="text-[10px] text-slate-500">
            Selection is deliberate — leaving this blank lets Session Zero build a new character.
          </p>
        </div>
      </div>

      <div className="space-y-2">
        <label htmlFor="setup-persona" className="block text-xs text-slate-500">Play as a saved persona (optional)</label>
        <select
          id="setup-persona"
          className="input-cyber w-full"
          value={selectedPersonaId}
          onChange={(e) => setSelectedPersonaId(e.target.value)}
          disabled={personasLoading || !!selectedCharacterId}
        >
          <option value="">Create a new character in Session Zero</option>
          {personas.map((persona) => (
            <option key={persona.id} value={persona.id}>
              {persona.name}
            </option>
          ))}
        </select>
        {selectedCharacterId ? (
          <p className="text-[10px] text-slate-500">
            A Controlled PC is already selected above and starts play immediately — clear it to play as a persona instead.
          </p>
        ) : (
          <p className="text-[10px] text-slate-500">
            Session Zero will pre-fill from this persona&apos;s description and personality instead of interviewing from scratch.
          </p>
        )}
      </div>

      <div className="space-y-2">
        <label className="block text-xs text-slate-500">Active speaker / PC focus</label>
        <input
          className="input-cyber w-full"
          value={speakerLabel}
          onChange={(e) => setSpeakerLabel(e.target.value)}
          placeholder="Geralt of Rivia"
        />
      </div>

      <div className="rounded-xl border border-white/8 bg-black/10 px-4 py-3 text-xs text-slate-400 space-y-1">
        <div>
          <strong className="text-slate-300">Setting:</strong> {selectedMv?.name ?? "Not selected"}
        </div>
        <div>
          <strong className="text-slate-300">Universe:</strong> {selectedUniverse?.name ?? "Not selected"}
        </div>
        <div>
          <strong className="text-slate-300">System:</strong> {selectedSystem?.name ?? "Not selected"}
        </div>
        <div>
          <strong className="text-slate-300">Controlled PC:</strong>{" "}
          {selectedCharacter?.name ?? "Custom / not selected"}
        </div>
        <div>
          <strong className="text-slate-300">Persona:</strong>{" "}
          {selectedCharacterId ? "Ignored (Controlled PC takes priority)" : selectedPersona?.name ?? "None — new character"}
        </div>
        <div>
          <strong className="text-slate-300">Speaker:</strong> {speakerLabel || "You / current PC"}
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        <button
          onClick={() =>
            onCreate({
              title: title.trim() || "New Story",
              mode,
              tone,
              story_premise: storyPremise.trim() || null,
              play_mode: selectedBenchmark?.play_mode ?? playMode,
              multiverse_id: selectedMvId || null,
              multiverse_label: selectedMv?.name ?? null,
              universe_id: selectedUniverseId || null,
              universe_label: selectedUniverse?.name ?? null,
              character_id: selectedCharacterId || null,
              speaker_character_id: selectedCharacterId || null,
              persona_id: selectedCharacterId ? null : selectedPersonaId || null,
              controlled_character_ids: selectedCharacterId ? [selectedCharacterId] : [],
              system_id: selectedBenchmark?.resolved_system_id || selectedSystemId || null,
              system_label: selectedBenchmark?.resolved_system_name || selectedSystem?.name || null,
              benchmark_id: selectedBenchmarkId || null,
              benchmark_label: selectedBenchmark?.name ?? null,
              speaker_label: speakerLabel.trim() || selectedCharacter?.name || null,
            })
          }
          disabled={isPending || !selectedUniverseId}
          className="btn-cyber justify-center"
        >
          {isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
          Create Session
        </button>
        <a
          href="/universes"
          className="px-3 py-2 rounded-lg border border-white/10 text-xs text-slate-300 hover:bg-white/5 transition-all"
        >
          Manage Worlds
        </a>
      </div>
    </div>
  );
}