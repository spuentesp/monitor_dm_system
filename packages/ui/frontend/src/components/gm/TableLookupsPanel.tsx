"use client";

import { useEffect, useState } from "react";
import { BookOpen, Brain, Dices, History, Loader2, Search, User, Users, Wand2 } from "lucide-react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { entitiesApi, storiesApi } from "@/lib/api";
import { gmTableApi } from "@/lib/gm-table-api";
import type {
  ImproviseResponse,
  LastSessionResponse,
  NpcDossierResponse,
  PartyKnowledgeAnswer,
  RulesAnswer,
} from "@/lib/gm-table-types";
import { cn } from "@/lib/utils";
import { KnowledgePanel } from "./KnowledgePanel";

type LookupTab =
  | "npc"
  | "party"
  | "knowledge"
  | "last-session"
  | "name"
  | "complication"
  | "rules";

const LOOKUP_TABS: Array<{ id: LookupTab; label: string; icon: typeof User }> = [
  { id: "npc", label: "NPC", icon: User },
  { id: "party", label: "Party knows", icon: Users },
  { id: "knowledge", label: "Knowledge", icon: Brain },
  { id: "last-session", label: "Last session", icon: History },
  { id: "name", label: "Name", icon: Wand2 },
  { id: "complication", label: "Complication", icon: Dices },
  { id: "rules", label: "Rules", icon: BookOpen },
];

const PARTY_KEY = "monitor.gm.tableParty";

function readParty(universeId: string): string[] {
  try {
    const raw = window.localStorage.getItem(`${PARTY_KEY}.${universeId}`);
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed.filter((x): x is string => typeof x === "string") : [];
  } catch {
    return [];
  }
}

function writeParty(universeId: string, ids: string[]): void {
  try {
    window.localStorage.setItem(`${PARTY_KEY}.${universeId}`, JSON.stringify(ids));
  } catch {
    // localStorage unavailable — the selection just doesn't persist
  }
}

/**
 * Table lookups (Phase 7 Part B, CF-3/Q-2/Q-4/Q-7): the lookups a GM needs
 * within a few seconds each — who is this NPC and what do they want, what do
 * the party know, what was said last session, a name or a complication on
 * demand, and a rules answer with its source.
 */
export function TableLookupsPanel({
  universeId,
  systemId,
}: {
  universeId: string | null;
  systemId: string | null;
}) {
  const [tab, setTab] = useState<LookupTab>("npc");

  if (!universeId) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center space-y-2 px-4">
        <Search className="w-8 h-8 text-slate-700" />
        <p className="text-xs text-slate-600">Select a universe to run table lookups</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <div className="flex items-center gap-1 px-2 py-2 border-b border-white/5 flex-shrink-0 overflow-x-auto">
        {LOOKUP_TABS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className={cn(
              "flex items-center gap-1 px-2 py-1 rounded-lg text-[10px] font-medium transition-all border whitespace-nowrap",
              tab === id
                ? "bg-emerald-500/10 text-emerald-300 border-emerald-500/25"
                : "text-slate-500 hover:text-slate-300 border-transparent hover:bg-white/4",
            )}
          >
            <Icon className="w-3 h-3" />
            {label}
          </button>
        ))}
      </div>
      <div className="flex-1 overflow-y-auto px-3 py-3">
        {tab === "npc" && <NpcLookup universeId={universeId} />}
        {tab === "party" && <PartyLookup universeId={universeId} />}
        {tab === "knowledge" && <KnowledgePanel universeId={universeId} />}
        {tab === "last-session" && <LastSessionLookup universeId={universeId} />}
        {tab === "name" && <ImproviseLookup universeId={universeId} kind="name" />}
        {tab === "complication" && <ImproviseLookup universeId={universeId} kind="complication" />}
        {tab === "rules" && <RulesLookup universeId={universeId} systemId={systemId} />}
      </div>
    </div>
  );
}

function NpcLookup({ universeId }: { universeId: string }) {
  const [name, setName] = useState("");
  const [result, setResult] = useState<NpcDossierResponse | null>(null);

  const lookup = useMutation({
    mutationFn: () => gmTableApi.lookupNpc(universeId, { name }),
    onSuccess: setResult,
  });

  return (
    <div className="space-y-3">
      <div className="flex gap-2">
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && name.trim()) lookup.mutate();
          }}
          placeholder="NPC name…"
          className="input-cyber flex-1 text-xs"
        />
        <button
          onClick={() => lookup.mutate()}
          disabled={!name.trim() || lookup.isPending}
          className="btn-cyber text-xs py-1 px-3"
          aria-label="Look up"
        >
          {lookup.isPending ? <Loader2 className="w-3 h-3 animate-spin" /> : <Search className="w-3 h-3" />}
        </button>
      </div>
      {lookup.isError && <p className="text-[10px] text-red-400">Lookup failed — try again.</p>}
      {result && !result.found && <p className="text-[11px] text-slate-600">{result.note}</p>}
      {result?.found && result.entity && (
        <div className="space-y-2">
          <div className="glass-dark rounded-xl border border-white/5 p-3">
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold text-slate-200">{result.entity.name}</span>
              <span className="text-[9px] bg-white/5 px-1.5 py-0.5 rounded text-slate-500">
                {result.entity.entity_type}
              </span>
            </div>
            {result.entity.description && (
              <p className="text-[11px] text-slate-400 mt-1 leading-relaxed">{result.entity.description}</p>
            )}
            {result.entity.state_tags && result.entity.state_tags.length > 0 && (
              <div className="flex flex-wrap gap-1 mt-1">
                {result.entity.state_tags.map((t) => (
                  <span key={t} className="text-[9px] bg-amber-500/10 text-amber-300 px-1.5 py-0.5 rounded">
                    {t}
                  </span>
                ))}
              </div>
            )}
          </div>
          {result.agendas.length > 0 && (
            <div>
              <h4 className="text-[9px] font-bold tracking-widest uppercase text-purple-400 mb-1">What they want</h4>
              {result.agendas.map((a, i) => (
                <div key={a.id ?? i} className="text-[11px] text-slate-300 bg-purple-500/10 border border-purple-500/20 rounded-lg px-2 py-1 mb-1">
                  <span className="font-medium">{a.title ?? "Agenda"}</span>
                  {a.description && <p className="text-[10px] text-slate-500">{a.description}</p>}
                </div>
              ))}
            </div>
          )}
          {result.recent_facts.length > 0 && (
            <div>
              <h4 className="text-[9px] font-bold tracking-widest uppercase text-emerald-400 mb-1">Recent facts</h4>
              {result.recent_facts.map((f) => (
                <p key={f.id} className="text-[10px] text-slate-400 mb-0.5">• {f.statement}</p>
              ))}
            </div>
          )}
          {result.relationships.length > 0 && (
            <div>
              <h4 className="text-[9px] font-bold tracking-widest uppercase text-cyan-400 mb-1">Connections</h4>
              {result.relationships.map((r, i) => (
                <p key={i} className="text-[10px] text-slate-500">
                  {r.rel_type} → {r.to_entity_id === result.entity?.id ? r.from_entity_id : r.to_entity_id}
                </p>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function PartyLookup({ universeId }: { universeId: string }) {
  const [topic, setTopic] = useState("");
  const [selected, setSelected] = useState<string[]>(() => readParty(universeId));
  const [result, setResult] = useState<PartyKnowledgeAnswer | null>(null);

  const characters = useQuery({
    queryKey: ["gm-table-characters", universeId],
    queryFn: () => entitiesApi.listNPCs({ entity_type: "character", limit: 100 }),
    enabled: !!universeId,
    staleTime: 60_000,
  });

  const toggle = (id: string) => {
    const next = selected.includes(id) ? selected.filter((s) => s !== id) : [...selected, id];
    setSelected(next);
    writeParty(universeId, next);
  };

  const lookup = useMutation({
    mutationFn: () =>
      gmTableApi.lookupPartyKnowledge(universeId, {
        character_ids: selected,
        topic: topic.trim() || null,
      }),
    onSuccess: setResult,
  });

  return (
    <div className="space-y-3">
      <div className="flex gap-2">
        <input
          value={topic}
          onChange={(e) => setTopic(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && selected.length > 0) lookup.mutate();
          }}
          placeholder="What do they know about… (blank = everything)"
          className="input-cyber flex-1 text-xs"
        />
        <button
          onClick={() => lookup.mutate()}
          disabled={selected.length === 0 || lookup.isPending}
          className="btn-cyber text-xs py-1 px-3"
          title={selected.length === 0 ? "Pick the party first" : "Look up"}
          aria-label="Look up party knowledge"
        >
          {lookup.isPending ? <Loader2 className="w-3 h-3 animate-spin" /> : <Users className="w-3 h-3" />}
        </button>
      </div>
      <div>
        <h4 className="text-[9px] font-bold tracking-widest uppercase text-slate-500 mb-1">
          Who is the party? ({selected.length} selected)
        </h4>
        <div className="flex flex-wrap gap-1">
          {(characters.data?.items ?? []).map((c) => (
            <button
              key={c.id}
              type="button"
              onClick={() => toggle(c.id)}
              className={cn(
                "text-[10px] px-2 py-0.5 rounded border transition-all",
                selected.includes(c.id)
                  ? "bg-emerald-500/15 text-emerald-300 border-emerald-500/30"
                  : "text-slate-500 border-white/5 hover:text-slate-300",
              )}
            >
              {c.name}
            </button>
          ))}
          {(characters.data?.items ?? []).length === 0 && (
            <p className="text-[10px] text-slate-600">No characters in this universe yet.</p>
          )}
        </div>
      </div>
      {lookup.isError && <p className="text-[10px] text-red-400">Lookup failed — try again.</p>}
      {result && (
        <div className="space-y-2">
          {result.summary && (
            <p className="text-[11px] text-slate-300 glass-dark rounded-xl border border-white/5 p-2 leading-relaxed">
              {result.summary}
            </p>
          )}
          {result.facts.length === 0 && !result.summary && (
            <p className="text-[11px] text-slate-600">Nothing they would know about that.</p>
          )}
          {result.facts.map((f) => (
            <p key={f.index} className="text-[10px] text-slate-400">• {f.statement}</p>
          ))}
        </div>
      )}
    </div>
  );
}

function LastSessionLookup({ universeId }: { universeId: string }) {
  const [storyId, setStoryId] = useState("");
  const [result, setResult] = useState<LastSessionResponse | null>(null);

  const { data: storiesData } = useQuery({
    queryKey: ["universe-stories", universeId],
    queryFn: () => storiesApi.listStories({ universe_id: universeId, limit: 100 }),
    enabled: !!universeId,
    staleTime: 15_000,
  });
  const stories = storiesData?.stories ?? [];

  // Default to the most recent story once loaded
  useEffect(() => {
    if (!storyId && stories.length > 0) setStoryId(stories[0].id);
    if (storyId && stories.length > 0 && !stories.some((s) => s.id === storyId)) {
      setStoryId(stories[0].id);
    }
  }, [stories, storyId]);

  const lookup = useMutation({
    mutationFn: () => gmTableApi.lookupLastSession(universeId, storyId),
    onSuccess: setResult,
  });

  return (
    <div className="space-y-3">
      <div className="flex gap-2">
        <select
          value={storyId}
          onChange={(e) => setStoryId(e.target.value)}
          className="input-cyber py-1 text-xs flex-1"
          disabled={stories.length === 0}
        >
          {stories.length === 0 && <option value="">No stories yet</option>}
          {stories.map((s) => (
            <option key={s.id} value={s.id}>{s.title}</option>
          ))}
        </select>
        <button
          onClick={() => lookup.mutate()}
          disabled={!storyId || lookup.isPending}
          className="btn-cyber text-xs py-1 px-3"
          aria-label="Look up last session"
        >
          {lookup.isPending ? <Loader2 className="w-3 h-3 animate-spin" /> : <History className="w-3 h-3" />}
        </button>
      </div>
      {lookup.isError && <p className="text-[10px] text-red-400">Lookup failed — try again.</p>}
      {result && !result.found && <p className="text-[11px] text-slate-600">{result.note}</p>}
      {result?.found && (
        <div className="space-y-2">
          {result.ledger_entry && (
            <div className="glass-dark rounded-xl border border-white/5 p-2 space-y-1">
              <h4 className="text-[9px] font-bold tracking-widest uppercase text-emerald-400">
                Last session (scene {result.ledger_entry.sequence})
              </h4>
              <p className="text-[11px] text-slate-300 leading-relaxed">{result.ledger_entry.summary}</p>
              {result.ledger_entry.state_changes.map((c, i) => (
                <p key={i} className="text-[10px] text-slate-500">
                  • {c.who ? `${c.who}: ` : ""}{c.what}{c.where ? ` (${c.where})` : ""}
                </p>
              ))}
              {result.ledger_entry.open_questions.length > 0 && (
                <div>
                  <h5 className="text-[9px] uppercase tracking-wider text-amber-400">Left open</h5>
                  {result.ledger_entry.open_questions.map((q, i) => (
                    <p key={i} className="text-[10px] text-slate-500">• {q}</p>
                  ))}
                </div>
              )}
            </div>
          )}
          {/* CF-2 / CF-11: the recap's time line — how in-fiction time moved. */}
          {result.time_line.length > 0 && (
            <div data-testid="recap-time-line" className="glass-dark rounded-xl border border-white/5 p-2 space-y-1">
              <h4 className="text-[9px] font-bold tracking-widest uppercase text-cyan-400">Time passed</h4>
              {result.world_time && (
                <p className="text-[10px] text-slate-400">World time: {result.world_time}</p>
              )}
              {result.time_line.map((a, i) => (
                <p key={i} className="text-[10px] text-slate-500">
                  • {a.delta}{" "}
                  {a.from_at
                    ? `(${a.from_at.slice(0, 10)} → ${a.to_at.slice(0, 10)})`
                    : `(set ${a.to_at.slice(0, 10)})`}
                </p>
              ))}
            </div>
          )}
          {result.transcript.length > 0 && (
            <div>
              <h4 className="text-[9px] font-bold tracking-widest uppercase text-slate-500 mb-1">
                Transcript tail{result.session_title ? ` — ${result.session_title}` : ""}
              </h4>
              {result.transcript.map((line, i) => (
                <p key={i} className="text-[10px] text-slate-400 mb-0.5">
                  <span className="text-slate-600">{line.role}:</span> {line.content}
                </p>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function ImproviseLookup({
  universeId,
  kind,
}: {
  universeId: string;
  kind: "name" | "complication";
}) {
  const [context, setContext] = useState("");
  const [result, setResult] = useState<ImproviseResponse | null>(null);

  const lookup = useMutation({
    mutationFn: () => gmTableApi.improvise({ universe_id: universeId, kind, context, count: 3 }),
    onSuccess: setResult,
  });

  return (
    <div className="space-y-3">
      <textarea
        value={context}
        onChange={(e) => setContext(e.target.value)}
        placeholder={
          kind === "name"
            ? "Who needs a name? ('a dock warden who owes Mira a favour')"
            : "What is happening? ('the party is stalling at the gate')"
        }
        className="input-cyber w-full h-16 resize-none text-xs"
      />
      <button
        onClick={() => lookup.mutate()}
        disabled={lookup.isPending}
        className="btn-cyber text-xs py-1 px-3"
      >
        {lookup.isPending ? <Loader2 className="w-3 h-3 animate-spin" /> : <Wand2 className="w-3 h-3" />}
        {kind === "name" ? "Give me names" : "Complicate things"}
      </button>
      {lookup.isError && <p className="text-[10px] text-red-400">Generation failed — try again.</p>}
      {result && (
        <div className="space-y-1.5">
          {result.suggestions.map((s, i) => (
            <div key={i} className="glass-dark rounded-lg border border-white/5 px-2 py-1.5 text-xs text-slate-200">
              {s}
            </div>
          ))}
          {result.rationale && <p className="text-[10px] text-slate-500">{result.rationale}</p>}
        </div>
      )}
    </div>
  );
}

function RulesLookup({ universeId, systemId }: { universeId: string; systemId: string | null }) {
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<RulesAnswer | null>(null);

  const lookup = useMutation({
    mutationFn: () =>
      gmTableApi.lookupRules({
        system_id: systemId,
        universe_id: systemId ? null : universeId,
        question: question.trim(),
      }),
    onSuccess: setResult,
  });

  return (
    <div className="space-y-3">
      <div className="flex gap-2">
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && question.trim()) lookup.mutate();
          }}
          placeholder="How does grappling work?"
          className="input-cyber flex-1 text-xs"
        />
        <button
          onClick={() => lookup.mutate()}
          disabled={!question.trim() || lookup.isPending}
          className="btn-cyber text-xs py-1 px-3"
          aria-label="Answer question"
        >
          {lookup.isPending ? <Loader2 className="w-3 h-3 animate-spin" /> : <BookOpen className="w-3 h-3" />}
        </button>
      </div>
      {!systemId && (
        <p className="text-[10px] text-amber-400/80">
          No system selected — the universe&apos;s bound system will be used.
        </p>
      )}
      {lookup.isError && <p className="text-[10px] text-red-400">Lookup failed — try again.</p>}
      {result && (
        <div className="glass-dark rounded-xl border border-white/5 p-3 space-y-1.5">
          <p className="text-xs text-slate-200 leading-relaxed">{result.answer}</p>
          <p className="text-[10px] text-emerald-400">
            {result.covered ? `Source: ${result.source || "the system's rules"}` : "Not covered by the system's rules"}
          </p>
        </div>
      )}
    </div>
  );
}
