"use client";

import { Suspense, useState, useEffect, useRef } from "react";
import { useSearchParams } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { useQuery } from "@tanstack/react-query";
import { BookOpen, ChevronDown, ChevronUp, ClipboardList, Dices, FileText, GitBranch, Globe2, Mic, NotebookPen, Search, SlidersHorizontal, Sparkles, Swords, Scroll, AlertTriangle } from "lucide-react";
import { universesApi } from "@/lib/api";
import { useDismissRef } from "@/lib/useDismissRef";
import { SessionRecorder } from "@/components/gm/SessionRecorder";
import { DiceRoller } from "@/components/gm/DiceRoller";
import { RulesPanel } from "@/components/gm/RulesPanel";
import { SessionNotebook } from "@/components/gm/SessionNotebook";

import { GMSelector } from "@/components/gm/GMSelector";
import { ActiveToolPanel, type GmToolPanelId } from "@/components/gm/ActiveToolPanel";
import {
  GmStepper,
  readStoredGmStep,
  writeStoredGmStep,
  type GmStep,
} from "@/components/gm/GmStepper";
import { WrapUpModal } from "@/components/gm/WrapUpModal";
import { FirstRunGuide, FirstUseTour } from "@/components/gm/FirstRunGuide";
import { GmOfflineBanner } from "@/components/gm/GmOfflineBanner";
import { useGmShortcuts, focusFirstVisible } from "@/components/gm/useGmShortcuts";
import { useGmPanelPrefs, visibleOrderedPanels } from "@/lib/gm-panel-prefs";
import { useWorldContext } from "@/lib/world-context";
import { cn } from "@/lib/utils";

// ═══════════════════════════════════════════════════════════════
//  Page
// ═══════════════════════════════════════════════════════════════

const GM_PANELS = [
  { id: "rules",          label: "Rules",          icon: BookOpen },
  { id: "recorder",       label: "Recorder",       icon: Mic },
  { id: "notebook",       label: "Scratchpad",     icon: NotebookPen },
  { id: "dice",           label: "Dice",            icon: Dices },
  { id: "combat",         label: "Combat",          icon: Swords },
  { id: "prep-table",     label: "Tonight",        icon: ClipboardList },
  { id: "lookups",        label: "Lookups",        icon: Search },
  { id: "session-log",    label: "Session Log",    icon: FileText },
  { id: "ask-world",      label: "Ask",             icon: Globe2 },
  { id: "hooks",          label: "Hooks",           icon: Sparkles },
  { id: "threads",        label: "Threads",        icon: GitBranch },
  { id: "contradictions", label: "Contradictions",  icon: AlertTriangle },
  { id: "session-prep",   label: "Prep",            icon: ClipboardList },
  { id: "handouts",       label: "Handouts",        icon: Scroll },
] as const;

type GMPanel = (typeof GM_PANELS)[number]["id"];

const TOOL_PANEL_IDS: GMPanel[] = [
  "prep-table",
  "lookups",
  "combat",
  "session-log",
  "ask-world",
  "hooks",
  "threads",
  "contradictions",
  "session-prep",
  "handouts",
];

// The Prep step narrows the tools column to the pre-session panels.
const PREP_PANEL_IDS: GMPanel[] = ["session-prep", "hooks", "threads", "handouts"];

function GMAssistantPageContent() {
  const searchParams = useSearchParams();
  const requestedUniverseId = searchParams.get("universe");
  const [universeId, setUniverseId] = useState<string | null>(requestedUniverseId);
  const [universeLabel, setUniverseLabel] = useState<string | null>(null);
  const [multiverseId, setMultiverseId] = useState<string | null>(null);
  const [activeStoryId, setActiveStoryId] = useState<string | null>(null);
  const [systemId, setSystemId] = useState<string | null>(null);
  const [systemOverridden, setSystemOverridden] = useState(false);
  const [activePanel, setActivePanel] = useState<GMPanel>("recorder");
  const [centerTab, setCenterTab] = useState<"recorder" | "notebook">("recorder");
  // Prep → Run → Wrap-up (UX-5). Wrap is transient; prep/run persist per universe.
  const [step, setStepState] = useState<GmStep>("run");
  const prevStableStepRef = useRef<GmStep>("run");
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const { prefs, toggleHidden, move } = useGmPanelPrefs();
  const [customizeOpen, setCustomizeOpen] = useState(false);
  const customizeRef = useDismissRef<HTMLDivElement>(() => setCustomizeOpen(false), customizeOpen);
  const toolPool: GMPanel[] = step === "prep" ? PREP_PANEL_IDS : TOOL_PANEL_IDS;
  const visibleToolPanels = visibleOrderedPanels(toolPool, prefs);
  // A hidden/non-tool active panel falls back to the first visible tool panel.
  const effectiveToolPanel: GMPanel | null = visibleToolPanels.includes(activePanel)
    ? activePanel
    : (visibleToolPanels[0] ?? null);

  // Resolve a deep-linked universe's label once
  const { data: requestedUniverse } = useQuery({
    queryKey: ["universe", requestedUniverseId],
    queryFn: () => universesApi.getUniverse(requestedUniverseId!),
    enabled: !!requestedUniverseId,
  });
  useEffect(() => {
    if (requestedUniverse && universeId === requestedUniverse.id && !universeLabel) {
      setUniverseLabel(requestedUniverse.name);
    }
  }, [requestedUniverse, universeId, universeLabel]);

  // The rules panel follows the selected universe's bound game system (P2.2)
  // unless the GM picked a system by hand — a manual choice always wins.
  const { data: selectedUniverse } = useQuery({
    queryKey: ["universe", universeId],
    queryFn: () => universesApi.getUniverse(universeId!),
    enabled: !!universeId,
  });
  useEffect(() => {
    if (systemOverridden) return;
    setSystemId(selectedUniverse?.default_game_system_id ?? null);
  }, [selectedUniverse, systemOverridden]);

  const handleSystemChange = (id: string | null) => {
    setSystemId(id);
    setSystemOverridden(true);
  };

  // No URL param → adopt the persisted global world once it hydrates (T-077)
  const world = useWorldContext();
  useEffect(() => {
    if (!requestedUniverseId && !universeId && world.universeId) {
      setUniverseId(world.universeId);
      setUniverseLabel(world.universeLabel);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [world.universeId]);

  const handleUniverseChange = (id: string | null, label?: string | null) => {
    setUniverseId(id);
    setUniverseLabel(label ?? null);
  };

  // Restore the persisted step whenever the active universe changes.
  useEffect(() => {
    setStepState(readStoredGmStep(universeId) ?? "run");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [universeId]);

  const setStep = (next: GmStep) => {
    if (next === step) return;
    if (step !== "wrap") prevStableStepRef.current = step;
    writeStoredGmStep(universeId, next);
    setStepState(next);
  };

  // Closing wrap-up returns to the step it was opened from.
  const closeWrap = () => {
    if (step === "wrap") setStepState(prevStableStepRef.current);
  };

  // The narrow single-panel view must stay inside the active step's pool.
  useEffect(() => {
    if (step === "wrap") return;
    const pool = step === "prep" ? PREP_PANEL_IDS : TOOL_PANEL_IDS;
    if (TOOL_PANEL_IDS.includes(activePanel) && !pool.includes(activePanel)) {
      const first = visibleOrderedPanels(pool, prefs)[0];
      if (first) setActivePanel(first);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step]);

  // Table shortcuts (UX-5): r = dice, n = new note, j/k = prev/next entry.
  const [pendingFocus, setPendingFocus] = useState<"dice" | "note" | null>(null);
  useEffect(() => {
    if (!pendingFocus) return;
    focusFirstVisible(
      pendingFocus === "dice"
        ? '[data-testid="dice-expr"]'
        : '[data-testid="session-notebook-input"]',
    );
    setPendingFocus(null);
  }, [pendingFocus, centerTab, activePanel]);

  useGmShortcuts({
    onRoll: () => {
      if (!focusFirstVisible('[data-testid="dice-expr"]')) {
        // Dice panel isn't visible on the narrow layout — switch, then retry.
        setActivePanel("dice");
        setPendingFocus("dice");
      }
    },
    onNewNote: () => {
      setCenterTab("notebook");
      setActivePanel("notebook");
      setPendingFocus("note");
    },
  });

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div className="flex items-center gap-4 px-6 py-3 border-b border-white/5 glass-dark flex-shrink-0 flex-wrap">
        <ClipboardList className="w-5 h-5 text-emerald-400 flex-shrink-0" />
        <h1 className="text-sm font-bold text-slate-200">GM Assistant</h1>
        <div className="h-5 w-px bg-white/10" />
        <GmStepper step={step} onStepChange={setStep} wrapDisabled={!universeId} />
        <div className="h-5 w-px bg-white/10" />
        <GMSelector
          universeId={universeId}
          systemId={systemId}
          onUniverseChange={handleUniverseChange}
          onSystemChange={handleSystemChange}
          onMultiverseChange={setMultiverseId}
        />

        {/* Panel tabs (mobile/narrow only; desktop has fixed columns) */}
        <div className="ml-auto flex items-center gap-1 xl:hidden">
          {GM_PANELS.filter(
            (p) => !TOOL_PANEL_IDS.includes(p.id) || toolPool.includes(p.id),
          ).map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              onClick={() => setActivePanel(id)}
              className={cn(
                "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all border max-xl:min-h-11",
                activePanel === id
                  ? "bg-emerald-500/10 text-emerald-300 border-emerald-500/25"
                  : "text-slate-500 hover:text-slate-300 border-transparent hover:bg-white/4",
              )}
            >
              <Icon className="w-3.5 h-3.5" />
              {label}
            </button>
          ))}
        </div>
      </div>

      <GmOfflineBanner />
      <FirstUseTour />

      {/* Three-panel layout (desktop: side by side, controlled via tab on mobile) */}
      <div className="flex-1 overflow-hidden">
        <div className="hidden xl:flex h-full">
          {/* Rules */}
          <div className="w-72 flex-shrink-0 border-r border-white/5 flex flex-col overflow-hidden">
            <div className="px-4 py-3 border-b border-white/5 flex-shrink-0">
              <div className="flex items-center gap-2">
                <BookOpen className="w-3.5 h-3.5 text-emerald-400" />
                <span className="text-xs font-semibold text-slate-300">Rules Reference</span>
              </div>
            </div>
            <div className="flex-1 overflow-hidden">
              <RulesPanel systemId={systemId} />
            </div>
          </div>

          {/* Center: Recorder / Scratchpad */}
          <div className="flex-1 border-r border-white/5 flex flex-col overflow-hidden">
            <div className="flex items-center gap-1 px-3 py-2 border-b border-white/5 flex-shrink-0">
              {([
                { id: "recorder", label: "Session Recorder", icon: Mic },
                { id: "notebook", label: "Scratchpad", icon: NotebookPen },
              ] as const).map(({ id, label, icon: Icon }) => (
                <button
                  key={id}
                  onClick={() => setCenterTab(id)}
                  className={cn(
                    "flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-medium transition-all border max-xl:min-h-11",
                    centerTab === id
                      ? "bg-emerald-500/10 text-emerald-300 border-emerald-500/25"
                      : "text-slate-500 hover:text-slate-300 border-transparent hover:bg-white/4",
                  )}
                >
                  <Icon className="w-3 h-3" />
                  {label}
                </button>
              ))}
            </div>
            <div className="flex-1 overflow-hidden flex flex-col">
              {centerTab === "recorder" ? (
                universeId ? (
                  <SessionRecorder universeId={universeId} universeLabel={universeLabel} onActiveStoryChange={setActiveStoryId} onActiveSessionChange={setActiveSessionId} />
                ) : (
                  <FirstRunGuide />
                )
              ) : (
                <SessionNotebook universeId={universeId} multiverseId={multiverseId} storyId={activeStoryId} />
              )}
            </div>
          </div>

          {/* GM Tools column */}
          <div className="w-96 flex-shrink-0 flex flex-col overflow-hidden">
            {/* Sub-tabs for GM tools (order/visibility is user-modifiable) */}
            <div className="relative flex items-center gap-1 px-3 py-2 border-b border-white/5 flex-shrink-0 overflow-x-auto">
              {GM_PANELS.filter((p) => visibleToolPanels.includes(p.id)).map(({ id, label, icon: Icon }) => (
                <button
                  key={id}
                  onClick={() => setActivePanel(id as GMPanel)}
                  className={cn(
                    "flex items-center gap-1 px-2 py-1 rounded-lg text-[10px] font-medium transition-all border whitespace-nowrap",
                    activePanel === id
                      ? "bg-emerald-500/10 text-emerald-300 border-emerald-500/25"
                      : "text-slate-500 hover:text-slate-300 border-transparent hover:bg-white/4"
                  )}
                >
                  <Icon className="w-3 h-3" />
                  {label}
                </button>
              ))}
              <div ref={customizeRef} className="contents">
                <button
                  onClick={() => setCustomizeOpen((o) => !o)}
                  aria-label="Customize panels"
                  className="ml-auto flex-shrink-0 text-slate-600 hover:text-slate-300"
                >
                  <SlidersHorizontal className="w-3.5 h-3.5" />
                </button>
                {customizeOpen && (
                  <div className="absolute right-2 top-9 z-20 w-52 rounded-lg border border-white/10 bg-slate-900/95 p-2 shadow-xl">
                  {GM_PANELS.filter((p) => TOOL_PANEL_IDS.includes(p.id)).map(({ id, label }) => (
                    <div key={id} className="flex items-center gap-1.5 py-0.5">
                      <input
                        type="checkbox"
                        id={`panel-vis-${id}`}
                        checked={!prefs.hidden.includes(id)}
                        onChange={() => toggleHidden(id)}
                        className="h-3 w-3 accent-emerald-400"
                      />
                      <label htmlFor={`panel-vis-${id}`} className="flex-1 text-xs text-slate-300">
                        {label}
                      </label>
                      <button
                        onClick={() => move(id, -1, [...TOOL_PANEL_IDS])}
                        aria-label={`Move ${label} up`}
                        className="text-slate-600 hover:text-slate-300"
                      >
                        <ChevronUp className="w-3 h-3" />
                      </button>
                      <button
                        onClick={() => move(id, 1, [...TOOL_PANEL_IDS])}
                        aria-label={`Move ${label} down`}
                        className="text-slate-600 hover:text-slate-300"
                      >
                        <ChevronDown className="w-3 h-3" />
                      </button>
                    </div>
                  ))}
                </div>
              )}
              </div>
            </div>
            <div className="flex-1 overflow-hidden">
              {visibleToolPanels.length === 0 ? (
                <div className="flex h-full flex-col items-center justify-center gap-2 p-6 text-center">
                  <SlidersHorizontal className="h-8 w-8 text-slate-700" />
                  <p className="text-xs text-slate-600">All panels hidden — customize to re-enable</p>
                </div>
              ) : (
                <ActiveToolPanel
                  panelId={effectiveToolPanel as GmToolPanelId | null}
                  universeId={universeId}
                  systemId={systemId}
                />
              )}
            </div>
          </div>

          {/* Dice */}
          <div className="w-64 flex-shrink-0 flex flex-col overflow-hidden px-4 py-4">
            <div className="flex items-center gap-2 mb-4">
              <Dices className="w-3.5 h-3.5 text-emerald-400" />
              <span className="text-xs font-semibold text-slate-300">Dice Roller</span>
            </div>
            <DiceRoller />
          </div>
        </div>

        {/* Mobile / narrow: single panel view */}
        <div className="xl:hidden h-full flex flex-col overflow-hidden">
          <AnimatePresence mode="wait">
            <motion.div
              key={activePanel}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -6 }}
              transition={{ duration: 0.12 }}
              className="flex-1 overflow-hidden flex flex-col"
            >
              {activePanel === "rules" && (
                <div className="flex-1 overflow-hidden">
                  <RulesPanel systemId={systemId} />
                </div>
              )}
              {activePanel === "recorder" && (
                <div className="flex-1 overflow-hidden flex flex-col">
                  {universeId ? (
                    <SessionRecorder universeId={universeId} universeLabel={universeLabel} onActiveStoryChange={setActiveStoryId} onActiveSessionChange={setActiveSessionId} />
                  ) : (
                    <FirstRunGuide />
                  )}
                </div>
              )}
              {activePanel === "notebook" && (
                <div className="flex-1 overflow-hidden flex flex-col">
                  <SessionNotebook universeId={universeId} multiverseId={multiverseId} storyId={activeStoryId} />
                </div>
              )}
              {activePanel === "dice" && (
                <div className="flex-1 overflow-hidden px-4 py-4">
                  <DiceRoller />
                </div>
              )}
              {TOOL_PANEL_IDS.includes(activePanel) && (
                <div className="flex-1 overflow-hidden">
                  <ActiveToolPanel
                    panelId={activePanel as GmToolPanelId}
                    universeId={universeId}
                    systemId={systemId}
                  />
                </div>
              )}
            </motion.div>
          </AnimatePresence>
        </div>
      </div>

      {/* Wrap-up step — opens the existing wrap-up flow (transient step). */}
      {step === "wrap" && universeId && (
        activeSessionId ? (
          <WrapUpModal
            sessionId={activeSessionId}
            universeId={universeId}
            storyId={activeStoryId}
            onClose={closeWrap}
          />
        ) : (
          <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
            role="dialog"
            aria-modal="true"
            data-testid="gm-wrap-empty"
          >
            <div className="glass-dark rounded-xl border border-white/10 p-5 max-w-sm space-y-3">
              <p className="text-xs text-slate-300">
                No recording to wrap up yet — log at least one entry in the Session
                Recorder first.
              </p>
              <button type="button" onClick={closeWrap} className="btn-cyber text-xs px-3 py-1.5">
                Close
              </button>
            </div>
          </div>
        )
      )}
    </div>
  );
}

export default function GMAssistantPage() {
  return (
    <Suspense fallback={<div className="p-6 text-sm text-slate-500">Loading GM assistant…</div>}>
      <GMAssistantPageContent />
    </Suspense>
  );
}
