"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  AlertCircle,
  BookOpen,
  Bot,
  Check,
  ChevronDown,
  Copy,
  Dices,
  Eye,
  Layers,
  Loader2,
  Pencil,
  Plus,
  RotateCcw,
  ScrollText,
  Send,
  Flag,
  ShieldCheck,
  Sparkles,
  Trash2,
  User,
  X,
} from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { chatApi, entitiesApi, universesApi } from "@/lib/api";
import { useChatWebSocket, type WsStatus } from "@/hooks/use-chat-websocket";
import type { Character, ChatSessionState, Message, PlaytestBenchmark, Session, StandaloneCharacter } from "@/lib/types";
import { cn, formatRelativeTime } from "@/lib/utils";
import { PLAY_KEYS, ENTITY_KEYS, UNIVERSE_KEYS } from "@/lib/query-keys";
import { workingStateChips } from "@/lib/workingState";
import { useSystems } from "@/hooks/use-systems";
import { useWorldContext } from "@/lib/world-context";
import { CharacterPanel } from "./CharacterPanel";
import { CombatPanel } from "./CombatPanel";
import { StoryPanel } from "./StoryPanel";
import { ChatModeToggle } from "./ChatModeToggle";
import { CanonReviewPanel } from "@/components/canon/CanonReviewPanel";
import { RecapModal } from "./RecapModal";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type WsServerMsg =
  | { type: "start"; message_id: string }
  | { type: "token"; message_id: string; token: string }
  | { type: "done" | "end"; message_id: string; metadata?: Record<string, unknown> }
  | { type: string };

interface DiceRequest {
  spec: string;      // e.g. "1d20+3"
  reason: string;    // e.g. "Strength check"
}

// ---------------------------------------------------------------------------
// Client-side dice roller (mirrors data-layer/utils/dice.py logic)
// ---------------------------------------------------------------------------

function clientRollDice(spec: string): { total: number; rolls: number[]; mod: number } {
  const m = spec.trim().match(/^(\d*)d(\d+)([+-]\d+)?$/i);
  if (!m) return { total: 1, rolls: [1], mod: 0 };
  const n = Math.max(1, parseInt(m[1] || "1", 10));
  const s = Math.max(2, parseInt(m[2], 10));
  const mod = m[3] ? parseInt(m[3], 10) : 0;
  const rolls = Array.from({ length: n }, () => Math.floor(Math.random() * s) + 1);
  return { total: Math.max(1, rolls.reduce((a, b) => a + b, 0) + mod), rolls, mod };
}

// ---------------------------------------------------------------------------
// Typing indicator
// ---------------------------------------------------------------------------

function TypingIndicator() {
  return (
    <div className="flex items-end gap-2 animate-fade-in">
      <div className="w-6 h-6 rounded-full bg-purple-500/20 border border-purple-500/30 flex items-center justify-center flex-shrink-0">
        <Bot className="w-3 h-3 text-purple-400" />
      </div>
      <div className="msg-gm rounded-xl rounded-bl-sm px-4 py-3">
        <div className="flex items-center gap-1.5">
          <div className="w-1.5 h-1.5 rounded-full bg-purple-400 typing-dot" />
          <div className="w-1.5 h-1.5 rounded-full bg-purple-400 typing-dot" />
          <div className="w-1.5 h-1.5 rounded-full bg-purple-400 typing-dot" />
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Markdown prose renderer (bold = dialogue, italic = action/narration)
// ---------------------------------------------------------------------------

function ProseBubble({ children }: { children: string }) {
  return (
    <div className="prose-bubble">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          p: ({ children: c }) => <p className="mb-1.5 last:mb-0 leading-relaxed">{c}</p>,
          strong: ({ children: c }) => (
            <strong className="font-semibold text-slate-100">{c}</strong>
          ),
          em: ({ children: c }) => (
            <em className="italic text-slate-400">{c}</em>
          ),
          code: ({ children: c, className }) => {
            const isBlock = !!className;
            return isBlock ? (
              <code className="block bg-black/30 rounded p-2 text-xs font-mono text-cyan-300 overflow-x-auto">
                {c}
              </code>
            ) : (
              <code className="bg-white/10 px-1 rounded text-xs font-mono text-cyan-300">
                {c}
              </code>
            );
          },
          ul: ({ children: c }) => <ul className="list-disc pl-4 space-y-0.5">{c}</ul>,
          ol: ({ children: c }) => <ol className="list-decimal pl-4 space-y-0.5">{c}</ol>,
          li: ({ children: c }) => <li className="leading-relaxed">{c}</li>,
          hr: () => <hr className="border-white/10 my-2" />,
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Copy-to-clipboard button (GM prose utility, T-069)
// ---------------------------------------------------------------------------

function CopyButton({ text, className }: { text: string; className?: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      onClick={(e) => {
        e.stopPropagation();
        navigator.clipboard?.writeText(text).then(() => {
          setCopied(true);
          setTimeout(() => setCopied(false), 1500);
        });
      }}
      className={cn(
        "p-1 rounded text-slate-600 hover:text-slate-200 hover:bg-white/10 transition-all",
        className,
      )}
      title="Copy prose"
    >
      {copied ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
    </button>
  );
}

// ---------------------------------------------------------------------------
// Session phase chip — tells the player which stage the loop is in
// ---------------------------------------------------------------------------

const PHASE_STYLE: Record<string, { label: string; cls: string }> = {
  awaiting_character: { label: "Choosing character", cls: "text-amber-300 border-amber-500/30 bg-amber-500/10" },
  awaiting_premise: { label: "Setting premise", cls: "text-amber-300 border-amber-500/30 bg-amber-500/10" },
  setup: { label: "Setup", cls: "text-amber-300 border-amber-500/30 bg-amber-500/10" },
  active_play: { label: "In play", cls: "text-emerald-300 border-emerald-500/30 bg-emerald-500/10" },
  scene_ended: { label: "Scene ended", cls: "text-cyan-300 border-cyan-500/30 bg-cyan-500/10" },
};

function PhaseChip({ phase }: { phase?: string }) {
  if (!phase) return null;
  const cfg = PHASE_STYLE[phase] ?? {
    label: phase.replace(/_/g, " "),
    cls: "text-slate-400 border-white/10 bg-white/5",
  };
  return (
    <span className={cn("text-[10px] px-2 py-0.5 rounded-full border capitalize", cfg.cls)}>
      {cfg.label}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Working-state HUD (T-067/T-078) — HP, resources, conditions from the loop
// ---------------------------------------------------------------------------

function WorkingStateCard({ state }: { state: Record<string, unknown> }) {
  const chips = workingStateChips(state);
  if (chips.length === 0) return null;
  return (
    <div className="glass rounded-2xl border border-white/5 p-4 space-y-3">
      <div className="flex items-center gap-2 text-slate-200">
        <ShieldCheck className="w-4 h-4 text-emerald-400" />
        <h2 className="text-sm font-semibold">Character State</h2>
      </div>
      <div className="flex flex-wrap gap-1.5">
        {chips.map((c, i) =>
          c.kind === "stat" ? (
            <span
              key={`${c.label}-${i}`}
              className="text-[11px] px-2 py-1 rounded-lg border border-emerald-500/20 bg-emerald-500/5 text-emerald-100 capitalize"
            >
              {c.label}{c.value ? ": " : ""}
              <span className="font-mono font-semibold text-emerald-300">{c.value}</span>
            </span>
          ) : (
            <span key={`${c.label}-${i}`} className="tag-amber text-[10px] capitalize">
              {c.label}
            </span>
          ),
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Pending-consequence banner (T-078) — choose a mixed-success cost by tap
// ---------------------------------------------------------------------------

function ConsequenceBanner({
  pending,
  disabled,
  onChoose,
}: {
  pending: { options?: unknown; risk_preview?: unknown };
  disabled: boolean;
  onChoose: (option: string) => void;
}) {
  const options = Array.isArray(pending.options)
    ? (pending.options as unknown[]).map(String).filter(Boolean)
    : [];
  if (options.length === 0) return null;
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      className="mb-3 rounded-xl border border-amber-500/30 bg-amber-500/8 px-4 py-3 space-y-2"
    >
      <div className="flex items-center gap-2 text-xs font-semibold text-amber-300 uppercase tracking-wider">
        <Flag className="w-3.5 h-3.5" />
        The cost comes due — choose
      </div>
      {typeof pending.risk_preview === "string" && pending.risk_preview && (
        <p className="text-xs text-amber-100/80 leading-relaxed">{pending.risk_preview}</p>
      )}
      <div className="flex flex-col gap-1.5">
        {options.slice(0, 4).map((opt) => (
          <button
            key={opt}
            onClick={() => onChoose(opt)}
            disabled={disabled}
            className="text-left text-xs px-3 py-2 rounded-lg border border-amber-500/25 text-amber-50 hover:bg-amber-500/15 disabled:opacity-50 transition-all"
          >
            {opt}
          </button>
        ))}
      </div>
    </motion.div>
  );
}

// ---------------------------------------------------------------------------
// Inline dice result card (shown in GM messages when metadata has dice info)
// ---------------------------------------------------------------------------

function DiceResultCard({
  spec,
  total,
  rolls,
  reason,
  successLevel,
}: {
  spec: string;
  total: number;
  rolls?: number[];
  reason?: string;
  successLevel?: string;
}) {
  return (
    <div className="mt-2 rounded-lg border border-purple-500/20 bg-purple-500/5 px-2.5 py-2 text-[11px] space-y-1.5">
      <div className="flex items-center gap-1.5 text-purple-300 font-medium">
        <Dices className="w-3 h-3" />
        {reason ?? spec}
      </div>
      {rolls && rolls.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {rolls.map((r, i) => (
            <span key={i} className="dice-face">{r}</span>
          ))}
        </div>
      )}
      <div className="flex items-center gap-2">
        <span className="dice-face-total">{total}</span>
        <span className="text-slate-400 font-mono text-[10px]">{spec}</span>
        {successLevel && (
          <span className="tag-purple capitalize">{successLevel.replace(/_/g, " ")}</span>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Dice-roll request prompt (interactive, sent by GM)
// ---------------------------------------------------------------------------

function DiceRollPrompt({
  request,
  onResult,
}: {
  request: DiceRequest;
  onResult: (spec: string, value: number, rolls: number[], reason: string) => void;
}) {
  const [spinning, setSpinning] = useState(false);
  const [result, setResult] = useState<{ total: number; rolls: number[] } | null>(null);
  const [manualValue, setManualValue] = useState("");

  const handleAutoRoll = () => {
    setSpinning(true);
    setTimeout(() => {
      const r = clientRollDice(request.spec);
      setResult(r);
      setSpinning(false);
    }, 580);
  };

  const handleSubmit = () => {
    if (result) {
      onResult(request.spec, result.total, result.rolls, request.reason);
    } else if (manualValue) {
      const v = parseInt(manualValue, 10);
      if (!isNaN(v)) onResult(request.spec, v, [], request.reason);
    }
  };

  const handleManual = () => {
    const v = parseInt(manualValue, 10);
    if (!isNaN(v)) onResult(request.spec, v, [], request.reason);
  };

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.97, y: 6 }}
      animate={{ opacity: 1, scale: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.95 }}
      transition={{ duration: 0.2 }}
      className="msg-dice-request px-4 py-3 space-y-3"
    >
      <div className="flex items-center gap-2">
        <Dices className="w-4 h-4 text-amber-400" />
        <span className="text-amber-300 text-xs font-semibold uppercase tracking-wider">
          Roll Required
        </span>
      </div>

      <div className="space-y-0.5">
        <p className="text-sm text-slate-200 font-medium">{request.reason}</p>
        <p className="text-xs font-mono text-amber-400">{request.spec}</p>
      </div>

      {result ? (
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-1.5">
            {result.rolls.map((r, i) => (
              <span key={i} className="dice-face">{r}</span>
            ))}
            <span className="text-slate-500 text-xs mx-1">→</span>
            <span className="dice-face-total">{result.total}</span>
          </div>
          <button
            onClick={handleSubmit}
            className="btn-cyber text-xs px-3 py-1.5"
          >
            Confirm {result.total} and continue
          </button>
        </div>
      ) : (
        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={handleAutoRoll}
            disabled={spinning}
            className="btn-cyber text-xs px-3 py-1.5 gap-1.5"
          >
            <Dices className={cn("w-3.5 h-3.5", spinning && "animate-dice-spin")} />
            {spinning ? "Rolling…" : `Roll ${request.spec}`}
          </button>
          <span className="text-slate-600 text-xs">or enter manually</span>
          <div className="flex items-center gap-1">
            <input
              type="number"
              min={1}
              value={manualValue}
              onChange={(e) => setManualValue(e.target.value)}
              placeholder="0"
              className="w-16 input-cyber text-xs py-1 px-2 text-center"
              onKeyDown={(e) => e.key === "Enter" && handleManual()}
            />
            <button
              onClick={handleManual}
              disabled={!manualValue}
              className="btn-ghost text-xs px-2 py-1"
            >
              Use
            </button>
          </div>
        </div>
      )}
    </motion.div>
  );
}

// ---------------------------------------------------------------------------
// Message bubble
// ---------------------------------------------------------------------------


const PHASE_DOT: Record<string, string> = {
  active_play: "bg-emerald-400",
  awaiting_character: "bg-amber-400",
  awaiting_premise: "bg-amber-400",
  setup: "bg-amber-400",
  scene_end: "bg-cyan-400",
  scene_ended: "bg-cyan-400",
};

function SessionList({
  sessions,
  activeId,
  onSelect,
  onNew,
  onDelete,
  onRename,
  loading,
}: {
  sessions: Session[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  onDelete: (id: string) => void;
  onRename: (id: string, title: string) => void;
  loading: boolean;
}) {
  const [filter, setFilter] = useState("");
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");

  const visible = filter.trim()
    ? sessions.filter((s) =>
        `${s.title} ${s.universe_label ?? ""} ${s.speaker_label ?? ""}`
          .toLowerCase()
          .includes(filter.trim().toLowerCase()),
      )
    : sessions;

  const commitRename = (id: string) => {
    const title = renameValue.trim();
    setRenamingId(null);
    if (title) onRename(id, title);
  };

  return (
    <div className="glass flex flex-col border-r border-white/5 w-72 flex-shrink-0">
      <div className="flex items-center justify-between px-4 py-4 border-b border-white/5">
        <div>
          <span className="text-xs font-semibold text-slate-500 tracking-widest uppercase">
            Play Sessions
          </span>
          <p className="text-[10px] text-slate-700 mt-0.5">New or continue a story</p>
        </div>
        <button
          onClick={onNew}
          className="w-7 h-7 flex items-center justify-center rounded border border-cyan-500/25 text-cyan-400 hover:bg-cyan-500/10 transition-all"
          title="New session"
        >
          <Plus className="w-3.5 h-3.5" />
        </button>
      </div>

      <div className="px-3 py-3 border-b border-white/5 space-y-2">
        <button onClick={onNew} className="btn-cyber w-full justify-center text-xs">
          <Sparkles className="w-3.5 h-3.5" />
          Start New Session
        </button>
        {sessions.length > 5 && (
          <input
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Filter sessions…"
            className="w-full bg-slate-900/60 border border-white/10 rounded-lg px-2.5 py-1.5 text-[11px] text-slate-200 placeholder:text-slate-600 focus:outline-none focus:border-cyan-500/40"
          />
        )}
      </div>

      <div className="flex-1 overflow-y-auto py-2 px-2 space-y-1">
        {loading && (
          <div className="flex items-center gap-2 px-3 py-2 text-slate-600 text-xs">
            <Loader2 className="w-3 h-3 animate-spin" />
            Loading…
          </div>
        )}

        {sessions.length === 0 && !loading && (
          <div className="flex flex-col items-center justify-center py-10 px-6 text-center">
            <div className="w-14 h-14 rounded-2xl bg-cyan-500/8 border border-cyan-500/15 flex items-center justify-center mb-4">
              <Sparkles className="w-6 h-6 text-cyan-500/40" />
            </div>
            <p className="text-xs text-slate-400 font-medium mb-1">No sessions yet</p>
            <p className="text-[11px] text-slate-600 leading-relaxed">Click "Start New Session" above, or pick a benchmark to begin.</p>
          </div>
        )}

        {visible.length === 0 && sessions.length > 0 && !loading && (
          <p className="px-3 py-4 text-[11px] text-slate-600 text-center">
            No sessions match “{filter.trim()}”.
          </p>
        )}

        {visible.map((s) => (
          <div
            key={s.id}
            className={cn(
              "group relative rounded-lg border transition-all duration-150",
              activeId === s.id
                ? "bg-cyan-500/8 border-cyan-500/20"
                : "border-transparent hover:bg-white/4",
            )}
          >
            {renamingId === s.id ? (
              <div className="px-3 py-3">
                <input
                  autoFocus
                  value={renameValue}
                  onChange={(e) => setRenameValue(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") commitRename(s.id);
                    if (e.key === "Escape") setRenamingId(null);
                  }}
                  onBlur={() => commitRename(s.id)}
                  className="w-full bg-slate-900/70 border border-cyan-500/40 rounded px-2 py-1 text-xs text-slate-100 focus:outline-none"
                />
              </div>
            ) : (
              <>
                <button
                  onClick={() => onSelect(s.id)}
                  onDoubleClick={() => {
                    setRenamingId(s.id);
                    setRenameValue(s.title);
                  }}
                  className="w-full text-left px-3 py-3 pr-14"
                  title="Double-click to rename"
                >
                  <div className="flex items-center gap-1.5 min-w-0">
                    <span
                      className={cn(
                        "w-1.5 h-1.5 rounded-full flex-shrink-0",
                        PHASE_DOT[s.phase ?? ""] ?? "bg-slate-600",
                      )}
                      title={`Phase: ${(s.phase ?? "unknown").replace(/_/g, " ")}`}
                    />
                    <span className={cn("text-xs font-medium truncate", activeId === s.id ? "text-cyan-300" : "text-slate-400 group-hover:text-slate-200")}>{s.title}</span>
                  </div>
                  <div className="text-[10px] text-slate-600 mt-0.5">
                    {(MODE_LABEL[s.mode] ?? s.mode).replace(/_/g, " ")}
                  </div>
                  <div className="text-[10px] text-slate-600 mt-1 space-y-0.5">
                    {(s.universe_label ?? s.world_id) && <div>Universe: {s.universe_label ?? "Bound"}</div>}
                    {s.speaker_label && <div>Speaker: {s.speaker_label}</div>}
                    {s.benchmark_label && <div>Benchmark: {s.benchmark_label}</div>}
                    <div>{formatRelativeTime(s.updated_at)}</div>
                  </div>
                </button>
                <div className="absolute top-2.5 right-2 flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-all">
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      setRenamingId(s.id);
                      setRenameValue(s.title);
                    }}
                    className="w-6 h-6 flex items-center justify-center rounded text-slate-600 hover:text-cyan-300 hover:bg-cyan-500/10"
                    title="Rename session"
                  >
                    <Pencil className="w-3 h-3" />
                  </button>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      if (window.confirm(`Delete session “${s.title}”? Its chat transcript is removed; canon already accepted stays in the world.`)) {
                        onDelete(s.id);
                      }
                    }}
                    className="w-6 h-6 flex items-center justify-center rounded text-slate-600 hover:text-red-400 hover:bg-red-500/10"
                    title="Delete session"
                  >
                    <Trash2 className="w-3 h-3" />
                  </button>
                </div>
              </>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function SetupPanel({
  isPending,
  initialMultiverseId,
  initialUniverseId,
  onCreate,
}: {
  isPending: boolean;
  initialMultiverseId?: string | null;
  initialUniverseId?: string | null;
  onCreate: (payload: {
    title: string;
    mode: "autonomous_gm" | "gm_assistant";
    tone: string;
    play_mode?: string;
    multiverse_id?: string | null;
    multiverse_label?: string | null;
    universe_id?: string | null;
    universe_label?: string | null;
    character_id?: string | null;
    speaker_character_id?: string | null;
    controlled_character_ids?: string[];
    system_id?: string | null;
    system_label?: string | null;
    benchmark_id?: string | null;
    benchmark_label?: string | null;
    speaker_label?: string | null;
  }) => void;
}) {
  const [title, setTitle] = useState("New Story");
  const [mode, setMode] = useState<"autonomous_gm" | "gm_assistant">("autonomous_gm");
  const [tone, setTone] = useState<(typeof TONES)[number]>("dramatic");
  const [speakerLabel, setSpeakerLabel] = useState("");
  const [selectedMvId, setSelectedMvId] = useState<string>(initialMultiverseId ?? "");
  const [selectedUniverseId, setSelectedUniverseId] = useState<string>(initialUniverseId ?? "");
  const [selectedSystemId, setSelectedSystemId] = useState<string>("");
  const [selectedCharacterId, setSelectedCharacterId] = useState<string>("");
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
    if (characters.length > 0 && !characters.some((c) => c.id === selectedCharacterId)) {
      setSelectedCharacterId(characters[0].id);
    }
    if (characters.length === 0) {
      setSelectedCharacterId("");
    }
  }, [characters, selectedCharacterId]);

  const selectedMv = multiverses.find((mv) => mv.id === selectedMvId);
  const selectedUniverse = universes.find((u) => u.id === selectedUniverseId);
  const selectedSystem = systems.find((s) => s.id === selectedSystemId);
  const selectedCharacter = characters.find((c) => c.id === selectedCharacterId);
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
          Launch and compare benchmark flows from <code className="font-mono text-cyan-200">Settings → Benchmark Testbed</code>.
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
            <p className="text-[10px] text-amber-400">No universes in this setting yet. Create one from the Worlds page first.</p>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="space-y-2">
          <label className="block text-xs text-slate-500">Rules system</label>
          <select
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
          <label className="block text-xs text-slate-500">Controlled PC (optional)</label>
          <select
            className="input-cyber w-full"
            value={selectedCharacterId}
            onChange={(e) => setSelectedCharacterId(e.target.value)}
            disabled={!selectedSystemId || charactersLoading}
          >
            <option value="">Type a custom / new speaker</option>
            {characters.map((character) => (
              <option key={character.id} value={character.id}>
                {character.name}
              </option>
            ))}
          </select>
          {selectedSystemId && !charactersLoading && characters.length === 0 && (
            <p className="text-[10px] text-slate-500">No existing characters found for this system yet.</p>
          )}
        </div>
      </div>
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
        <div><strong className="text-slate-300">Setting:</strong> {selectedMv?.name ?? "Not selected"}</div>
        <div><strong className="text-slate-300">Universe:</strong> {selectedUniverse?.name ?? "Not selected"}</div>
        <div><strong className="text-slate-300">System:</strong> {selectedSystem?.name ?? "Not selected"}</div>
        <div><strong className="text-slate-300">Controlled PC:</strong> {selectedCharacter?.name ?? "Custom / not selected"}</div>
        <div><strong className="text-slate-300">Speaker:</strong> {speakerLabel || "You / current PC"}</div>
      </div>

      <div className="flex flex-wrap gap-2">
        <button
          onClick={() =>
            onCreate({
              title: title.trim() || "New Story",
              mode,
              tone,
              play_mode: selectedBenchmark?.play_mode ?? "dice_game_system",
              multiverse_id: selectedMvId || null,
              multiverse_label: selectedMv?.name ?? null,
              universe_id: selectedUniverseId || null,
              universe_label: selectedUniverse?.name ?? null,
              character_id: selectedCharacterId || null,
              speaker_character_id: selectedCharacterId || null,
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
        <a href="/universes" className="px-3 py-2 rounded-lg border border-white/10 text-xs text-slate-300 hover:bg-white/5 transition-all">
          Manage Worlds
        </a>
      </div>
    </div>
  );
}

function MessageBubble({ msg }: { msg: Message & { streaming?: string } }) {
  const isGM = msg.role === "gm";
  const isSystem = msg.role === "system";
  const meta = (msg.metadata ?? {}) as {
    type?: string;
    intent_type?: string;
    success_level?: string;
    roll_breakdown?: string;
    roll_detail?: { spec: string; total: number; rolls: number[]; reason?: string };
    dice_result?: { spec: string; value: number; rolls?: number[]; reason?: string };
    effects?: string[];
    risk_preview?: string;
    consequence_options?: string[];
    requires_player_choice?: boolean;
    narrative_pressure?: string;
    social_read?: {
      stance_after?: string;
      reason?: string;
      confidence?: number;
      deltas?: Record<string, number>;
    };
    relationship_snapshot?: Record<string, unknown>;
  };

  if (isSystem) {
    return (
      <div className="flex justify-center">
        <div className="msg-system rounded-lg px-3 py-1.5 text-xs text-slate-500 max-w-md text-center">
          <ProseBubble>{msg.content}</ProseBubble>
        </div>
      </div>
    );
  }

  // Determine if this is a dice-result player message
  const isDiceResultMsg = meta.type === "dice_result" && isGM === false;
  const socialDeltaEntries = Object.entries(meta.social_read?.deltas ?? {}).slice(0, 4);

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2 }}
      className={cn("group/bubble flex items-end gap-2", !isGM && "flex-row-reverse")}
    >
      <div
        className={cn(
          "w-6 h-6 rounded-full flex items-center justify-center flex-shrink-0 border",
          isGM
            ? "bg-purple-500/20 border-purple-500/30"
            : isDiceResultMsg
            ? "bg-amber-500/20 border-amber-500/30"
            : "bg-cyan-500/20 border-cyan-500/30",
        )}
      >
        {isGM ? (
          <Bot className="w-3 h-3 text-purple-400" />
        ) : isDiceResultMsg ? (
          <Dices className="w-3 h-3 text-amber-400" />
        ) : (
          <User className="w-3 h-3 text-cyan-400" />
        )}
      </div>

      <div
        className={cn(
          "max-w-[80%] rounded-xl px-4 py-3 text-sm leading-relaxed",
          isGM
            ? "msg-gm rounded-bl-sm"
            : isDiceResultMsg
            ? "rounded-br-sm bg-amber-500/5 border border-amber-500/20"
            : "msg-player rounded-br-sm",
        )}
      >
        {"streaming" in msg && msg.streaming !== undefined ? (
          <span>
            <ProseBubble>{msg.streaming}</ProseBubble>
            <span className="inline-block w-0.5 h-4 bg-purple-400 ml-0.5 animate-pulse align-middle" />
          </span>
        ) : isGM ? (
          <ProseBubble>{msg.content}</ProseBubble>
        ) : (
          // Player messages: render markdown too (bold dialogue, italic action)
          <ProseBubble>{msg.content}</ProseBubble>
        )}

        {/* Inline dice result card (from agent resolution metadata) */}
        {isGM && meta.roll_detail && (
          <DiceResultCard
            spec={meta.roll_detail.spec}
            total={meta.roll_detail.total}
            rolls={meta.roll_detail.rolls}
            reason={meta.roll_detail.reason}
            successLevel={meta.success_level}
          />
        )}

        {/* Compact roll breakdown (legacy metadata) */}
        {isGM && !meta.roll_detail && meta.roll_breakdown && (
          <div className="mt-2 rounded-lg border border-purple-500/20 bg-purple-500/5 px-2.5 py-2 text-[11px] text-purple-100">
            <div className="font-medium text-purple-300">Resolution</div>
            <div className="mt-0.5">{meta.roll_breakdown}</div>
          </div>
        )}

        {isGM && (meta.risk_preview || (Array.isArray(meta.consequence_options) && meta.consequence_options.length > 0)) && (
          <div className="mt-2 rounded-lg border border-amber-500/20 bg-amber-500/5 px-2.5 py-2 text-[11px] text-amber-100">
            {meta.intent_type && (
              <div className="mb-1 text-amber-300 font-medium capitalize">
                {meta.intent_type.replace(/_/g, " ")}
                {meta.narrative_pressure ? ` · pressure ${meta.narrative_pressure}` : ""}
              </div>
            )}
            {meta.risk_preview && <p>{meta.risk_preview}</p>}
            {Array.isArray(meta.consequence_options) && meta.consequence_options.length > 0 && (
              <div className="mt-1.5 space-y-1">
                <div className="font-medium text-amber-300">
                  {meta.requires_player_choice ? "Suggested consequence choices" : "Likely follow-through"}
                </div>
                <ul className="list-disc pl-4 space-y-0.5">
                  {meta.consequence_options.slice(0, 3).map((option) => (
                    <li key={option}>{option}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}

        {isGM && (meta.social_read?.stance_after || Object.keys(meta.relationship_snapshot ?? {}).length > 0) && (
          <div className="mt-2 rounded-lg border border-cyan-500/20 bg-cyan-500/5 px-2.5 py-2 text-[11px] text-cyan-100">
            <div className="font-medium text-cyan-300">Social continuity</div>
            {meta.social_read?.stance_after && (
              <div className="mt-1">
                <span className="text-slate-300">Stance:</span> {meta.social_read.stance_after}
              </div>
            )}
            {socialDeltaEntries.length > 0 && (
              <div className="mt-1 flex flex-wrap gap-1.5">
                {socialDeltaEntries.map(([key, value]) => (
                  <span key={key} className="tag-dim">
                    {key} {value >= 0 ? "+" : ""}{value.toFixed(2)}
                  </span>
                ))}
              </div>
            )}
            {meta.social_read?.reason && (
              <p className="mt-1.5 leading-relaxed text-cyan-50/90">{meta.social_read.reason}</p>
            )}
          </div>
        )}

        <div
          className={cn(
            "flex items-center gap-2 text-[10px] mt-1.5",
            isGM ? "text-purple-200" : isDiceResultMsg ? "text-amber-200" : "text-cyan-200",
          )}
        >
          <span className="opacity-40">{formatRelativeTime(msg.timestamp)}</span>
          {isGM && msg.content && !("streaming" in msg && msg.streaming !== undefined) && (
            <span className="opacity-0 group-hover/bubble:opacity-100 transition-opacity">
              <CopyButton text={msg.content} />
            </span>
          )}
        </div>
      </div>
    </motion.div>
  );
}

export default function PlayConsole() {
  const qc = useQueryClient();
  const searchParams = useSearchParams();
  const world = useWorldContext();
  const requestedSessionId = searchParams.get("session");
  const urlUniverseId = searchParams.get("universe");
  // URL params win; the persisted global world context is the default (T-077)
  const requestedUniverseId = urlUniverseId ?? world.universeId;
  const requestedMultiverseId = searchParams.get("multiverse") ?? world.multiverseId;
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  // Deep link from Worlds tree ("Play here"): open setup with the universe
  // preselected. Only an explicit URL param auto-opens setup — the persisted
  // world default must not hijack normal "resume last session" visits.
  const [showSetup, setShowSetup] = useState(() => Boolean(urlUniverseId && !requestedSessionId));
  const [streamingMsg, setStreamingMsg] = useState<{ id: string; text: string } | null>(null);
  const [inputValue, setInputValue] = useState("");
  const [isTyping, setIsTyping] = useState(false);
  const [pendingDiceRequest, setPendingDiceRequest] = useState<DiceRequest | null>(null);
  const [selectedCharacter, setSelectedCharacter] = useState<StandaloneCharacter | null>(null);
  const [chatMode, setChatMode] = useState<"ic" | "ooc">("ic");
  const [sendFailure, setSendFailure] = useState<{ text: string; detail: string } | null>(null);
  const [showRecap, setShowRecap] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  // Watchdog: if the GM never answers a WS send (connection died mid-turn),
  // surface a retry card instead of typing-dots forever (T-073).
  const turnWatchdogRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastSentRef = useRef<string | null>(null);

  const clearTurnWatchdog = useCallback(() => {
    if (turnWatchdogRef.current) {
      clearTimeout(turnWatchdogRef.current);
      turnWatchdogRef.current = null;
    }
  }, []);

  const armTurnWatchdog = useCallback(
    (text: string) => {
      clearTurnWatchdog();
      turnWatchdogRef.current = setTimeout(() => {
        setIsTyping(false);
        setStreamingMsg(null);
        setSendFailure({ text, detail: "The GM didn't respond within 4 minutes." });
      }, 240_000);
    },
    [clearTurnWatchdog],
  );

  // WebSocket message handler — stable ref to avoid re-creating the socket
  const handleWsMessage = useCallback(
    (data: Record<string, unknown>) => {
      const msg = data as WsServerMsg;
      if (msg.type === "start") {
        setIsTyping(false);
        setStreamingMsg({ id: (msg as { type: "start"; message_id: string }).message_id ?? crypto.randomUUID(), text: "" });
      } else if (msg.type === "token") {
        const t = msg as { type: "token"; token: string };
        setStreamingMsg((prev) =>
          prev ? { ...prev, text: prev.text + (t.token ?? "") } : null,
        );
      } else if (msg.type === "done" || msg.type === "end") {
        clearTurnWatchdog();
        setStreamingMsg(null);
        setSendFailure(null);
        qc.invalidateQueries({ queryKey: PLAY_KEYS.messages(activeSessionId) });
        qc.invalidateQueries({ queryKey: PLAY_KEYS.state(activeSessionId) });
        qc.invalidateQueries({ queryKey: PLAY_KEYS.sessions });

        // Check for a dice roll request from the GM
        const d = msg as { type: string; metadata?: Record<string, unknown> };
        const dr = d.metadata?.dice_request as DiceRequest | undefined;
        if (dr?.spec) {
          setPendingDiceRequest({ spec: dr.spec, reason: dr.reason ?? dr.spec });
        } else {
          setPendingDiceRequest(null);
        }
      } else if (msg.type === "error") {
        clearTurnWatchdog();
        setIsTyping(false);
        setStreamingMsg(null);
        const detail = String((data as { detail?: unknown; message?: unknown }).detail ?? (data as { message?: unknown }).message ?? "The GM hit an error.");
        setSendFailure({ text: lastSentRef.current ?? "", detail });
      }
    },
    [activeSessionId, qc, clearTurnWatchdog],
  );

  const { status: wsStatus, send: wsSend, wsRef, reconnect: wsReconnect } = useChatWebSocket({
    sessionId: activeSessionId,
    onMessage: handleWsMessage,
  });

  const { data: sessions = [], isLoading: sessionsLoading } = useQuery({
    queryKey: PLAY_KEYS.sessions,
    queryFn: () => chatApi.listSessions().then((s) => s.filter((x) => x.mode !== "world_architect")),
  });

  const { data: benchmarkCatalog = [] } = useQuery<PlaytestBenchmark[]>({
    queryKey: PLAY_KEYS.benchmarks,
    queryFn: chatApi.listBenchmarks,
  });

  useEffect(() => {
    if (requestedSessionId && sessions.some((session) => session.id === requestedSessionId) && activeSessionId !== requestedSessionId) {
      setActiveSessionId(requestedSessionId);
      setShowSetup(false);
      return;
    }

    if (!activeSessionId && sessions[0]?.id) {
      setActiveSessionId(sessions[0].id);
    }
  }, [sessions, activeSessionId, requestedSessionId]);

  const { data: messages = [] } = useQuery({
    queryKey: PLAY_KEYS.messages(activeSessionId),
    queryFn: () => (activeSessionId ? chatApi.getMessages(activeSessionId) : []),
    enabled: !!activeSessionId,
  });

  const { data: sessionState } = useQuery<ChatSessionState>({
    queryKey: PLAY_KEYS.state(activeSessionId),
    queryFn: () => chatApi.getSessionState(activeSessionId!),
    enabled: !!activeSessionId,
  });

  const createSession = useMutation({
    mutationFn: chatApi.createSession,
    onSuccess: (session) => {
      qc.invalidateQueries({ queryKey: PLAY_KEYS.sessions });
      setActiveSessionId(session.id);
      setShowSetup(false);
      // The world you start a session in becomes the global default (T-077)
      if (session.universe_id) {
        world.setWorld({
          multiverseId: session.multiverse_id ?? null,
          universeId: session.universe_id,
          universeLabel: session.universe_label ?? null,
        });
      }
    },
  });

  const deleteSession = useMutation({
    mutationFn: chatApi.deleteSession,
    onSuccess: (_data, sessionId) => {
      qc.invalidateQueries({ queryKey: PLAY_KEYS.sessions });
      if (activeSessionId === sessionId) {
        setActiveSessionId(null);
      }
    },
  });

  const patchTone = useMutation({
    mutationFn: ({ tone }: { tone: string }) =>
      chatApi.patchSession(activeSessionId!, { tone }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["play-sessions"] }),
  });

  const renameSession = useMutation({
    mutationFn: ({ id, title }: { id: string; title: string }) =>
      chatApi.patchSession(id, { title }),
    onSuccess: () => qc.invalidateQueries({ queryKey: PLAY_KEYS.sessions }),
  });

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingMsg, isTyping]);

  /** Deliver a player turn over WS when live, REST otherwise. Both paths show
   *  the player's message immediately and keep the typing indicator honest. */
  const deliverTurn = useCallback(
    (text: string, opts?: { skipEcho?: boolean }) => {
      if (!text || !activeSessionId) return;

      setPendingDiceRequest(null);
      setSendFailure(null);
      setIsTyping(true);
      lastSentRef.current = text;

      const sendOptions: { chat_mode?: "ic" | "ooc"; character_id?: string; is_ooc_persona?: boolean } = {};
      if (selectedCharacter) {
        sendOptions.character_id = selectedCharacter.id;
        if (chatMode === "ooc" || selectedCharacter.is_ooc_persona) {
          sendOptions.chat_mode = "ooc";
          sendOptions.is_ooc_persona = selectedCharacter.is_ooc_persona;
        }
      }

      if (!opts?.skipEcho) {
        const fake: Message = {
          id: crypto.randomUUID(),
          session_id: activeSessionId,
          role: "player",
          content: text,
          timestamp: new Date().toISOString(),
          metadata: {},
        };
        qc.setQueryData<Message[]>(PLAY_KEYS.messages(activeSessionId), (prev) => [
          ...(prev ?? []),
          fake,
        ]);
      }

      if (wsStatus === "connected") {
        wsSend({ type: "message", content: text, ...sendOptions });
        armTurnWatchdog(text);
      } else {
        chatApi
          .sendMessage(activeSessionId, text, sendOptions)
          .then(() => {
            setSendFailure(null);
            qc.invalidateQueries({ queryKey: PLAY_KEYS.messages(activeSessionId) });
            qc.invalidateQueries({ queryKey: PLAY_KEYS.state(activeSessionId) });
            qc.invalidateQueries({ queryKey: PLAY_KEYS.sessions });
          })
          .catch((err: unknown) => {
            const detail = err instanceof Error ? err.message : "Request failed";
            setSendFailure({ text, detail });
          })
          .finally(() => setIsTyping(false));
      }
    },
    [activeSessionId, qc, selectedCharacter, chatMode, wsStatus, wsSend, armTurnWatchdog],
  );

  const handleSend = useCallback(() => {
    const text = inputValue.trim();
    if (!text || !activeSessionId) return;
    setInputValue("");
    deliverTurn(text);
    textareaRef.current?.focus();
  }, [activeSessionId, inputValue, deliverTurn]);

  /** Re-send the previous player input (after a failure, or on demand). */
  const retryLastTurn = useCallback(() => {
    const lastPlayer = [...messages].reverse().find(
      (m) => m.role === "player" && (m.metadata as { type?: string })?.type !== "dice_result",
    );
    // A failed send is already on screen as the last player bubble — don't
    // echo it twice. A voluntary "retry last action" is a new action: echo it.
    const text = sendFailure?.text || lastPlayer?.content;
    if (text) deliverTurn(text, { skipEcho: Boolean(sendFailure) });
  }, [messages, sendFailure, deliverTurn]);

  const [endingScene, setEndingScene] = useState(false);
  const handleEndScene = useCallback(() => {
    if (!activeSessionId || endingScene) return;
    setEndingScene(true);
    chatApi
      .endScene(activeSessionId)
      .then(() => {
        qc.invalidateQueries({ queryKey: PLAY_KEYS.messages(activeSessionId) });
        qc.invalidateQueries({ queryKey: PLAY_KEYS.state(activeSessionId) });
        qc.invalidateQueries({ queryKey: PLAY_KEYS.sessions });
      })
      .catch((err: unknown) => {
        const detail = err instanceof Error ? err.message : "End-scene failed";
        setSendFailure({ text: "", detail: `Scene wrap-up failed: ${detail}` });
      })
      .finally(() => setEndingScene(false));
  }, [activeSessionId, endingScene, qc]);

  // Reset transient turn state when switching sessions; drop the watchdog on unmount.
  useEffect(() => {
    setSendFailure(null);
    setStreamingMsg(null);
    setIsTyping(false);
    setPendingDiceRequest(null);
    clearTurnWatchdog();
    return clearTurnWatchdog;
  }, [activeSessionId, clearTurnWatchdog]);

  const handleDiceResult = useCallback(
    (spec: string, value: number, rolls: number[], reason: string) => {
      setPendingDiceRequest(null);
      if (!activeSessionId) return;

      const resultContent = rolls.length > 0
        ? `🎲 **${reason}** — rolled *${spec}*: [${rolls.join(", ")}] = **${value}**`
        : `🎲 **${reason}** — *${spec}* = **${value}** *(manual)*`;

      const playerMsg: Message = {
        id: crypto.randomUUID(),
        session_id: activeSessionId,
        role: "player",
        content: resultContent,
        timestamp: new Date().toISOString(),
        metadata: { type: "dice_result", spec, value, rolls, reason },
      };

      qc.setQueryData<Message[]>(PLAY_KEYS.messages(activeSessionId), (prev) => [
        ...(prev ?? []),
        playerMsg,
      ]);

      if (wsStatus === "connected") {
        wsSend({ type: "dice_result", spec, value, rolls, reason });
        setIsTyping(true);
      }
    },
    [activeSessionId, qc, wsStatus, wsSend],
  );

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const activeSession = sessions.find((s) => s.id === activeSessionId) ?? null;
  const activeBenchmark = benchmarkCatalog.find((b) => b.benchmark_id === activeSession?.benchmark_id) ?? null;

  const latestAudit = useMemo(() => {
    return [...messages]
      .reverse()
      .find((msg) => msg.role === "gm" && Object.keys(msg.metadata ?? {}).length > 0);
  }, [messages]);

  const recapLines = useMemo(() => {
    return messages
      .slice(-4)
      .map((msg) => `${msg.role === "gm" ? "MONITOR" : msg.role === "player" ? "You" : "System"}: ${msg.content}`)
      .slice(-3);
  }, [messages]);

  const auditMeta = (latestAudit?.metadata ?? {}) as {
    intent_type?: string;
    success_level?: string;
    roll_breakdown?: string;
    effects?: string[];
    risk_preview?: string;
    consequence_options?: string[];
    requires_player_choice?: boolean;
    narrative_pressure?: string;
    turns_count?: number;
    social_read?: {
      stance_after?: string;
      reason?: string;
      confidence?: number;
      deltas?: Record<string, number>;
    };
    relationship_snapshot?: Record<string, unknown>;
  };

  const socialRead = (sessionState?.latest_social_read ?? auditMeta.social_read ?? {}) as {
    stance_after?: string;
    reason?: string;
    confidence?: number;
    deltas?: Record<string, number>;
  };
  const relationshipSnapshot = (sessionState?.latest_relationship_snapshot ?? auditMeta.relationship_snapshot ?? {}) as Record<string, unknown>;
  const socialDeltaEntries = Object.entries(socialRead.deltas ?? {}).slice(0, 4);

  return (
    <div className="flex h-full min-h-0">
      <SessionList
        sessions={sessions}
        activeId={activeSessionId}
        onSelect={setActiveSessionId}
        onNew={() => setShowSetup(true)}
        onDelete={(id) => deleteSession.mutate(id)}
        onRename={(id, title) => renameSession.mutate({ id, title })}
        loading={sessionsLoading}
      />

      <div className="flex-1 min-w-0 grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_340px]">
        <div className="flex flex-col min-w-0 border-r border-white/5">
          <div className="flex items-center justify-between px-6 py-3.5 border-b border-white/5 glass">
            <div>
              <p className="section-label">P-18 Play Console</p>
              <h1 className="text-sm font-semibold text-slate-200 mt-1">
                {activeSession?.title ?? "Select or create a session"}
              </h1>
              {activeSession && (
                <p className="text-xs text-slate-600 mt-0.5">
                  {(MODE_LABEL[activeSession.mode] ?? activeSession.mode)} · {messages.length} messages
                </p>
              )}
            </div>
            <div className="flex items-center gap-2">
              {activeSession?.tone && (
                <div className="relative group">
                  <button className="tag-purple capitalize flex items-center gap-1 cursor-pointer hover:bg-purple-500/20 transition-colors">
                    {activeSession.tone}
                    <ChevronDown className="w-2.5 h-2.5 opacity-60" />
                  </button>
                  <div className="absolute right-0 top-full mt-1 z-50 hidden group-hover:block glass rounded-xl border border-white/10 p-2 space-y-0.5 min-w-[180px]">
                    {TONES.map((t) => (
                      <button
                        key={t}
                        onClick={() => patchTone.mutate({ tone: t })}
                        className={cn(
                          "w-full text-left px-3 py-1.5 rounded-lg text-xs capitalize transition-all",
                          t === activeSession.tone
                            ? "bg-purple-500/15 text-purple-300"
                            : "text-slate-400 hover:bg-white/5 hover:text-slate-200"
                        )}
                      >
                        {t}
                        <span className="block text-[10px] text-slate-600 truncate">{TONE_DESCRIPTIONS[t]}</span>
                      </button>
                    ))}
                  </div>
                </div>
              )}
              {activeSession && (
                <span className="tag-cyan capitalize">
                  {MODE_LABEL[activeSession.mode] ?? activeSession.mode}
                </span>
              )}
              {activeSession && <PhaseChip phase={sessionState?.session?.phase ?? activeSession.phase} />}
              {selectedCharacter && (
                <ChatModeToggle
                  mode={chatMode}
                  onChange={setChatMode}
                />
              )}
              {activeSessionId && (
                <button
                  onClick={handleEndScene}
                  disabled={endingScene}
                  className="ml-auto flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs border border-amber-500/30 text-amber-300 hover:bg-amber-500/10 disabled:opacity-50 transition-all"
                  title="Complete the current scene and advance the story"
                >
                  <Flag className="w-3 h-3" />
                  {endingScene ? "Ending…" : "End scene"}
                </button>
              )}
            </div>
          </div>

          <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
            {!activeSessionId && !showSetup && (
              <div className="flex flex-col items-center justify-center h-full text-center space-y-4">
                <div className="w-16 h-16 rounded-2xl bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center shadow-cyan-glow">
                  <Bot className="w-8 h-8 text-cyan-400" />
                </div>
                <div>
                  <h2 className="text-lg font-semibold text-slate-200">MONITOR Play</h2>
                  <p className="text-sm text-slate-600 mt-1 max-w-md">
                    Start a session, choose a setting and universe, then tell MONITOR what kind of story or opening scene you want in chat.
                  </p>
                </div>
                <button onClick={() => setShowSetup(true)} className="btn-cyber">
                  <Plus className="w-4 h-4" />
                  New Play Session
                </button>
              </div>
            )}

            {showSetup && (
              <SetupPanel
                isPending={createSession.isPending}
                initialMultiverseId={requestedMultiverseId}
                initialUniverseId={requestedUniverseId}
                onCreate={(payload) => createSession.mutate(payload)}
              />
            )}

            {!showSetup && (
              <>
                <AnimatePresence initial={false}>
                  {messages.map((msg) => (
                    <MessageBubble key={msg.id} msg={msg} />
                  ))}
                </AnimatePresence>

                {streamingMsg && activeSessionId && (
                  <MessageBubble
                    msg={{
                      id: streamingMsg.id,
                      session_id: activeSessionId,
                      role: "gm",
                      content: "",
                      timestamp: new Date().toISOString(),
                      metadata: {},
                      streaming: streamingMsg.text,
                    }}
                  />
                )}

                {isTyping && <TypingIndicator />}

                {sendFailure && !isTyping && !streamingMsg && (
                  <motion.div
                    initial={{ opacity: 0, y: 6 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="rounded-xl border border-red-500/25 bg-red-500/5 px-4 py-3 space-y-2"
                  >
                    <div className="flex items-center gap-2 text-xs text-red-300 font-medium">
                      <AlertCircle className="w-3.5 h-3.5" />
                      Turn didn&apos;t go through
                    </div>
                    <p className="text-xs text-slate-400 leading-relaxed break-words">
                      {sendFailure.detail}
                    </p>
                    <div className="flex items-center gap-2">
                      {sendFailure.text && (
                        <button onClick={retryLastTurn} className="btn-cyber text-xs py-1 px-3">
                          <RotateCcw className="w-3 h-3" /> Retry
                        </button>
                      )}
                      <button
                        onClick={() => setSendFailure(null)}
                        className="btn-ghost text-xs py-1 px-2 text-slate-500"
                      >
                        <X className="w-3 h-3" /> Dismiss
                      </button>
                    </div>
                  </motion.div>
                )}

                <AnimatePresence>
                  {pendingDiceRequest && !isTyping && (
                    <DiceRollPrompt
                      key="dice-prompt"
                      request={pendingDiceRequest}
                      onResult={handleDiceResult}
                    />
                  )}
                </AnimatePresence>

                <div ref={messagesEndRef} />
              </>
            )}
          </div>

          {activeSessionId && !showSetup && (
            <div className="px-6 pb-5 pt-3 border-t border-white/5">
              {sessionState?.pending_consequence &&
                Object.keys(sessionState.pending_consequence).length > 0 && (
                  <ConsequenceBanner
                    pending={sessionState.pending_consequence as { options?: unknown; risk_preview?: unknown }}
                    disabled={isTyping || !!streamingMsg}
                    onChoose={(opt) => deliverTurn(opt)}
                  />
                )}
              {activeBenchmark?.starter_questions && activeBenchmark.starter_questions.length > 0 && (
                <div className="mb-3">
                  <p className="text-[10px] text-amber-400 uppercase tracking-wider mb-2">Benchmark probes</p>
                  <div className="flex flex-wrap gap-2">
                    {activeBenchmark.starter_questions.slice(0, 3).map((question) => (
                      <button
                        key={question}
                        onClick={() => setInputValue(question)}
                        className="px-2.5 py-1 rounded-full text-[11px] border border-amber-500/20 text-amber-200 hover:bg-amber-500/10 transition-all"
                      >
                        {question}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              <div className="flex flex-wrap gap-2 mb-3">
                <button
                  onClick={() => deliverTurn("I pause and take in my surroundings — what do I see, hear, and notice?")}
                  disabled={isTyping || !!streamingMsg}
                  className="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] border border-white/10 text-slate-400 hover:text-slate-100 hover:border-cyan-500/30 hover:bg-cyan-500/10 disabled:opacity-40 transition-all"
                >
                  <Eye className="w-3 h-3" /> Look around
                </button>
                <button
                  onClick={() => {
                    setInputValue("(( Oracle: ");
                    textareaRef.current?.focus();
                  }}
                  className="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] border border-white/10 text-slate-400 hover:text-slate-100 hover:border-purple-500/30 hover:bg-purple-500/10 transition-all"
                  title="Ask the oracle a yes/no question about the world"
                >
                  <Sparkles className="w-3 h-3" /> Ask the Oracle
                </button>
                <button
                  onClick={() => setShowRecap(true)}
                  className="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] border border-white/10 text-slate-400 hover:text-slate-100 hover:border-amber-500/30 hover:bg-amber-500/10 transition-all"
                >
                  <BookOpen className="w-3 h-3" /> Story so far
                </button>
                {messages.some((m) => m.role === "player") && (
                  <button
                    onClick={retryLastTurn}
                    disabled={isTyping || !!streamingMsg}
                    className="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] border border-white/10 text-slate-400 hover:text-slate-100 hover:border-cyan-500/30 hover:bg-cyan-500/10 disabled:opacity-40 transition-all"
                    title="Re-send your previous action"
                  >
                    <RotateCcw className="w-3 h-3" /> Retry last
                  </button>
                )}
              </div>

              <div className="flex items-end gap-3 glass rounded-xl p-3">
                {wsStatus !== "connected" && (
                  <div className={cn(
                    "flex items-center gap-1.5 text-[10px] px-2 py-1 rounded-full mb-auto",
                    wsStatus === "reconnecting" && "bg-yellow-500/10 text-yellow-400 border border-yellow-500/20",
                    wsStatus === "connecting" && "bg-blue-500/10 text-blue-400 border border-blue-500/20",
                    wsStatus === "disconnected" && "bg-red-500/10 text-red-400 border border-red-500/20",
                  )}>
                    <span className={cn(
                      "w-1.5 h-1.5 rounded-full",
                      wsStatus === "reconnecting" && "bg-yellow-400 animate-pulse",
                      wsStatus === "connecting" && "bg-blue-400 animate-pulse",
                      wsStatus === "disconnected" && "bg-red-400",
                    )} />
                    {wsStatus === "reconnecting" && "Reconnecting…"}
                    {wsStatus === "connecting" && "Connecting…"}
                    {wsStatus === "disconnected" && (
                      <button onClick={wsReconnect} className="underline hover:text-red-300">Disconnected — retry</button>
                    )}
                  </div>
                )}
                <textarea
                  ref={textareaRef}
                  value={inputValue}
                  onChange={(e) => setInputValue(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="Use *action* for in-fiction moves, or ((...)) for OOC / rules questions…"
                  rows={2}
                  className="flex-1 bg-transparent text-sm text-slate-200 placeholder:text-slate-600 resize-none focus:outline-none"
                />
                <button
                  onClick={handleSend}
                  disabled={!inputValue.trim()}
                  className={cn(
                    "flex-shrink-0 w-9 h-9 rounded-lg flex items-center justify-center transition-all duration-150",
                    inputValue.trim()
                      ? "bg-cyan-500/15 text-cyan-400 border border-cyan-500/30 hover:bg-cyan-500/25 hover:shadow-cyan-glow"
                      : "bg-white/4 text-slate-600 border border-white/8 cursor-not-allowed",
                  )}
                >
                  <Send className="w-4 h-4" />
                </button>
              </div>
              <p className="text-[10px] text-slate-700 mt-2 text-center">
                Chat-first setup and play · Use <code>*action*</code> for in-fiction emphasis and <code>((...))</code> for OOC questions · Enter to send · Shift + Enter for new line
              </p>
            </div>
          )}
        </div>

        <aside className="hidden xl:flex xl:flex-col gap-4 p-4 overflow-y-auto bg-black/10">
          <CharacterPanel
            selectedId={selectedCharacter?.id ?? null}
            onSelect={(id, char) => setSelectedCharacter(char)}
            chatMode={chatMode}
            onChatModeChange={setChatMode}
          />

          {sessionState?.latest_working_state &&
            Object.keys(sessionState.latest_working_state).length > 0 && (
              <>
                <WorkingStateCard state={sessionState.latest_working_state} />
                <CombatPanel state={sessionState.latest_working_state} />
              </>
            )}

          {activeSession?.story_id && (
            <div className="flex-shrink-0 h-[380px] border-t border-white/5 pt-4">
              <StoryPanel storyId={activeSession.story_id} />
            </div>
          )}

          {activeSession?.story_id && (
            <div className="flex-shrink-0 border-t border-white/5 pt-4">
              <CanonReviewPanel storyId={activeSession.story_id} compact />
            </div>
          )}

          <div className="glass rounded-2xl border border-white/5 p-4 space-y-3">
            <div className="flex items-center gap-2 text-slate-200">
              <Layers className="w-4 h-4 text-cyan-400" />
              <h2 className="text-sm font-semibold">Session Context</h2>
            </div>
            {activeSession ? (
              <div className="space-y-2 text-xs text-slate-400">
                <div><span className="text-slate-300">Setting:</span> {activeSession.multiverse_label ?? "Not set"}</div>
                <div><span className="text-slate-300">Universe:</span> {activeSession.universe_label ?? "Not set"}</div>
                <div><span className="text-slate-300">System:</span> {activeSession.system_label ?? "Not set"}</div>
                <div><span className="text-slate-300">Benchmark:</span> {activeSession.benchmark_label ?? "Custom free-play"}</div>
                <div><span className="text-slate-300">Speaker:</span> {activeSession.speaker_label ?? "You / current PC"}</div>
                {activeBenchmark?.comparison_group && <div><span className="text-slate-300">Comparison group:</span> {activeBenchmark.comparison_group}</div>}
                <div><span className="text-slate-300">Continuity:</span> changes persist in this universe across stories</div>
                <div><span className="text-slate-300">Story binding:</span> {activeSession.story_id ? "attached" : "not attached yet"}</div>
                <div><span className="text-slate-300">Scene binding:</span> {activeSession.scene_id ? "attached" : "not attached yet"}</div>
              </div>
            ) : (
              <p className="text-xs text-slate-500">Create a session to bind it to a setting, universe, and active speaker.</p>
            )}
          </div>

          <div className="glass rounded-2xl border border-white/5 p-4 space-y-3">
            <div className="flex items-center gap-2 text-slate-200">
              <Dices className="w-4 h-4 text-purple-400" />
              <h2 className="text-sm font-semibold">Audit & Resolution</h2>
            </div>
            {auditMeta.roll_breakdown ? (
              <div className="space-y-2 text-xs">
                {auditMeta.success_level && (
                  <span className="tag-purple capitalize">{auditMeta.success_level.replace(/_/g, " ")}</span>
                )}
                <p className="text-slate-300">{auditMeta.roll_breakdown}</p>
                {auditMeta.intent_type && (
                  <div className="text-slate-400 capitalize">
                    Intent: {auditMeta.intent_type.replace(/_/g, " ")}
                    {auditMeta.narrative_pressure ? ` · pressure ${auditMeta.narrative_pressure}` : ""}
                  </div>
                )}
                {Array.isArray(auditMeta.effects) && auditMeta.effects.length > 0 && (
                  <div className="flex flex-wrap gap-1.5">
                    {auditMeta.effects.map((effect) => (
                      <span key={effect} className="tag-dim capitalize">
                        {effect.replace(/_/g, " ")}
                      </span>
                    ))}
                  </div>
                )}
                {auditMeta.risk_preview && (
                  <div className="rounded-xl border border-amber-500/20 bg-amber-500/5 px-3 py-2 text-amber-100">
                    <div className="font-medium text-amber-300">Risk & stakes</div>
                    <p className="mt-1 leading-relaxed">{auditMeta.risk_preview}</p>
                  </div>
                )}
                {Array.isArray(auditMeta.consequence_options) && auditMeta.consequence_options.length > 0 && (
                  <div className="rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-slate-200">
                    <div className="font-medium text-slate-100">
                      {auditMeta.requires_player_choice ? "Consequence choices" : "Likely next beats"}
                    </div>
                    <ul className="mt-1 space-y-1 list-disc pl-4 text-[11px] text-slate-300">
                      {auditMeta.consequence_options.slice(0, 3).map((option) => (
                        <li key={option}>{option}</li>
                      ))}
                    </ul>
                  </div>
                )}
                <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/5 px-3 py-2 text-emerald-200">
                  <div className="flex items-center gap-1.5 font-medium">
                    <ShieldCheck className="w-3.5 h-3.5" />
                    CanonKeeper
                  </div>
                  <p className="text-[11px] mt-1 text-emerald-100/85">
                    Pending scene-end review. Accepted changes in this universe will persist across future stories.
                  </p>
                </div>
              </div>
            ) : (
              <p className="text-xs text-slate-500">
                No mechanical resolution yet. When MONITOR triggers a check, the latest roll breakdown and outcome will appear here.
              </p>
            )}
          </div>

          <div className="glass rounded-2xl border border-white/5 p-4 space-y-3">
            <div className="flex items-center gap-2 text-slate-200">
              <Sparkles className="w-4 h-4 text-cyan-400" />
              <h2 className="text-sm font-semibold">NPC Social Continuity</h2>
            </div>
            {socialRead.stance_after || Object.keys(relationshipSnapshot).length > 0 ? (
              <div className="space-y-2 text-xs text-slate-300">
                {socialRead.stance_after && (
                  <div><span className="text-slate-400">Current stance:</span> {socialRead.stance_after}</div>
                )}
                {typeof relationshipSnapshot.trust === "number" && (
                  <div><span className="text-slate-400">Trust:</span> {relationshipSnapshot.trust.toFixed(2)}</div>
                )}
                {typeof relationshipSnapshot.fear === "number" && (
                  <div><span className="text-slate-400">Fear:</span> {relationshipSnapshot.fear.toFixed(2)}</div>
                )}
                {typeof relationshipSnapshot.leverage === "number" && (
                  <div><span className="text-slate-400">Leverage:</span> {relationshipSnapshot.leverage.toFixed(2)}</div>
                )}
                {socialDeltaEntries.length > 0 && (
                  <div className="flex flex-wrap gap-1.5">
                    {socialDeltaEntries.map(([key, value]) => (
                      <span key={key} className="tag-dim">
                        {key} {value >= 0 ? "+" : ""}{value.toFixed(2)}
                      </span>
                    ))}
                  </div>
                )}
                {socialRead.reason && (
                  <p className="leading-relaxed text-slate-400">{socialRead.reason}</p>
                )}
                {sessionState?.recent_npc_stances && sessionState.recent_npc_stances.length > 1 && (
                  <div>
                    <span className="text-slate-400">Recent stances:</span> {sessionState.recent_npc_stances.slice(-4).join(" → ")}
                  </div>
                )}
              </div>
            ) : (
              <p className="text-xs text-slate-500">
                Social stance changes will appear here once an NPC scene produces durable relationship drift.
              </p>
            )}
          </div>

          <div className="glass rounded-2xl border border-white/5 p-4 space-y-3">
            <div className="flex items-center gap-2 text-slate-200">
              <ScrollText className="w-4 h-4 text-amber-400" />
              <h2 className="text-sm font-semibold">Benchmark Notes</h2>
            </div>
            {activeBenchmark ? (
              <div className="space-y-2 text-xs text-slate-400">
                <p className="leading-relaxed">{activeBenchmark.description}</p>
                {activeBenchmark.focus_areas.length > 0 && (
                  <div>
                    <span className="text-slate-300">Focus:</span> {activeBenchmark.focus_areas.slice(0, 3).join(" · ")}
                  </div>
                )}
                {activeBenchmark.expected_signals.length > 0 && (
                  <div>
                    <span className="text-slate-300">Expected:</span> {activeBenchmark.expected_signals.slice(0, 2).join(" / ")}
                  </div>
                )}
                {activeBenchmark.adversarial_goals.length > 0 && (
                  <div>
                    <span className="text-slate-300">Probe for:</span> {activeBenchmark.adversarial_goals.slice(0, 2).join(" / ")}
                  </div>
                )}
              </div>
            ) : recapLines.length > 0 ? (
              <div className="space-y-2 text-xs text-slate-400">
                {recapLines.map((line, index) => (
                  <p key={`${line}-${index}`} className="leading-relaxed">{line}</p>
                ))}
              </div>
            ) : (
              <p className="text-xs text-slate-500">Scene recaps and recent turns will appear here for quick continuation.</p>
            )}
          </div>
        </aside>
      </div>

      {showRecap && activeSessionId && (
        <RecapModal sessionId={activeSessionId} onClose={() => setShowRecap(false)} />
      )}
    </div>
  );
}
