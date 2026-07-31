# Two-Tier Hub UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure the MONITOR web UI into a two-tier hub — a player-facing Lobby (Campaigns landing page at `/` + a separate Light RP screen at `/light-rp`), a builder Workbench (World Forge + GM Assistant with a new "ask the world" chat panel), and a first-class Configuration section at `/config` — plus LLM-registry-integrated image generation (MiniMax `image-01`, Google Gemini `gemini-2.5-flash-image`) exposed as "✨ Generate portrait" on character cards and "🖼 Generate scene image" in chats, with images stored in MinIO and served via presigned URLs.

**Architecture:** Implements `docs/superpowers/specs/2026-07-31-ui-two-tier-hub-design.md` exactly. No new databases and no new backend aggregation endpoints: the Lobby composes the existing `chatApi.listSessions`, `universesApi.listUniverses`, and `storiesApi.listStories` endpoints client-side. Image generation adds one data-layer adapter module (`monitor_data/llm/image_providers.py`) and one UI-backend router (`routers/image_gen.py` mounted at `/api/image`); provider configuration reuses the PostgreSQL `llm_providers` table via a new `ModelRole.IMAGE` role — no schema migration needed because the `role` column is unconstrained `TEXT`.

**Tech Stack:** Next.js 15 App Router + React 19 + TanStack Query + Tailwind (existing `glass`, `input-cyber`, `btn-cyber`, `btn-ghost` classes) + lucide-react on the frontend; FastAPI + Pydantic v2 on the UI backend; Python 3.11 data-layer with httpx, aiobotocore (MinIO), pymongo; Vitest + Testing Library + happy-dom (frontend), pytest + FastAPI TestClient (backend).

## Global Constraints

- Three-layer dependency rule: CLI (3) → agents (2) → data-layer (1), never import upward. The image adapter lives in data-layer (`packages/data-layer/src/monitor_data/llm/image_providers.py`); UI-backend routers call it through data-layer (`monitor_data.llm.image_providers`, `monitor_data.db.minio`, `monitor_data.db.postgres`) and never talk HTTP to image providers directly.
- Line-length 100, Python 3.11, mypy strict (`uv run mypy packages/*/src --cache-dir /tmp/mypy-cache`).
- Run `python scripts/check_layer_dependencies.py` before committing backend changes.
- Test commands: `uv run pytest packages/data-layer -q`, `uv run pytest packages/ui/backend -q`, `cd packages/ui/frontend && npm test` (vitest run).
- Lint/format: `uv run ruff check packages` + `uv run ruff format packages`; frontend types: `cd packages/ui/frontend && npx tsc --noEmit`.
- Frontend tests use vitest with the `// @vitest-environment happy-dom` pragma and the `@` → `src` alias; page/component tests wrap renders in `QueryClientProvider` and stub APIs with `vi.spyOn(api.<ns>, "<method>")`.
- Backend router tests build a bare `FastAPI()` app, `include_router(router)`, and use `fastapi.testclient.TestClient` with `AsyncMock`/`patch` for postgres/Mongo/MinIO — never real databases, never real network.
- Only CanonKeeper writes to Neo4j — this plan adds no graph writes at all; characters are MongoDB documents updated via `routers/character_storage.update_character`.
- Standard per-task commit steps are kept; the executing skill's review gates handle confirmation.

---

## Task 1: Navigation restructure — three tiers, no footer pickers, dead-link fix, redirects

**Files:**

- Modify: `packages/ui/frontend/src/components/Sidebar.tsx`
- Modify: `packages/ui/frontend/next.config.ts`
- Modify: `packages/ui/frontend/src/components/play/SetupPanel.tsx` (dead `/universes` link at line 462–467)
- Test: `packages/ui/frontend/src/components/Sidebar.test.tsx` (rewrite)

**Interfaces:**

- Consumes: `usePathname()` from `next/navigation`; existing `ConnectionStatus` component.
- Produces: `NAV_GROUPS` with three groups — `lobby` (Campaigns `/`, Light RP `/light-rp`), `workbench` (World Forge `/forge`, GM Assistant `/gm`), `configuration` (Configuration `/config`). Redirects: `/settings` → `/config`, `/characters` → `/light-rp` (both `permanent: false`, matching the existing redirect style).

Notes:

- `/play`, `/search`, `/explorer`, `/history` stay live as routes (deep-linked from the Lobby and elsewhere) but leave the sidebar, per the approved IA. `/universes` already redirects to `/forge/worlds` in `next.config.ts`; the SetupPanel fix points the raw `<a>` straight at `/forge/worlds` via `next/link` so it stops doing a full-page redirect hop.
- Active-route detection must special-case `/` (`pathname === href`) or every route would highlight Campaigns.

**Steps:**

- [ ] **Step 1: Write the failing test** — replace `packages/ui/frontend/src/components/Sidebar.test.tsx` entirely:

```tsx
// @vitest-environment happy-dom
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";

// Mock next/navigation so we can drive usePathname per test.
let mockPathname = "/";
vi.mock("next/navigation", () => ({
  usePathname: () => mockPathname,
}));

vi.mock("@/components/ConnectionStatus", () => ({
  ConnectionStatus: () => <div data-testid="connection-status" />,
}));

import { Sidebar } from "./Sidebar";

function renderSidebar(pathname = "/") {
  mockPathname = pathname;
  return render(<Sidebar />);
}

describe("Sidebar two-tier nav", () => {
  it("renders the three tiers: Lobby, Workbench, Configuration", () => {
    renderSidebar();
    expect(screen.getByText("Lobby")).toBeInTheDocument();
    expect(screen.getByText("Workbench")).toBeInTheDocument();
    // "Configuration" appears as both the tier label and its single nav item.
    expect(screen.getAllByText("Configuration").length).toBeGreaterThanOrEqual(2);
    for (const gone of ["Modes", "Forge", "Query", "System"]) {
      expect(screen.queryByText(gone)).not.toBeInTheDocument();
    }
  });

  it("Lobby group contains Campaigns (/) and Light RP (/light-rp)", () => {
    renderSidebar();
    expect(screen.getByRole("link", { name: /Campaigns/ })).toHaveAttribute("href", "/");
    expect(screen.getByRole("link", { name: /Light RP/ })).toHaveAttribute("href", "/light-rp");
  });

  it("Workbench group contains World Forge and GM Assistant only", () => {
    renderSidebar();
    expect(screen.getByRole("link", { name: /World Forge/ })).toHaveAttribute("href", "/forge");
    expect(screen.getByRole("link", { name: /GM Assistant/ })).toHaveAttribute("href", "/gm");
    for (const gone of ["Play", "Characters", "Search", "Explorer", "History"]) {
      expect(screen.queryByRole("link", { name: gone })).not.toBeInTheDocument();
    }
  });

  it("Configuration group links /config", () => {
    renderSidebar();
    expect(screen.getByRole("link", { name: /Configuration/ })).toHaveAttribute("href", "/config");
  });

  it("no longer renders WorldPicker or ModeSwitcher in the footer", () => {
    renderSidebar();
    expect(screen.queryByTestId("world-picker")).not.toBeInTheDocument();
    expect(screen.queryByTestId("mode-switcher")).not.toBeInTheDocument();
    expect(screen.getByTestId("connection-status")).toBeInTheDocument();
  });

  it("highlights Campaigns only on exactly /", () => {
    renderSidebar("/light-rp");
    expect(screen.getByRole("link", { name: /Light RP/ })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: /Campaigns/ })).not.toHaveAttribute("aria-current");
  });

  it("highlights World Forge on nested forge routes", () => {
    renderSidebar("/forge/packs");
    expect(screen.getByRole("link", { name: /World Forge/ })).toHaveAttribute("aria-current", "page");
  });
});
```

- [ ] **Step 2: Run the test, expect failure:**

```bash
cd packages/ui/frontend && npx vitest run src/components/Sidebar.test.tsx
```

Expected: FAIL — old group labels ("Modes", "Forge", ...) render instead of the new tiers.

- [ ] **Step 3: Rewrite `packages/ui/frontend/src/components/Sidebar.tsx`** — full replacement:

```tsx
"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import {
  Activity,
  ChevronLeft,
  ChevronRight,
  ClipboardList,
  FlaskConical,
  Home,
  MessagesSquare,
  Settings,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { ConnectionStatus } from "@/components/ConnectionStatus";

// ─── Navigation structure ──────────────────────────────────────
// Two-tier hub IA (2026-07-31 spec): Lobby (player) / Workbench (builder) /
// Configuration. World selection lives on universe cards; the old footer
// WorldPicker/ModeSwitcher dropdowns are gone.

const NAV_GROUPS = [
  {
    id: "lobby",
    label: "Lobby",
    items: [
      { href: "/",         icon: Home,           label: "Campaigns", sub: "Your worlds & sessions",        accent: "cyan"   },
      { href: "/light-rp", icon: MessagesSquare, label: "Light RP",  sub: "Story-free character chats",    accent: "purple" },
    ],
  },
  {
    id: "workbench",
    label: "Workbench",
    items: [
      { href: "/forge", icon: FlaskConical,  label: "World Forge",  sub: "Author worlds, packs & canon",  accent: "cyan"    },
      { href: "/gm",    icon: ClipboardList, label: "GM Assistant", sub: "Dice, books, prep & canon Q&A", accent: "emerald" },
    ],
  },
  {
    id: "configuration",
    label: "Configuration",
    items: [
      { href: "/config", icon: Settings, label: "Configuration", sub: "LLMs, prompts & infrastructure", accent: "emerald" },
    ],
  },
] as const;

type Accent = "cyan" | "purple" | "emerald";

const ACCENT_CLASSES: Record<Accent, { active: string; icon: string; indicator: string }> = {
  cyan: {
    active: "bg-cyan-500/10 border-cyan-500/25 text-cyan-300",
    icon: "text-cyan-400",
    indicator: "bg-cyan-500",
  },
  purple: {
    active: "bg-purple-500/10 border-purple-500/25 text-purple-300",
    icon: "text-purple-400",
    indicator: "bg-purple-500",
  },
  emerald: {
    active: "bg-emerald-500/10 border-emerald-500/25 text-emerald-300",
    icon: "text-emerald-400",
    indicator: "bg-emerald-500",
  },
};

function isActive(pathname: string, href: string): boolean {
  // "/" prefix-matches everything — only exact match counts for the landing.
  return href === "/" ? pathname === "/" : pathname.startsWith(href);
}

// ─── Component ────────────────────────────────────────────────

export function Sidebar() {
  const [collapsed, setCollapsed] = useState(false);
  const pathname = usePathname();

  return (
    <motion.nav
      animate={{ width: collapsed ? 60 : 224 }}
      initial={false}
      transition={{ type: "spring", stiffness: 320, damping: 32 }}
      className="glass flex-shrink-0 flex flex-col h-full border-r border-white/5 z-10 relative overflow-hidden"
    >
      {/* Logo */}
      <div className="flex items-center gap-3 px-3.5 py-5 border-b border-white/5 overflow-hidden flex-shrink-0">
        <div className="flex-shrink-0 w-8 h-8 rounded-lg bg-cyan-500/10 border border-cyan-500/25 flex items-center justify-center shadow-cyan-glow">
          <Activity className="w-4 h-4 text-cyan-400" />
        </div>
        <AnimatePresence mode="wait">
          {!collapsed && (
            <motion.div
              initial={{ opacity: 0, x: -8 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -8 }}
              transition={{ duration: 0.15 }}
              className="overflow-hidden"
            >
              <div className="text-xs font-bold text-neon-cyan tracking-[0.2em] whitespace-nowrap">
                MONITOR
              </div>
              <div className="text-[10px] text-slate-600 whitespace-nowrap tracking-wide">
                Narrative AI
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Navigation groups */}
      <div className="flex-1 py-2 px-2 overflow-y-auto overflow-x-hidden space-y-1">
        {NAV_GROUPS.map((group, gi) => (
          <div key={group.id} className={cn(gi > 0 && "pt-1")}>
            {/* Section divider + label */}
            <div className={cn(
              "flex items-center gap-2 px-2 mb-0.5 overflow-hidden",
              gi > 0 ? "mt-1 pt-1 border-t border-white/5" : "",
            )}>
              <AnimatePresence mode="wait">
                {!collapsed ? (
                  <motion.span
                    key="label"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    transition={{ duration: 0.12 }}
                    className="text-[9px] font-semibold tracking-[0.18em] uppercase text-slate-600 whitespace-nowrap"
                  >
                    {group.label}
                  </motion.span>
                ) : (
                  <motion.div
                    key="dot"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    className="w-full flex justify-center"
                  >
                    <div className="w-3 h-px bg-white/10" />
                  </motion.div>
                )}
              </AnimatePresence>
            </div>

            {group.items.map(({ href, icon: Icon, label, sub, accent }) => {
              const active = isActive(pathname, href);
              const ac = ACCENT_CLASSES[accent as Accent];
              return (
                <Link
                  key={href}
                  href={href}
                  aria-current={active ? "page" : undefined}
                  className="block"
                >
                  <motion.div
                    whileHover={{ x: collapsed ? 0 : 2 }}
                    className={cn(
                      "relative flex items-center gap-3 px-2.5 py-2 rounded-lg border transition-all duration-200 overflow-hidden",
                      active
                        ? ac.active
                        : "border-transparent text-slate-400 hover:text-slate-200 hover:bg-white/4",
                    )}
                  >
                    {active && (
                      <motion.div
                        layoutId="sidebar-indicator"
                        className={cn(
                          "absolute left-0 top-2 bottom-2 w-0.5 rounded-full",
                          ac.indicator,
                        )}
                      />
                    )}

                    <Icon className={cn("w-4 h-4 flex-shrink-0", active ? ac.icon : "")} />

                    <AnimatePresence mode="wait">
                      {!collapsed && (
                        <motion.div
                          initial={{ opacity: 0 }}
                          animate={{ opacity: 1 }}
                          exit={{ opacity: 0 }}
                          transition={{ duration: 0.12 }}
                          className="min-w-0"
                        >
                          <div className="text-sm font-medium leading-tight whitespace-nowrap">
                            {label}
                          </div>
                          <div className="text-[10px] text-slate-600 whitespace-nowrap mt-0.5">
                            {sub}
                          </div>
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </motion.div>
                </Link>
              );
            })}
          </div>
        ))}
      </div>

      {/* Footer — connection status + collapse only (no world/mode pickers) */}
      <div className="border-t border-white/5 px-2 py-3 space-y-1 flex-shrink-0">
        <AnimatePresence>
          {!collapsed && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="px-2.5 pb-1"
            >
              <div className="text-[10px] text-slate-700 font-mono">v0.1.0-dev</div>
            </motion.div>
          )}
        </AnimatePresence>
        <ConnectionStatus />
        <button
          onClick={() => setCollapsed((c) => !c)}
          className="w-full flex items-center justify-center p-2 rounded-lg text-slate-600 hover:text-cyan-400 hover:bg-cyan-500/5 transition-all duration-150"
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {collapsed ? <ChevronRight className="w-4 h-4" /> : <ChevronLeft className="w-4 h-4" />}
        </button>
      </div>
    </motion.nav>
  );
}
```

- [ ] **Step 4: Add redirects in `packages/ui/frontend/next.config.ts`** — extend the existing `redirects()` array:

```ts
  async redirects() {
    return [
      { source: "/worlds", destination: "/forge/worlds", permanent: false },
      { source: "/snapshots", destination: "/forge/snapshots", permanent: false },
      { source: "/systems", destination: "/forge/systems", permanent: false },
      { source: "/architect", destination: "/forge/architect", permanent: false },
      { source: "/universes", destination: "/forge/worlds", permanent: false },
      // Two-tier hub: settings content moves to /config; the character
      // roster is superseded by the Light RP screen.
      { source: "/settings", destination: "/config", permanent: false },
      { source: "/characters", destination: "/light-rp", permanent: false },
    ];
  },
```

- [ ] **Step 5: Fix the dead link in `packages/ui/frontend/src/components/play/SetupPanel.tsx`** — add `import Link from "next/link";` to the imports and replace the raw anchor at the bottom of the panel:

```tsx
        <Link
          href="/forge/worlds"
          className="px-3 py-2 rounded-lg border border-white/10 text-xs text-slate-300 hover:bg-white/5 transition-all"
        >
          Manage Worlds
        </Link>
```

- [ ] **Step 6: Run tests + typecheck, expect pass:**

```bash
cd packages/ui/frontend && npx vitest run src/components/Sidebar.test.tsx && npx tsc --noEmit
```

Expected: all 7 sidebar tests pass; tsc clean. (`WorldPicker.test.tsx` keeps passing — the component still exists, it is just no longer mounted in the sidebar; no changes needed there.)

- [ ] **Step 7: Commit**

```bash
git add packages/ui/frontend/src/components/Sidebar.tsx packages/ui/frontend/src/components/Sidebar.test.tsx packages/ui/frontend/next.config.ts packages/ui/frontend/src/components/play/SetupPanel.tsx
git commit -m "feat(ui): two-tier sidebar nav, remove footer pickers, /settings+/characters redirects"
```

---

## Task 2: Lobby Campaigns tab at `/` — universe cards + continue-playing rail

**Files:**

- Create: `packages/ui/frontend/src/components/lobby/ContinuePlayingRail.tsx`
- Create: `packages/ui/frontend/src/components/lobby/UniverseCardGrid.tsx`
- Modify: `packages/ui/frontend/src/app/page.tsx` (full rewrite — current mode-tiles landing is replaced)
- Test: `packages/ui/frontend/src/app/page.test.tsx`

**Interfaces:**

- Consumes: `chatApi.listSessions(): Promise<Session[]>` (`GET /api/chat`); `universesApi.listUniverses(): Promise<Universe[]>` (`GET /api/universes/universes`); `storiesApi.listStories({ limit }): Promise<{ stories: StorySummary[]; total: number }>` (`GET /api/stories`). Types `Session`, `Universe`, `StorySummary` from `@/lib/types`.
- Produces:
  - `ContinuePlayingRail({ sessions }: { sessions: Session[] })` — renders up to 6 most-recent sessions; each row links "Continue" → `/play?session={id}` (PlayConsole reads the `session` search param at `PlayConsole.tsx:162`).
  - `UniverseCardGrid({ universes, latestStoryByUniverse }: { universes: Universe[]; latestStoryByUniverse: Record<string, StorySummary | undefined> })` — card per universe: name, playable-state badge, entity/story counts, latest story title, Play → `/play?universe={id}` (PlayConsole reads `universe` at `PlayConsole.tsx:163`), Stories → `/forge/worlds?universe={id}`.

Playable-state derivation (no backend field exists): `is_active` → `ready`; otherwise `needs review`. Badges are computed in a small exported pure function `playableState(u: Universe): "ready" | "needs review"` so it is unit-testable and easy to extend with an `ingesting` state later.

**Steps:**

- [ ] **Step 1: Write the failing test** — `packages/ui/frontend/src/app/page.test.tsx`:

```tsx
// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import LobbyPage from "./page";
import * as api from "@/lib/api";
import type { Session, Universe, StorySummary } from "@/lib/types";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => "/",
}));

const session: Session = {
  id: "s-1",
  title: "The Ashen Road",
  mode: "autonomous_gm",
  multiverse_id: null,
  universe_id: "u-1",
  universe_label: "Mistlands",
  world_id: null,
  character_id: null,
  created_at: "2026-07-30T10:00:00Z",
  updated_at: "2026-07-31T09:00:00Z",
  message_count: 42,
} as Session;

const universe: Universe = {
  id: "u-1",
  name: "Mistlands",
  multiverse_id: "m-1",
  genre: "dark fantasy",
  description: "A drowned kingdom.",
  tags: [],
  is_active: true,
  entity_count: 120,
  session_count: 3,
  story_count: 2,
  created_at: "2026-07-01T00:00:00Z",
} as Universe;

const story: StorySummary = {
  id: "st-1",
  universe_id: "u-1",
  title: "Salt and Smoke",
  story_type: "campaign",
  status: "active",
  scene_count: 7,
  created_at: "2026-07-20T00:00:00Z",
} as StorySummary;

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <LobbyPage />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.restoreAllMocks();
  vi.spyOn(api.chatApi, "listSessions").mockResolvedValue([session]);
  vi.spyOn(api.universesApi, "listUniverses").mockResolvedValue([universe]);
  vi.spyOn(api.storiesApi, "listStories").mockResolvedValue({ stories: [story], total: 1 });
});

describe("Lobby — Campaigns tab", () => {
  it("shows the continue-playing rail with a resume link to /play?session=", async () => {
    renderPage();
    expect(await screen.findByText("The Ashen Road")).toBeInTheDocument();
    const cont = screen.getByRole("link", { name: /continue/i });
    expect(cont).toHaveAttribute("href", "/play?session=s-1");
  });

  it("shows a universe card with playable state and latest story", async () => {
    renderPage();
    expect(await screen.findByText("Mistlands")).toBeInTheDocument();
    expect(screen.getByText("ready")).toBeInTheDocument();
    expect(screen.getByText("Salt and Smoke")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /^play$/i })).toHaveAttribute("href", "/play?universe=u-1");
    expect(screen.getByRole("link", { name: /stories/i })).toHaveAttribute(
      "href",
      "/forge/worlds?universe=u-1",
    );
  });

  it("has a New campaign call-to-action", async () => {
    renderPage();
    expect(await screen.findByRole("button", { name: /new campaign/i })).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run the test, expect failure:**

```bash
cd packages/ui/frontend && npx vitest run src/app/page.test.tsx
```

Expected: FAIL — current landing shows mode tiles, no rail/cards.

- [ ] **Step 3: Create `packages/ui/frontend/src/components/lobby/ContinuePlayingRail.tsx`:**

```tsx
"use client";

import Link from "next/link";
import { History, Play } from "lucide-react";
import type { Session } from "@/lib/types";
import { formatRelativeTime } from "@/lib/utils";

/** Last-N sessions with one-click resume into the play console. */
export function ContinuePlayingRail({ sessions }: { sessions: Session[] }) {
  const recent = [...sessions]
    .sort((a, b) => (b.updated_at ?? "").localeCompare(a.updated_at ?? ""))
    .slice(0, 6);
  if (recent.length === 0) return null;

  return (
    <section aria-label="Continue playing" className="space-y-2">
      <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
        <History className="w-3.5 h-3.5" /> Continue playing
      </div>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-3">
        {recent.map((s) => (
          <div key={s.id} className="glass flex items-center justify-between gap-3 rounded-xl px-4 py-3">
            <div className="min-w-0">
              <div className="truncate text-sm font-medium text-slate-200">{s.title}</div>
              <div className="mt-0.5 truncate text-[11px] text-slate-500">
                {s.universe_label ?? "Unbound"} · {s.message_count} messages ·{" "}
                {formatRelativeTime(s.updated_at)}
              </div>
            </div>
            <Link
              href={`/play?session=${s.id}`}
              className="btn-cyber flex flex-shrink-0 items-center gap-1.5 px-3 py-1.5 text-xs"
            >
              <Play className="h-3 w-3" /> Continue
            </Link>
          </div>
        ))}
      </div>
    </section>
  );
}
```

- [ ] **Step 4: Create `packages/ui/frontend/src/components/lobby/UniverseCardGrid.tsx`:**

```tsx
"use client";

import Link from "next/link";
import { BookOpen, Globe2, Play } from "lucide-react";
import type { StorySummary, Universe } from "@/lib/types";
import { cn } from "@/lib/utils";

/** Playable-state badge — derived client-side until a real ingestion status exists. */
export function playableState(u: Universe): "ready" | "needs review" {
  return u.is_active ? "ready" : "needs review";
}

const BADGE_CLASSES: Record<ReturnType<typeof playableState>, string> = {
  ready: "bg-emerald-500/10 border-emerald-500/25 text-emerald-300",
  "needs review": "bg-amber-500/10 border-amber-500/25 text-amber-300",
};

export function UniverseCardGrid({
  universes,
  latestStoryByUniverse,
}: {
  universes: Universe[];
  latestStoryByUniverse: Record<string, StorySummary | undefined>;
}) {
  if (universes.length === 0) {
    return (
      <div className="glass rounded-xl px-6 py-10 text-center text-sm text-slate-500">
        No universes yet — author one in the{" "}
        <Link href="/forge" className="text-cyan-300 hover:underline">
          World Forge
        </Link>
        .
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
      {universes.map((u) => {
        const state = playableState(u);
        const latest = latestStoryByUniverse[u.id];
        return (
          <div key={u.id} className="glass flex flex-col gap-3 rounded-2xl p-5">
            <div className="flex items-start justify-between gap-2">
              <div className="flex items-center gap-2.5 min-w-0">
                <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg bg-cyan-500/10 border border-cyan-500/20">
                  <Globe2 className="h-4 w-4 text-cyan-400" />
                </div>
                <div className="min-w-0">
                  <div className="truncate text-sm font-semibold text-slate-100">{u.name}</div>
                  <div className="truncate text-[11px] text-slate-500">
                    {[u.genre, u.tone].filter(Boolean).join(" · ") || "—"}
                  </div>
                </div>
              </div>
              <span
                className={cn(
                  "flex-shrink-0 rounded-md border px-2 py-0.5 text-[10px] font-medium",
                  BADGE_CLASSES[state],
                )}
              >
                {state}
              </span>
            </div>

            <div className="text-[11px] text-slate-500">
              {u.entity_count} entities · {u.story_count ?? 0} stories · {u.session_count} sessions
            </div>

            <div className="flex items-center gap-1.5 text-xs text-slate-400 min-h-[1rem]">
              <BookOpen className="h-3 w-3 flex-shrink-0 text-purple-300" />
              <span className="truncate">{latest ? latest.title : "No stories yet"}</span>
            </div>

            <div className="mt-auto flex gap-2">
              <Link
                href={`/play?universe=${u.id}`}
                className="btn-cyber flex flex-1 items-center justify-center gap-1.5 px-3 py-2 text-xs"
              >
                <Play className="h-3 w-3" /> Play
              </Link>
              <Link
                href={`/forge/worlds?universe=${u.id}`}
                className="btn-ghost flex-1 px-3 py-2 text-center text-xs"
              >
                Stories
              </Link>
            </div>
          </div>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 5: Rewrite `packages/ui/frontend/src/app/page.tsx`** (the "New campaign" button is wired to the wizard in Task 3 — for now it is a real button whose handler is swapped then):

```tsx
"use client";

import { useQuery } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { chatApi, storiesApi, universesApi } from "@/lib/api";
import { ContinuePlayingRail } from "@/components/lobby/ContinuePlayingRail";
import { UniverseCardGrid } from "@/components/lobby/UniverseCardGrid";
import type { StorySummary } from "@/lib/types";

export default function LobbyPage() {
  const sessionsQ = useQuery({ queryKey: ["sessions"], queryFn: chatApi.listSessions });
  const universesQ = useQuery({ queryKey: ["universes"], queryFn: () => universesApi.listUniverses() });
  const storiesQ = useQuery({
    queryKey: ["stories", "lobby"],
    queryFn: () => storiesApi.listStories({ limit: 100 }),
  });

  const latestStoryByUniverse: Record<string, StorySummary | undefined> = {};
  for (const s of storiesQ.data?.stories ?? []) {
    const prev = latestStoryByUniverse[s.universe_id];
    if (!prev || (s.created_at ?? "") > (prev.created_at ?? "")) {
      latestStoryByUniverse[s.universe_id] = s;
    }
  }

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-8 p-8">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-100">Campaigns</h1>
          <p className="mt-1 text-sm text-slate-500">
            Jump back in, or start a new campaign in one of your worlds.
          </p>
        </div>
        <button type="button" className="btn-cyber flex items-center gap-2 px-4 py-2 text-sm">
          <Plus className="h-4 w-4" /> New campaign
        </button>
      </header>

      <ContinuePlayingRail sessions={sessionsQ.data ?? []} />

      <section aria-label="Playable universes" className="space-y-2">
        <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
          Playable universes
        </div>
        {universesQ.isLoading ? (
          <div className="text-sm text-slate-500">Loading universes…</div>
        ) : (
          <UniverseCardGrid
            universes={universesQ.data ?? []}
            latestStoryByUniverse={latestStoryByUniverse}
          />
        )}
      </section>
    </div>
  );
}
```

- [ ] **Step 6: Run tests + typecheck, expect pass:**

```bash
cd packages/ui/frontend && npx vitest run src/app/page.test.tsx && npx tsc --noEmit
```

Expected: 3 tests pass, tsc clean.

- [ ] **Step 7: Commit**

```bash
git add packages/ui/frontend/src/components/lobby packages/ui/frontend/src/app/page.tsx packages/ui/frontend/src/app/page.test.tsx
git commit -m "feat(ui): lobby campaigns tab with universe cards and continue-playing rail"
```

---

## Task 3: NewCampaignWizard — guided step wizard replacing the dropdown chain

**Files:**

- Create: `packages/ui/frontend/src/components/lobby/NewCampaignWizard.tsx`
- Modify: `packages/ui/frontend/src/app/page.tsx` (wire the "New campaign" button to the wizard)
- Test: `packages/ui/frontend/src/components/lobby/NewCampaignWizard.test.tsx`

**Interfaces:**

- Consumes: `storiesApi.listStories({ universe_id, limit: 100 })`; `chatApi.createSession(data)` (payload fields per `api.ts:200-229`: `title`, `mode`, `universe_id`, `universe_label`, `story_id`, `tone`, `story_premise`); `useRouter().push` from `next/navigation`.
- Produces: `NewCampaignWizard({ universes, onClose }: { universes: Universe[]; onClose: () => void })`. Three steps: (1) pick universe → (2) pick an existing story or "New story" → (3) title + tone → create. On success routes to `/play?session={id}`.

The wizard deliberately does **not** reproduce the multiverse/system/character dropdown chain from `SetupPanel`: system binding follows the universe's `default_game_system_id` server-side, and character creation happens inside Session Zero in the play console.

**Steps:**

- [ ] **Step 1: Write the failing test** — `packages/ui/frontend/src/components/lobby/NewCampaignWizard.test.tsx`:

```tsx
// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { NewCampaignWizard } from "./NewCampaignWizard";
import * as api from "@/lib/api";
import type { Session, Universe } from "@/lib/types";

const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
}));

vi.mock("@/components/NotificationProvider", () => ({
  useNotify: () => ({ notify: vi.fn() }),
}));

const universe: Universe = {
  id: "u-1",
  name: "Mistlands",
  multiverse_id: "m-1",
  genre: "dark fantasy",
  description: null,
  tags: [],
  is_active: true,
  entity_count: 120,
  session_count: 3,
  story_count: 1,
  created_at: "2026-07-01T00:00:00Z",
} as Universe;

function renderWizard() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <NewCampaignWizard universes={[universe]} onClose={() => {}} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.restoreAllMocks();
  push.mockReset();
  vi.spyOn(api.storiesApi, "listStories").mockResolvedValue({ stories: [], total: 0 });
  vi.spyOn(api.chatApi, "createSession").mockResolvedValue({ id: "s-new" } as Session);
});

describe("NewCampaignWizard", () => {
  it("walks universe → story → details and creates a session", async () => {
    const user = userEvent.setup();
    renderWizard();

    // Step 1: pick the universe
    await user.click(await screen.findByRole("button", { name: /Mistlands/ }));

    // Step 2: start a brand-new story (no existing stories mocked)
    await user.click(await screen.findByRole("button", { name: /new story/i }));

    // Step 3: title + begin
    await user.type(screen.getByLabelText(/campaign title/i), "The Drowned Court");
    await user.click(screen.getByRole("button", { name: /begin campaign/i }));

    expect(api.chatApi.createSession).toHaveBeenCalledWith(
      expect.objectContaining({
        title: "The Drowned Court",
        mode: "autonomous_gm",
        universe_id: "u-1",
        universe_label: "Mistlands",
      }),
    );
    expect(push).toHaveBeenCalledWith("/play?session=s-new");
  });

  it("offers existing stories in step 2", async () => {
    vi.spyOn(api.storiesApi, "listStories").mockResolvedValue({
      stories: [
        {
          id: "st-1",
          universe_id: "u-1",
          title: "Salt and Smoke",
          story_type: "campaign",
          status: "active",
          scene_count: 3,
          created_at: "2026-07-20T00:00:00Z",
        },
      ],
      total: 1,
    });
    const user = userEvent.setup();
    renderWizard();
    await user.click(await screen.findByRole("button", { name: /Mistlands/ }));
    expect(await screen.findByRole("button", { name: /Salt and Smoke/ })).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run the test, expect failure:**

```bash
cd packages/ui/frontend && npx vitest run src/components/lobby/NewCampaignWizard.test.tsx
```

Expected: FAIL — module does not exist.

- [ ] **Step 3: Create `packages/ui/frontend/src/components/lobby/NewCampaignWizard.tsx`:**

```tsx
"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { BookOpen, ChevronLeft, Globe2, Loader2, Sparkles, X } from "lucide-react";
import { chatApi, storiesApi } from "@/lib/api";
import { useNotify } from "@/components/NotificationProvider";
import { errorMessage } from "@/lib/errors";
import type { StorySummary, Universe } from "@/lib/types";
import { cn } from "@/lib/utils";

type Step = "universe" | "story" | "details";

const TONES = ["heroic", "gritty", "whimsical", "horror", "mystery"] as const;

/** Guided new-campaign flow: universe → story → title/tone → play. */
export function NewCampaignWizard({
  universes,
  onClose,
}: {
  universes: Universe[];
  onClose: () => void;
}) {
  const router = useRouter();
  const { notify } = useNotify();
  const [step, setStep] = useState<Step>("universe");
  const [universe, setUniverse] = useState<Universe | null>(null);
  const [story, setStory] = useState<StorySummary | null>(null); // null = brand-new story
  const [title, setTitle] = useState("");
  const [tone, setTone] = useState<string>("heroic");
  const [creating, setCreating] = useState(false);

  const storiesQ = useQuery({
    queryKey: ["stories", "wizard", universe?.id],
    queryFn: () => storiesApi.listStories({ universe_id: universe!.id, limit: 100 }),
    enabled: !!universe,
  });

  async function begin() {
    if (!universe || creating) return;
    setCreating(true);
    try {
      const session = await chatApi.createSession({
        title: title.trim() || `New ${universe.name} campaign`,
        mode: "autonomous_gm",
        universe_id: universe.id,
        universe_label: universe.name,
        story_id: story?.id ?? null,
        tone,
      });
      router.push(`/play?session=${session.id}`);
    } catch (e) {
      notify("error", `Couldn't create campaign: ${errorMessage(e)}`);
      setCreating(false);
    }
  }

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      role="dialog"
      aria-label="New campaign"
    >
      <motion.div
        initial={{ scale: 0.96, y: 8 }}
        animate={{ scale: 1, y: 0 }}
        className="glass w-full max-w-lg rounded-2xl border border-cyan-500/20 p-6"
      >
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-cyan-300">New campaign</h2>
          <button onClick={onClose} aria-label="Close" className="text-slate-600 hover:text-slate-300">
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Step indicator */}
        <div className="mb-5 flex gap-1.5">
          {(["universe", "story", "details"] as Step[]).map((s, i) => (
            <div
              key={s}
              className={cn(
                "h-1 flex-1 rounded-full",
                (["universe", "story", "details"] as Step[]).indexOf(step) >= i
                  ? "bg-cyan-500/60"
                  : "bg-white/10",
              )}
            />
          ))}
        </div>

        <AnimatePresence mode="wait">
          {step === "universe" && (
            <motion.div key="u" initial={{ opacity: 0, x: 12 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -12 }} className="space-y-2">
              <div className="text-xs text-slate-500">1 · Choose a world</div>
              {universes.map((u) => (
                <button
                  key={u.id}
                  onClick={() => {
                    setUniverse(u);
                    setStory(null);
                    setStep("story");
                  }}
                  className="glass flex w-full items-center gap-3 rounded-xl px-4 py-3 text-left transition-colors hover:border-cyan-500/30"
                >
                  <Globe2 className="h-4 w-4 flex-shrink-0 text-cyan-400" />
                  <span className="min-w-0">
                    <span className="block truncate text-sm font-medium text-slate-200">{u.name}</span>
                    <span className="block truncate text-[11px] text-slate-500">
                      {[u.genre, `${u.entity_count} entities`].filter(Boolean).join(" · ")}
                    </span>
                  </span>
                </button>
              ))}
            </motion.div>
          )}

          {step === "story" && universe && (
            <motion.div key="s" initial={{ opacity: 0, x: 12 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -12 }} className="space-y-2">
              <div className="text-xs text-slate-500">2 · Continue a story or start fresh</div>
              <button
                onClick={() => {
                  setStory(null);
                  setStep("details");
                }}
                className="glass flex w-full items-center gap-3 rounded-xl border-cyan-500/25 px-4 py-3 text-left hover:border-cyan-500/40"
              >
                <Sparkles className="h-4 w-4 flex-shrink-0 text-cyan-400" />
                <span className="text-sm font-medium text-slate-200">New story</span>
              </button>
              {storiesQ.isLoading && <div className="text-xs text-slate-600">Loading stories…</div>}
              {(storiesQ.data?.stories ?? []).map((s) => (
                <button
                  key={s.id}
                  onClick={() => {
                    setStory(s);
                    setStep("details");
                  }}
                  className="glass flex w-full items-center gap-3 rounded-xl px-4 py-3 text-left hover:border-purple-500/30"
                >
                  <BookOpen className="h-4 w-4 flex-shrink-0 text-purple-300" />
                  <span className="min-w-0">
                    <span className="block truncate text-sm font-medium text-slate-200">{s.title}</span>
                    <span className="block text-[11px] text-slate-500">
                      {s.status} · {s.scene_count} scenes
                    </span>
                  </span>
                </button>
              ))}
              <button onClick={() => setStep("universe")} className="btn-ghost flex items-center gap-1 px-2 py-1 text-xs">
                <ChevronLeft className="h-3 w-3" /> Back
              </button>
            </motion.div>
          )}

          {step === "details" && universe && (
            <motion.div key="d" initial={{ opacity: 0, x: 12 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -12 }} className="space-y-4">
              <div className="text-xs text-slate-500">
                3 · {universe.name}
                {story ? ` — ${story.title}` : " — new story"}
              </div>
              <div className="space-y-1.5">
                <label htmlFor="wizard-title" className="text-xs text-slate-500">
                  Campaign title
                </label>
                <input
                  id="wizard-title"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder={`New ${universe.name} campaign`}
                  className="input-cyber w-full"
                />
              </div>
              <div className="space-y-1.5">
                <label htmlFor="wizard-tone" className="text-xs text-slate-500">
                  Tone
                </label>
                <select
                  id="wizard-tone"
                  value={tone}
                  onChange={(e) => setTone(e.target.value)}
                  className="input-cyber w-full"
                >
                  {TONES.map((t) => (
                    <option key={t} value={t}>
                      {t}
                    </option>
                  ))}
                </select>
              </div>
              <div className="flex items-center justify-between">
                <button onClick={() => setStep("story")} className="btn-ghost flex items-center gap-1 px-2 py-1 text-xs">
                  <ChevronLeft className="h-3 w-3" /> Back
                </button>
                <button
                  onClick={begin}
                  disabled={creating}
                  className="btn-cyber flex items-center gap-2 px-4 py-2 text-sm"
                >
                  {creating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
                  Begin campaign
                </button>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </motion.div>
    </motion.div>
  );
}
```

- [ ] **Step 4: Wire the wizard into `packages/ui/frontend/src/app/page.tsx`** — full replacement of the Task-2 version (only the header button and the wizard render change):

```tsx
"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { AnimatePresence } from "framer-motion";
import { Plus } from "lucide-react";
import { chatApi, storiesApi, universesApi } from "@/lib/api";
import { ContinuePlayingRail } from "@/components/lobby/ContinuePlayingRail";
import { NewCampaignWizard } from "@/components/lobby/NewCampaignWizard";
import { UniverseCardGrid } from "@/components/lobby/UniverseCardGrid";
import type { StorySummary } from "@/lib/types";

export default function LobbyPage() {
  const [wizardOpen, setWizardOpen] = useState(false);
  const sessionsQ = useQuery({ queryKey: ["sessions"], queryFn: chatApi.listSessions });
  const universesQ = useQuery({ queryKey: ["universes"], queryFn: () => universesApi.listUniverses() });
  const storiesQ = useQuery({
    queryKey: ["stories", "lobby"],
    queryFn: () => storiesApi.listStories({ limit: 100 }),
  });

  const latestStoryByUniverse: Record<string, StorySummary | undefined> = {};
  for (const s of storiesQ.data?.stories ?? []) {
    const prev = latestStoryByUniverse[s.universe_id];
    if (!prev || (s.created_at ?? "") > (prev.created_at ?? "")) {
      latestStoryByUniverse[s.universe_id] = s;
    }
  }

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-8 p-8">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-100">Campaigns</h1>
          <p className="mt-1 text-sm text-slate-500">
            Jump back in, or start a new campaign in one of your worlds.
          </p>
        </div>
        <button
          type="button"
          onClick={() => setWizardOpen(true)}
          className="btn-cyber flex items-center gap-2 px-4 py-2 text-sm"
        >
          <Plus className="h-4 w-4" /> New campaign
        </button>
      </header>

      <ContinuePlayingRail sessions={sessionsQ.data ?? []} />

      <section aria-label="Playable universes" className="space-y-2">
        <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
          Playable universes
        </div>
        {universesQ.isLoading ? (
          <div className="text-sm text-slate-500">Loading universes…</div>
        ) : (
          <UniverseCardGrid
            universes={universesQ.data ?? []}
            latestStoryByUniverse={latestStoryByUniverse}
          />
        )}
      </section>

      <AnimatePresence>
        {wizardOpen && (
          <NewCampaignWizard
            universes={universesQ.data ?? []}
            onClose={() => setWizardOpen(false)}
          />
        )}
      </AnimatePresence>
    </div>
  );
}
```

- [ ] **Step 5: Run tests + typecheck, expect pass:**

```bash
cd packages/ui/frontend && npx vitest run src/components/lobby src/app/page.test.tsx && npx tsc --noEmit
```

Expected: wizard tests + lobby tests all pass; tsc clean.

- [ ] **Step 6: Commit**

```bash
git add packages/ui/frontend/src/components/lobby packages/ui/frontend/src/app/page.tsx
git commit -m "feat(ui): new-campaign step wizard on the lobby page"
```

---

## Task 4: Light RP screen at `/light-rp` — character card grid + SillyTavern import + chat reuse

**Files:**

- Create: `packages/ui/frontend/src/components/lightrp/CharacterCardGrid.tsx`
- Create: `packages/ui/frontend/src/app/light-rp/page.tsx`
- Modify: `packages/ui/frontend/src/lib/api.ts` (export the existing `apiUrl` helper — it is currently module-private at `api.ts:100` and the card grid needs it for avatar `<img>` sources)
- Test: `packages/ui/frontend/src/app/light-rp/page.test.tsx`

**Interfaces:**

- Consumes: `entitiesApi.listStandaloneCharacters()`, `entitiesApi.importCharacterCard(file: File)`, `entitiesApi.deleteStandaloneCharacter(id)`; the existing `CharacterChat` component (`@/components/characters/CharacterChat`, props `{ character: StandaloneCharacter; onBack: () => void }`); `apiUrl` from `@/lib/api` for avatar img src.
- Produces:
  - `CharacterCardGrid({ characters, onChat, onGeneratePortrait, onDelete }: { characters: StandaloneCharacter[]; onChat: (c: StandaloneCharacter) => void; onGeneratePortrait?: (c: StandaloneCharacter) => void; onDelete: (c: StandaloneCharacter) => void })` — card: avatar (`apiUrl("/image/avatar/{id}")` when `avatar_url` set, initials placeholder otherwise), name, first line of `description`, `memory_count` badge, Chat button; overflow actions Generate portrait (rendered only when `onGeneratePortrait` provided — wired in Task 8) and Delete.
  - Route `/light-rp`: grid + "Import card" button (hidden file input, accepts `.json,.png`) + inline `CharacterChat` when a character is selected.

Avatar serving note: `avatar_url` stores a MinIO object key after Task 7; `GET /api/image/avatar/{id}` (also Task 7) redirects to a fresh presigned URL, so `<img src={apiUrl(\`/image/avatar/${c.id}\`)}>` works for both generated keys and legacy values. Until Task 7 lands, cards without avatars show the initials placeholder (the common case today).

**Steps:**

- [ ] **Step 1: Write the failing test** — `packages/ui/frontend/src/app/light-rp/page.test.tsx`:

```tsx
// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import LightRpPage from "./page";
import * as api from "@/lib/api";
import type { StandaloneCharacter } from "@/lib/types";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

// Keep the real chat out of page tests — it opens conversations on mount.
vi.mock("@/components/characters/CharacterChat", () => ({
  CharacterChat: ({ character, onBack }: { character: StandaloneCharacter; onBack: () => void }) => (
    <div data-testid="character-chat">
      chat:{character.name}
      <button onClick={onBack}>back</button>
    </div>
  ),
}));

vi.mock("@/components/NotificationProvider", () => ({
  useNotify: () => ({ notify: vi.fn() }),
}));

const char: StandaloneCharacter = {
  id: "c-1",
  name: "Wisp",
  description: "A fox-spirit guide.\nLikes riddles.",
  avatar_url: null,
  personality: "playful",
  gm_notes: "",
  first_message: "Hello, traveller.",
  is_ooc_persona: false,
  entity_id: null,
  default_universe_id: null,
  versions: [],
  memory_count: 7,
  created_at: "2026-07-01T00:00:00Z",
  updated_at: "2026-07-30T00:00:00Z",
} as StandaloneCharacter;

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <LightRpPage />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.restoreAllMocks();
  vi.spyOn(api.entitiesApi, "listStandaloneCharacters").mockResolvedValue([char]);
});

describe("/light-rp", () => {
  it("renders character cards with one-line summary and memory badge", async () => {
    renderPage();
    expect(await screen.findByText("Wisp")).toBeInTheDocument();
    expect(screen.getByText("A fox-spirit guide.")).toBeInTheDocument();
    expect(screen.queryByText("Likes riddles.")).not.toBeInTheDocument();
    expect(screen.getByText("7")).toBeInTheDocument(); // memory_count badge
  });

  it("opens the chat on card Chat click and returns on back", async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole("button", { name: /^chat$/i }));
    expect(screen.getByTestId("character-chat")).toHaveTextContent("chat:Wisp");
    await user.click(screen.getByRole("button", { name: /back/i }));
    expect(await screen.findByText("Wisp")).toBeInTheDocument();
  });

  it("has an Import card button that accepts SillyTavern files", async () => {
    renderPage();
    const input = (await screen.findByLabelText(/import card/i)) as HTMLInputElement;
    expect(input).toHaveAttribute("type", "file");
    expect(input.accept).toContain(".json");
    expect(input.accept).toContain(".png");
  });
});
```

- [ ] **Step 2: Run the test, expect failure:**

```bash
cd packages/ui/frontend && npx vitest run src/app/light-rp/page.test.tsx
```

Expected: FAIL — route/component do not exist.

- [ ] **Step 3: Export `apiUrl` in `packages/ui/frontend/src/lib/api.ts`** — one-word change at line 100 (needed by the card grid for avatar URLs; same helper `exportCharacterCardUrl` already uses internally):

```ts
export function apiUrl(path: string): string {
  return `${BASE}/api${path}`;
}
```

- [ ] **Step 4: Create `packages/ui/frontend/src/components/lightrp/CharacterCardGrid.tsx`:**

```tsx
"use client";

import { Brain, MessageCircle, MoreVertical, Sparkles, Trash2 } from "lucide-react";
import { useState } from "react";
import { apiUrl } from "@/lib/api";
import type { StandaloneCharacter } from "@/lib/types";
import { cn } from "@/lib/utils";

function oneLine(text: string): string {
  return (text ?? "").split("\n").map((l) => l.trim()).find(Boolean) ?? "";
}

export function CharacterCardGrid({
  characters,
  onChat,
  onGeneratePortrait,
  onDelete,
}: {
  characters: StandaloneCharacter[];
  onChat: (c: StandaloneCharacter) => void;
  onGeneratePortrait?: (c: StandaloneCharacter) => void;
  onDelete: (c: StandaloneCharacter) => void;
}) {
  const [menuFor, setMenuFor] = useState<string | null>(null);

  if (characters.length === 0) {
    return (
      <div className="glass rounded-xl px-6 py-10 text-center text-sm text-slate-500">
        No characters yet — import a SillyTavern card to get started.
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
      {characters.map((c) => (
        <div key={c.id} className="glass relative flex flex-col gap-3 rounded-2xl p-4">
          <div className="flex items-start gap-3">
            {c.avatar_url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={apiUrl(`/image/avatar/${c.id}`)}
                alt={c.name}
                className="h-12 w-12 flex-shrink-0 rounded-full border border-white/10 object-cover"
              />
            ) : (
              <div className="flex h-12 w-12 flex-shrink-0 items-center justify-center rounded-full bg-purple-500/15 text-sm font-bold text-purple-300">
                {c.name.slice(0, 2).toUpperCase()}
              </div>
            )}
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm font-semibold text-slate-100">{c.name}</div>
              <div className="truncate text-[11px] text-slate-500">{oneLine(c.description) || "—"}</div>
            </div>
            <button
              onClick={() => setMenuFor(menuFor === c.id ? null : c.id)}
              aria-label={`Actions for ${c.name}`}
              className="text-slate-600 hover:text-slate-300"
            >
              <MoreVertical className="h-4 w-4" />
            </button>
          </div>

          {menuFor === c.id && (
            <div className="absolute right-3 top-12 z-10 w-44 rounded-lg border border-white/10 bg-slate-900/95 py-1 shadow-xl">
              {onGeneratePortrait && (
                <button
                  onClick={() => {
                    setMenuFor(null);
                    onGeneratePortrait(c);
                  }}
                  className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs text-slate-300 hover:bg-white/5"
                >
                  <Sparkles className="h-3 w-3 text-cyan-300" /> Generate portrait
                </button>
              )}
              <button
                onClick={() => {
                  setMenuFor(null);
                  onDelete(c);
                }}
                className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs text-red-300 hover:bg-white/5"
              >
                <Trash2 className="h-3 w-3" /> Delete
              </button>
            </div>
          )}

          <div className="mt-auto flex items-center justify-between">
            <span
              className={cn(
                "flex items-center gap-1 rounded-md border px-2 py-0.5 text-[10px]",
                "border-purple-500/25 bg-purple-500/10 text-purple-300",
              )}
              title="Stored memories"
            >
              <Brain className="h-3 w-3" /> {c.memory_count}
            </span>
            <button
              onClick={() => onChat(c)}
              className="btn-cyber flex items-center gap-1.5 px-3 py-1.5 text-xs"
            >
              <MessageCircle className="h-3 w-3" /> Chat
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 5: Create `packages/ui/frontend/src/app/light-rp/page.tsx`:**

```tsx
"use client";

import { useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Upload } from "lucide-react";
import { entitiesApi } from "@/lib/api";
import { CharacterChat } from "@/components/characters/CharacterChat";
import { CharacterCardGrid } from "@/components/lightrp/CharacterCardGrid";
import { useNotify } from "@/components/NotificationProvider";
import { errorMessage } from "@/lib/errors";
import type { StandaloneCharacter } from "@/lib/types";

export default function LightRpPage() {
  const qc = useQueryClient();
  const { notify } = useNotify();
  const fileRef = useRef<HTMLInputElement>(null);
  const [active, setActive] = useState<StandaloneCharacter | null>(null);
  const [importing, setImporting] = useState(false);

  const charactersQ = useQuery({
    queryKey: ["standalone-characters"],
    queryFn: () => entitiesApi.listStandaloneCharacters(),
  });

  async function importCard(file: File) {
    setImporting(true);
    try {
      await entitiesApi.importCharacterCard(file);
      await qc.invalidateQueries({ queryKey: ["standalone-characters"] });
      notify("success", `Imported ${file.name}`);
    } catch (e) {
      notify("error", `Import failed: ${errorMessage(e)}`);
    } finally {
      setImporting(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  async function deleteChar(c: StandaloneCharacter) {
    try {
      await entitiesApi.deleteStandaloneCharacter(c.id);
      await qc.invalidateQueries({ queryKey: ["standalone-characters"] });
    } catch (e) {
      notify("error", `Delete failed: ${errorMessage(e)}`);
    }
  }

  if (active) {
    return (
      <div className="h-full min-h-0 p-4">
        <CharacterChat character={active} onBack={() => setActive(null)} />
      </div>
    );
  }

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6 p-8">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-100">Light RP</h1>
          <p className="mt-1 text-sm text-slate-500">
            Story-free chats with your characters. No canon, no dice — just talk.
          </p>
        </div>
        <div>
          <input
            ref={fileRef}
            id="import-card"
            type="file"
            accept=".json,.png"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) void importCard(f);
            }}
          />
          <label htmlFor="import-card" className="btn-cyber flex cursor-pointer items-center gap-2 px-4 py-2 text-sm">
            <Upload className="h-4 w-4" /> {importing ? "Importing…" : "Import card"}
          </label>
        </div>
      </header>

      {charactersQ.isLoading ? (
        <div className="text-sm text-slate-500">Loading characters…</div>
      ) : (
        <CharacterCardGrid
          characters={charactersQ.data ?? []}
          onChat={setActive}
          onDelete={(c) => void deleteChar(c)}
        />
      )}
    </div>
  );
}
```

- [ ] **Step 6: Run tests + typecheck, expect pass:**

```bash
cd packages/ui/frontend && npx vitest run src/app/light-rp/page.test.tsx && npx tsc --noEmit
```

Expected: 3 tests pass, tsc clean.

- [ ] **Step 7: Commit**

```bash
git add packages/ui/frontend/src/components/lightrp packages/ui/frontend/src/app/light-rp packages/ui/frontend/src/lib/api.ts
git commit -m "feat(ui): light RP screen with character card grid and card import"
```

---

## Task 5: Workbench — GM "Ask the world" chat panel + modifiable panel layout

Routes stay where they are (`/forge/*`, `/gm`); the Workbench grouping already happened in the sidebar (Task 1). This task adds the new canon-Q&A panel to the GM Assistant and makes the GM tool panels user-modifiable (show/hide + reorder, persisted in `localStorage` — no backend change, per spec §4).

**Files:**

- Create: `packages/ui/frontend/src/components/gm/AskTheWorldPanel.tsx`
- Create: `packages/ui/frontend/src/lib/gm-panel-prefs.ts`
- Modify: `packages/ui/frontend/src/app/gm/page.tsx` (register the panel, wire prefs into the tools column)
- Test: `packages/ui/frontend/src/components/gm/AskTheWorldPanel.test.tsx`
- Test: `packages/ui/frontend/src/lib/gm-panel-prefs.test.ts`

**Interfaces:**

- Consumes: `searchApi.universeSearch(universeId: string, q: string, opts?): Promise<SemanticSearchResponse>` (`GET /api/search/universes/{id}/search` — the existing scoped canon query endpoint, `routers/search.py:200`); `SearchResultItem { id, collection, score, text, entity_type, ... }` from `@/lib/types`.
- Produces:
  - `AskTheWorldPanel({ universeId }: { universeId: string | null })` — chat-style panel: question input, answer cards (top-5 canon hits with score + collection badge).
  - `useGmPanelPrefs()` → `{ order: string[]; hidden: string[]; setOrder(next: string[]): void; toggleHidden(id: string): void; visibleOrdered<T extends string>(ids: T[]): T[] }`, persisted under localStorage keys `monitor.gm.panelOrder` / `monitor.gm.hiddenPanels`.

**Steps:**

- [ ] **Step 1: Write the failing tests** — `packages/ui/frontend/src/components/gm/AskTheWorldPanel.test.tsx`:

```tsx
// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AskTheWorldPanel } from "./AskTheWorldPanel";
import * as api from "@/lib/api";

beforeEach(() => {
  vi.restoreAllMocks();
  vi.spyOn(api.searchApi, "universeSearch").mockResolvedValue({
    query: "Who rules the drowned court?",
    collections_searched: ["entities"],
    total_results: 1,
    results: [
      {
        id: "e-1",
        collection: "entities",
        score: 0.91,
        payload: {},
        text: "The Eelmother rules the Drowned Court from her throne of chains.",
        entity_type: "character",
        universe_id: "u-1",
        story_id: null,
      },
    ],
  });
});

describe("AskTheWorldPanel", () => {
  it("asks a question against the selected universe and shows canon hits", async () => {
    const user = userEvent.setup();
    render(<AskTheWorldPanel universeId="u-1" />);

    await user.type(screen.getByPlaceholderText(/ask the world/i), "Who rules the drowned court?");
    await user.click(screen.getByRole("button", { name: /ask/i }));

    expect(api.searchApi.universeSearch).toHaveBeenCalledWith(
      "u-1",
      "Who rules the drowned court?",
      { limit: 5 },
    );
    expect(await screen.findByText(/Eelmother rules the Drowned Court/)).toBeInTheDocument();
    expect(screen.getByText("entities")).toBeInTheDocument();
  });

  it("prompts for a universe when none is selected", () => {
    render(<AskTheWorldPanel universeId={null} />);
    expect(screen.getByText(/select a universe/i)).toBeInTheDocument();
    expect(screen.queryByPlaceholderText(/ask the world/i)).not.toBeInTheDocument();
  });
});
```

And `packages/ui/frontend/src/lib/gm-panel-prefs.test.ts`:

```ts
// @vitest-environment happy-dom
import { describe, it, expect, beforeEach } from "vitest";
import { readPanelPrefs, writePanelPrefs, visibleOrderedPanels } from "./gm-panel-prefs";

beforeEach(() => {
  window.localStorage.clear();
});

describe("gm-panel-prefs", () => {
  it("defaults to the given order with nothing hidden", () => {
    const ids = ["ask-world", "hooks", "dice"];
    expect(visibleOrderedPanels(ids, readPanelPrefs())).toEqual(ids);
  });

  it("persists hidden panels and order to localStorage", () => {
    writePanelPrefs({ order: ["dice", "hooks", "ask-world"], hidden: ["hooks"] });
    const ids = ["ask-world", "hooks", "dice"];
    expect(visibleOrderedPanels(ids, readPanelPrefs())).toEqual(["dice", "ask-world"]);
  });

  it("ignores stored ids that no longer exist and appends new ones", () => {
    writePanelPrefs({ order: ["ghost", "dice"], hidden: [] });
    expect(visibleOrderedPanels(["ask-world", "dice"], readPanelPrefs())).toEqual([
      "dice",
      "ask-world",
    ]);
  });

  it("tolerates corrupt JSON in localStorage", () => {
    window.localStorage.setItem("monitor.gm.panelOrder", "{not json");
    expect(readPanelPrefs()).toEqual({ order: [], hidden: [] });
  });
});
```

- [ ] **Step 2: Run the tests, expect failure:**

```bash
cd packages/ui/frontend && npx vitest run src/components/gm/AskTheWorldPanel.test.tsx src/lib/gm-panel-prefs.test.ts
```

Expected: FAIL — modules do not exist.

- [ ] **Step 3: Create `packages/ui/frontend/src/lib/gm-panel-prefs.ts`:**

```ts
"use client";

import { useCallback, useState } from "react";

const ORDER_KEY = "monitor.gm.panelOrder";
const HIDDEN_KEY = "monitor.gm.hiddenPanels";

export interface GmPanelPrefs {
  order: string[];
  hidden: string[];
}

function readIds(key: string): string[] {
  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.filter((x): x is string => typeof x === "string") : [];
  } catch {
    return [];
  }
}

export function readPanelPrefs(): GmPanelPrefs {
  if (typeof window === "undefined") return { order: [], hidden: [] };
  return { order: readIds(ORDER_KEY), hidden: readIds(HIDDEN_KEY) };
}

export function writePanelPrefs(prefs: GmPanelPrefs): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(ORDER_KEY, JSON.stringify(prefs.order));
  window.localStorage.setItem(HIDDEN_KEY, JSON.stringify(prefs.hidden));
}

/**
 * Apply stored prefs to a panel id list: drop hidden ids, honor stored order,
 * append panels the stored order doesn't know about (new panels appear).
 */
export function visibleOrderedPanels<T extends string>(ids: T[], prefs: GmPanelPrefs): T[] {
  const available = new Set(ids);
  const ordered: T[] = [];
  for (const id of prefs.order) {
    if (available.has(id as T) && !ordered.includes(id as T)) ordered.push(id as T);
  }
  for (const id of ids) {
    if (!ordered.includes(id)) ordered.push(id);
  }
  return ordered.filter((id) => !prefs.hidden.includes(id));
}

/** React binding: keeps prefs in state and persists every change. */
export function useGmPanelPrefs() {
  const [prefs, setPrefs] = useState<GmPanelPrefs>(() => readPanelPrefs());

  const update = useCallback((next: GmPanelPrefs) => {
    setPrefs(next);
    writePanelPrefs(next);
  }, []);

  const setOrder = useCallback((order: string[]) => update({ ...readPanelPrefs(), order }), [update]);

  const toggleHidden = useCallback(
    (id: string) => {
      const cur = readPanelPrefs();
      const hidden = cur.hidden.includes(id)
        ? cur.hidden.filter((h) => h !== id)
        : [...cur.hidden, id];
      update({ ...cur, hidden });
    },
    [update],
  );

  const move = useCallback(
    (id: string, dir: -1 | 1, ids: string[]) => {
      const cur = readPanelPrefs();
      const order = visibleOrderedPanels(ids, cur);
      const i = order.indexOf(id);
      const j = i + dir;
      if (i < 0 || j < 0 || j >= order.length) return;
      [order[i], order[j]] = [order[j], order[i]];
      update({ ...cur, order });
    },
    [update],
  );

  return { prefs, setOrder, toggleHidden, move };
}
```

- [ ] **Step 4: Create `packages/ui/frontend/src/components/gm/AskTheWorldPanel.tsx`:**

```tsx
"use client";

import { useState } from "react";
import { Globe2, Loader2, Send } from "lucide-react";
import { searchApi } from "@/lib/api";
import type { SearchResultItem } from "@/lib/types";
import { errorMessage } from "@/lib/errors";
import { cn } from "@/lib/utils";

type QA = { question: string; results: SearchResultItem[]; error?: string };

/**
 * "Ask the world" — natural-language questions against the selected universe's
 * canon, backed by the existing scoped semantic-search endpoint.
 */
export function AskTheWorldPanel({ universeId }: { universeId: string | null }) {
  const [draft, setDraft] = useState("");
  const [asking, setAsking] = useState(false);
  const [history, setHistory] = useState<QA[]>([]);

  if (!universeId) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 p-6 text-center">
        <Globe2 className="h-8 w-8 text-slate-700" />
        <p className="text-xs text-slate-600">Select a universe to ask its canon questions</p>
      </div>
    );
  }

  async function ask() {
    const q = draft.trim();
    if (!q || asking || !universeId) return;
    setDraft("");
    setAsking(true);
    try {
      const res = await searchApi.universeSearch(universeId, q, { limit: 5 });
      setHistory((h) => [...h, { question: q, results: res.results }]);
    } catch (e) {
      setHistory((h) => [...h, { question: q, results: [], error: errorMessage(e) }]);
    } finally {
      setAsking(false);
    }
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex-1 space-y-4 overflow-y-auto p-3">
        {history.length === 0 && (
          <p className="p-2 text-center text-[11px] text-slate-600">
            Ask anything about this world — answers come from stored canon.
          </p>
        )}
        {history.map((qa, i) => (
          <div key={i} className="space-y-2">
            <div className="flex justify-end">
              <div className="max-w-[85%] rounded-2xl rounded-br-sm bg-emerald-500/15 px-3 py-1.5 text-xs text-slate-200">
                {qa.question}
              </div>
            </div>
            {qa.error ? (
              <div className="rounded-lg border border-red-500/20 bg-red-500/5 px-3 py-2 text-[11px] text-red-300">
                {qa.error}
              </div>
            ) : qa.results.length === 0 ? (
              <div className="px-2 text-[11px] text-slate-600">No canon found for that.</div>
            ) : (
              qa.results.map((r) => (
                <div key={r.id} className="glass rounded-xl px-3 py-2">
                  <div className="mb-1 flex items-center gap-2">
                    <span className="rounded border border-emerald-500/25 bg-emerald-500/10 px-1.5 py-0.5 text-[9px] text-emerald-300">
                      {r.collection}
                    </span>
                    {r.entity_type && (
                      <span className="text-[9px] text-slate-600">{r.entity_type}</span>
                    )}
                    <span className="ml-auto text-[9px] tabular-nums text-slate-600">
                      {r.score.toFixed(2)}
                    </span>
                  </div>
                  <p className="text-xs leading-relaxed text-slate-300">{r.text ?? "—"}</p>
                </div>
              ))
            )}
          </div>
        ))}
        {asking && (
          <div className="flex items-center gap-2 px-2 text-[11px] text-slate-600">
            <Loader2 className="h-3 w-3 animate-spin" /> Consulting canon…
          </div>
        )}
      </div>
      <div className="flex items-end gap-2 border-t border-white/5 p-3">
        <textarea
          className="input-cyber max-h-24 min-h-[38px] flex-1 resize-none text-xs"
          placeholder="Ask the world…"
          value={draft}
          rows={1}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void ask();
            }
          }}
        />
        <button
          onClick={() => void ask()}
          disabled={asking || !draft.trim()}
          className={cn("btn-cyber px-3 py-2", (asking || !draft.trim()) && "opacity-50")}
          title="Ask"
        >
          <Send className="h-3.5 w-3.5" />
          <span className="sr-only">Ask</span>
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Edit `packages/ui/frontend/src/app/gm/page.tsx`** — four precise edits:

Edit 5a — panel registry (replace the `GM_PANELS` / `GMPanel` / `TOOL_PANEL_IDS` block at lines 1089–1103):

```tsx
const GM_PANELS = [
  { id: "rules",          label: "Rules",          icon: BookOpen },
  { id: "recorder",       label: "Recorder",       icon: Mic },
  { id: "notebook",       label: "Scratchpad",     icon: NotebookPen },
  { id: "dice",           label: "Dice",            icon: Dices },
  { id: "ask-world",      label: "Ask",             icon: Globe2 },
  { id: "hooks",          label: "Hooks",          icon: Sparkles },
  { id: "threads",        label: "Threads",        icon: GitBranch },
  { id: "contradictions", label: "Contradictions",  icon: AlertTriangle },
  { id: "session-prep",   label: "Prep",           icon: ClipboardList },
  { id: "handouts",       label: "Handouts",       icon: Scroll },
] as const;

type GMPanel = (typeof GM_PANELS)[number]["id"];

const TOOL_PANEL_IDS: GMPanel[] = ["ask-world", "hooks", "threads", "contradictions", "session-prep", "handouts"];
```

Edit 5b — imports: add `Globe2` to the lucide-react import, plus:

```tsx
import { AskTheWorldPanel } from "@/components/gm/AskTheWorldPanel";
import { useGmPanelPrefs, visibleOrderedPanels } from "@/lib/gm-panel-prefs";
```

Edit 5c — inside `GMAssistantPageContent`, next to the other hooks (after `const [centerTab, setCenterTab] = ...`):

```tsx
  const { prefs, toggleHidden, move } = useGmPanelPrefs();
  const [customizeOpen, setCustomizeOpen] = useState(false);
  const visibleToolPanels = visibleOrderedPanels(TOOL_PANEL_IDS, prefs);
```

Edit 5d — GM Tools column (lines 1249–1278): replace the sub-tab strip and body with the prefs-aware version plus a customize popover, and render the new panel:

```tsx
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
            <div className="flex-1 overflow-hidden">
              {activePanel === "ask-world" && <AskTheWorldPanel universeId={universeId} />}
              {activePanel === "hooks" && <PlotHooksPanel universeId={universeId} />}
              {activePanel === "threads" && <ThreadsPanel universeId={universeId} />}
              {activePanel === "contradictions" && <ContradictionsPanel universeId={universeId} />}
              {activePanel === "session-prep" && <SessionPrepPanel universeId={universeId} />}
              {activePanel === "handouts" && <HandoutsPanel universeId={universeId} />}
              {/* Default to ask-the-world if a hidden/non-tool panel is active */}
              {!visibleToolPanels.includes(activePanel) && <AskTheWorldPanel universeId={universeId} />}
            </div>
          </div>
```

(`SlidersHorizontal`, `ChevronUp`, `ChevronDown` join the lucide import in edit 5b.) The mobile panel-strip (`GM_PANELS.map` at line 1177) intentionally keeps showing all panels — the prefs target the desktop tools column; mobile already collapses to one panel.

- [ ] **Step 6: Run tests + typecheck, expect pass:**

```bash
cd packages/ui/frontend && npx vitest run src/components/gm/AskTheWorldPanel.test.tsx src/lib/gm-panel-prefs.test.ts src/app/gm/page.test.tsx && npx tsc --noEmit
```

Expected: new tests pass; the existing `app/gm/page.test.tsx` suite stays green (panel ids are additive); tsc clean.

- [ ] **Step 7: Commit**

```bash
git add packages/ui/frontend/src/components/gm/AskTheWorldPanel.tsx packages/ui/frontend/src/lib/gm-panel-prefs.ts packages/ui/frontend/src/app/gm/page.tsx packages/ui/frontend/src/components/gm/AskTheWorldPanel.test.tsx packages/ui/frontend/src/lib/gm-panel-prefs.test.ts
git commit -m "feat(ui): ask-the-world canon chat panel and modifiable GM tool panels"
```

---

## Task 6: Configuration section at `/config` + `image` role in the LLM settings UI

The Configuration section reuses the existing settings page wholesale: the file moves, the `/settings` → `/config` redirect is already in place (Task 1), and the sidebar already points at `/config`. This task also teaches the LLM-management UI about the new `image` role so image providers are assignable exactly like chat roles (spec §5).

**Files:**

- Move: `packages/ui/frontend/src/app/settings/page.tsx` → `packages/ui/frontend/src/app/config/page.tsx`
- Move: `packages/ui/frontend/src/app/settings/page.test.tsx` → `packages/ui/frontend/src/app/config/page.test.tsx`
- Modify: `packages/ui/frontend/src/lib/types.ts` (`LLMConnection.role` union gains `"image"`)
- Test: `packages/ui/frontend/src/app/config/page.test.tsx` (moved + new image-role test appended)

**Interfaces:**

- Consumes: unchanged settings APIs (`llmApi.*`, `dbApi.*`, `promptsApi.*`, …).
- Produces: route `/config` serving the six existing tabs (llm / agents / testbed / databases / tone / performance); role selects and tier meta extended with `image` (value `"image"`, label "Image — image generation").

**Steps:**

- [ ] **Step 1: Move the files** (preserves git history; keep `error.tsx`/`loading.tsx` in `app/settings/` — the redirect fires before they render, and they stay harmless):

```bash
mkdir -p packages/ui/frontend/src/app/config
git mv packages/ui/frontend/src/app/settings/page.tsx packages/ui/frontend/src/app/config/page.tsx
git mv packages/ui/frontend/src/app/settings/page.test.tsx packages/ui/frontend/src/app/config/page.test.tsx
```

The moved test imports `./page`, so it keeps working unchanged.

- [ ] **Step 2: Extend the failing test** — append to `packages/ui/frontend/src/app/config/page.test.tsx`:

```tsx
describe("/config — image role", () => {
  it("offers the image role in the add-provider role select", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const user = userEvent.setup();
    render(
      <QueryClientProvider client={qc}>
        <SettingsPage />
      </QueryClientProvider>,
    );

    await user.click(await screen.findByRole("button", { name: /add provider/i }));
    const roleSelect = screen.getByRole("combobox", { name: /role tier/i });
    expect(roleSelect).toContainElement(screen.getByRole("option", { name: /image generation/i }));
  });
});
```

- [ ] **Step 3: Run the test, expect failure:**

```bash
cd packages/ui/frontend && npx vitest run src/app/config/page.test.tsx
```

Expected: FAIL — no `image` option in the role select.

- [ ] **Step 4: Edit `packages/ui/frontend/src/app/config/page.tsx`** — four small replacements:

4a — add-provider form state type (line ~120):

```tsx
    role: "standard" as "light" | "standard" | "heavy" | "embedding" | "image",
```

4b — add-provider role select (lines ~249–258):

```tsx
          <select
            value={form.role}
            onChange={(e) => setForm({ ...form, role: e.target.value as "light" | "standard" | "heavy" | "embedding" | "image" })}
            className="input-cyber"
            aria-label="Role tier"
          >
            <option value="light">Light — fast/cheap tasks</option>
            <option value="standard">Standard — balanced</option>
            <option value="heavy">Heavy — most capable</option>
            <option value="embedding">Embedding — vector embeddings</option>
            <option value="image">Image — image generation</option>
          </select>
```

4c — provider-card edit-role select (lines ~435–438): add the same option after the embedding option:

```tsx
              <option value="embedding">Embedding — vector embeddings</option>
              <option value="image">Image — image generation</option>
```

4d — `ROLE_COLORS` and `TIER_META` + tier list:

```tsx
const ROLE_COLORS: Record<string, string> = {
  light: "text-sky-300 bg-sky-500/10 border-sky-500/20",
  standard: "text-amber-300 bg-amber-500/10 border-amber-500/20",
  heavy: "text-rose-300 bg-rose-500/10 border-rose-500/20",
  embedding: "text-teal-300 bg-teal-500/10 border-teal-500/20",
  image: "text-fuchsia-300 bg-fuchsia-500/10 border-fuchsia-500/20",
};
```

```tsx
const TIER_META: Record<string, { label: string; desc: string; colors: string }> = {
  heavy:    { label: "Heavy",    desc: "Complex reasoning, narration, canon decisions",  colors: "text-rose-300 bg-rose-500/10 border-rose-500/25" },
  standard: { label: "Standard", desc: "Balanced tasks, NPC dialogue, world queries",    colors: "text-amber-300 bg-amber-500/10 border-amber-500/25" },
  light:    { label: "Light",    desc: "Fast/cheap tasks: intent parsing, context prep",  colors: "text-sky-300 bg-sky-500/10 border-sky-500/25" },
  image:    { label: "Image",    desc: "Portraits & scene illustrations",                 colors: "text-fuchsia-300 bg-fuchsia-500/10 border-fuchsia-500/25" },
};
```

and in `TierAssignment`, extend the mapped tier tuple:

```tsx
      {(["heavy", "standard", "light", "image"] as const).map((tier) => {
```

- [ ] **Step 5: Edit `packages/ui/frontend/src/lib/types.ts`** — widen the stored role union:

```tsx
export interface LLMConnection {
  id: string;
  name: string;
  provider: LLMProvider;
  model: string;
  api_key_masked: string | null;
  base_url: string | null;
  status: "connected" | "error" | "unconfigured";
  latency_ms: number | null;
  is_default: boolean;
  role: "light" | "standard" | "heavy" | "embedding" | "image";
}
```

- [ ] **Step 6: Run tests + typecheck, expect pass:**

```bash
cd packages/ui/frontend && npx vitest run src/app/config/page.test.tsx && npx tsc --noEmit
```

Expected: the full moved settings suite passes at its new path plus the new image-role test; tsc clean.

- [ ] **Step 7: Commit**

```bash
git add packages/ui/frontend/src/app/config packages/ui/frontend/src/app/settings packages/ui/frontend/src/lib/types.ts
git commit -m "feat(ui): move settings to /config and add image role to LLM management UI"
```

---

## Task 7: Image generation backend — `ModelRole.IMAGE`, provider adapters, `/api/image` router

**Files:**

- Modify: `packages/data-layer/src/monitor_data/schemas/llm_config.py` (add `IMAGE` to `ModelRole`)
- Create: `packages/data-layer/src/monitor_data/llm/image_providers.py`
- Create: `packages/ui/backend/src/monitor_ui/routers/image_gen.py`
- Modify: `packages/ui/backend/src/monitor_ui/main.py` (register the router)
- Modify: `packages/ui/backend/src/monitor_ui/routers/llm_mgmt.py` (suggest image models in `AVAILABLE_MODELS`)
- Test: `packages/data-layer/tests/test_image_providers.py`
- Test: `packages/ui/backend/tests/test_image_gen.py`

**Interfaces:**

- Consumes: `monitor_data.db.postgres.get_postgres_client()` → `providers_list()` (rows shaped as in `llm_mgmt` — `id/provider/model/api_key/base_url/role/status/is_default`); `monitor_data.db.minio.get_minio_client()` → `upload(key, data, content_type)` / `presigned_url(key, expires_in)`; `routers/character_storage.get_character(id)` / `update_character(id, {"avatar_url": key})`; `routers/chat_persistence.db_load_messages(session_id)` (rows: `{role, content, timestamp, ...}`); MongoDB `conversations` collection (`turns: [{speaker_role, entity_name, text, timestamp}]`).
- Produces:
  - `ModelRole.IMAGE = "image"` — no DB migration: `llm_providers.role` is unconstrained `TEXT` (see `postgres.py:297`), and `ModelRole.coerce` handles the new value automatically.
  - `image_providers.py`:
    - `class ImageProviderError(RuntimeError)`
    - `class ImageProviderAdapter(Protocol): async def generate_image(self, prompt: str, *, aspect_ratio: str = "1:1") -> bytes`
    - `class MiniMaxImageAdapter(api_key: str, base_url: str = "https://api.minimaxi.com", model: str = "image-01")`
    - `class GeminiImageAdapter(api_key: str, model: str = "gemini-2.5-flash-image", base_url: str = "https://generativelanguage.googleapis.com")`
    - `def adapter_for_provider_row(row: dict[str, Any]) -> ImageProviderAdapter`
    - `async def resolve_image_adapter(postgres: Any) -> ImageProviderAdapter | None` — picks the `role == "image"` provider row (default first, then `connected`), returns `None` when unconfigured.
  - `routers/image_gen.py` (mounted at `/api/image`):
    - `build_portrait_prompt(character: dict[str, Any]) -> str`
    - `build_scene_prompt(messages: list[dict[str, Any]], character: dict[str, Any] | None = None) -> str`
    - `POST /portrait {character_id}` → `PortraitResponse{avatar_url, key}` — uploads `portraits/{character_id}/{uuid}.png`, sets `avatar_url` to the **object key**, returns a presigned URL.
    - `POST /scene {conversation_id?, session_id?, last_n: int = 12}` → `SceneResponse{image_url, key}` — uploads `scenes/{source}/{uuid}.png`; does not mutate the character.
    - `GET /avatar/{character_id}` → redirect to a fresh presigned URL for the character's `avatar_url` key (frontend `<img>` src; handles legacy `http(s)://`/`data:` values by redirecting through).
    - Errors: no image-role provider → `400` with a message pointing at `/config`; provider failure → `502`; unknown character/conversation → `404`.

API shapes (from the approved spec):

- MiniMax: `POST {base_url}/v1/image_generation`, `Authorization: Bearer {api_key}`, body `{"model", "prompt", "aspect_ratio", "response_format"}`; response `data.image_urls` (temporary URLs — download immediately) or base64 payloads. The adapter accepts both shapes. Default base `https://api.minimaxi.com` (international `https://api.minimax.io`); a stored chat base URL ending in `/anthropic` is trimmed to the host root.
- Gemini nano-banana: `POST {base_url}/v1beta/models/{model}:generateContent`, header `x-goog-api-key`, body `{"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]}}`; image bytes base64 at `candidates[0].content.parts[*].inlineData.data`.

**Steps:**

- [ ] **Step 1: Add the role** — in `packages/data-layer/src/monitor_data/schemas/llm_config.py`, extend `ModelRole` (and its docstring):

```python
class ModelRole(StrEnum):
    """
    Task-complexity tier for a model instance.

    Agents pick the cheapest tier that satisfies the need:

    LIGHT    — fast/cheap: classification, summarisation, simple extraction,
               embedding re-ranking, health-checks.
    STANDARD — balanced: most agent tasks (context assembly, resolver,
               memory indexing, proposed-change evaluation).
    HEAVY    — most capable: narrative generation (Narrator), final canon
               evaluation (CanonKeeper), long-form story reasoning.
    EMBEDDING — vector embeddings.
    IMAGE    — image generation (portraits, scene illustrations); resolved
               by monitor_data.llm.image_providers, not by the chat registry.
    """

    LIGHT = "light"
    STANDARD = "standard"
    HEAVY = "heavy"
    EMBEDDING = "embedding"
    IMAGE = "image"
```

- [ ] **Step 2: Write the failing data-layer tests** — `packages/data-layer/tests/test_image_providers.py` (network fully mocked; follows the `_run` idiom from `test_provider_semaphore.py`):

```python
"""Image provider adapter tests — httpx fully mocked, no network."""

from __future__ import annotations

import asyncio
import base64

import pytest

from monitor_data.llm.image_providers import (
    GeminiImageAdapter,
    ImageProviderError,
    MiniMaxImageAdapter,
    adapter_for_provider_row,
)


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class _FakeResponse:
    def __init__(self, payload=None, content=b"", status_code=200):
        self._payload = payload
        self.content = content
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


class _FakeClient:
    """Records calls; serves queued post/get responses."""

    def __init__(self, posts=None, gets=None):
        self._posts = list(posts or [])
        self._gets = list(gets or [])
        self.post_calls: list[dict] = []
        self.get_calls: list[str] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, **kwargs):
        self.post_calls.append({"url": url, **kwargs})
        return self._posts.pop(0)

    async def get(self, url):
        self.get_calls.append(url)
        return self._gets.pop(0)


PNG_BYTES = b"\x89PNG-fake-bytes"
PNG_B64 = base64.b64encode(PNG_BYTES).decode()


def test_minimax_url_response_downloads_image(monkeypatch):
    client = _FakeClient(
        posts=[_FakeResponse({"data": {"image_urls": ["https://cdn.example.com/tmp/1.png"]}})],
        gets=[_FakeResponse(content=PNG_BYTES)],
    )
    monkeypatch.setattr("monitor_data.llm.image_providers.httpx.AsyncClient", lambda **kw: client)

    adapter = MiniMaxImageAdapter(api_key="sk-test", base_url="https://api.minimaxi.com")
    out = _run(adapter.generate_image("a fox spirit", aspect_ratio="1:1"))

    assert out == PNG_BYTES
    call = client.post_calls[0]
    assert call["url"] == "https://api.minimaxi.com/v1/image_generation"
    assert call["headers"]["Authorization"] == "Bearer sk-test"
    assert call["json"]["model"] == "image-01"
    assert call["json"]["prompt"] == "a fox spirit"
    assert call["json"]["aspect_ratio"] == "1:1"
    assert client.get_calls == ["https://cdn.example.com/tmp/1.png"]


def test_minimax_base64_response_shape(monkeypatch):
    client = _FakeClient(posts=[_FakeResponse({"data": {"image_base64": [PNG_B64]}})])
    monkeypatch.setattr("monitor_data.llm.image_providers.httpx.AsyncClient", lambda **kw: client)

    adapter = MiniMaxImageAdapter(api_key="sk-test")
    assert _run(adapter.generate_image("portrait")) == PNG_BYTES
    assert client.get_calls == []  # no follow-up download for base64 payloads


def test_minimax_anthropic_base_url_is_trimmed_to_host(monkeypatch):
    client = _FakeClient(posts=[_FakeResponse({"data": {"image_base64": [PNG_B64]}})])
    monkeypatch.setattr("monitor_data.llm.image_providers.httpx.AsyncClient", lambda **kw: client)

    adapter = MiniMaxImageAdapter(api_key="k", base_url="https://api.minimax.io/anthropic")
    _run(adapter.generate_image("p"))
    assert client.post_calls[0]["url"] == "https://api.minimax.io/v1/image_generation"


def test_minimax_empty_data_raises(monkeypatch):
    client = _FakeClient(posts=[_FakeResponse({"data": {}})])
    monkeypatch.setattr("monitor_data.llm.image_providers.httpx.AsyncClient", lambda **kw: client)

    with pytest.raises(ImageProviderError):
        _run(MiniMaxImageAdapter(api_key="k").generate_image("p"))


def test_gemini_extracts_inline_image(monkeypatch):
    payload = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {"text": "here is your image"},
                        {"inlineData": {"mimeType": "image/png", "data": PNG_B64}},
                    ]
                }
            }
        ]
    }
    client = _FakeClient(posts=[_FakeResponse(payload)])
    monkeypatch.setattr("monitor_data.llm.image_providers.httpx.AsyncClient", lambda **kw: client)

    adapter = GeminiImageAdapter(api_key="gk-test")
    out = _run(adapter.generate_image("a drowned court", aspect_ratio="16:9"))

    assert out == PNG_BYTES
    call = client.post_calls[0]
    assert call["url"] == (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "gemini-2.5-flash-image:generateContent"
    )
    assert call["headers"]["x-goog-api-key"] == "gk-test"
    assert call["json"]["generationConfig"]["responseModalities"] == ["TEXT", "IMAGE"]


def test_gemini_no_image_part_raises(monkeypatch):
    payload = {"candidates": [{"content": {"parts": [{"text": "no image"}]}}]}
    client = _FakeClient(posts=[_FakeResponse(payload)])
    monkeypatch.setattr("monitor_data.llm.image_providers.httpx.AsyncClient", lambda **kw: client)

    with pytest.raises(ImageProviderError):
        _run(GeminiImageAdapter(api_key="gk").generate_image("p"))


def test_factory_picks_adapter_by_provider_type():
    mm = adapter_for_provider_row(
        {"provider": "minimax", "api_key": "k", "base_url": None, "model": "image-01"}
    )
    assert isinstance(mm, MiniMaxImageAdapter)
    g = adapter_for_provider_row(
        {
            "provider": "google_ai_studio",
            "api_key": "k",
            "base_url": None,
            "model": "gemini-2.5-flash-image",
        }
    )
    assert isinstance(g, GeminiImageAdapter)
    with pytest.raises(ImageProviderError):
        adapter_for_provider_row({"provider": "anthropic", "api_key": "k"})


def test_factory_requires_api_key(monkeypatch):
    monkeypatch.delenv("MINIMAX_TOKEN", raising=False)
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
    with pytest.raises(ImageProviderError):
        adapter_for_provider_row({"provider": "minimax", "api_key": "", "base_url": None})


@pytest.mark.asyncio
async def test_resolve_image_adapter_prefers_default_image_row():
    class _PG:
        async def providers_list(self):
            return [
                {"id": "chat", "provider": "openai", "role": "standard", "api_key": "x"},
                {"id": "img-b", "provider": "google_ai_studio", "role": "image", "api_key": "g",
                 "status": "connected", "is_default": False, "model": "gemini-2.5-flash-image"},
                {"id": "img-a", "provider": "minimax", "role": "image", "api_key": "m",
                 "status": "connected", "is_default": True, "model": "image-01", "base_url": None},
            ]

    from monitor_data.llm.image_providers import resolve_image_adapter

    adapter = await resolve_image_adapter(_PG())
    assert isinstance(adapter, MiniMaxImageAdapter)  # default image row wins


@pytest.mark.asyncio
async def test_resolve_image_adapter_none_when_unconfigured():
    class _PG:
        async def providers_list(self):
            return [{"id": "chat", "provider": "openai", "role": "standard", "api_key": "x"}]

    from monitor_data.llm.image_providers import resolve_image_adapter

    assert await resolve_image_adapter(_PG()) is None
```

- [ ] **Step 3: Run, expect failure:**

```bash
uv run pytest packages/data-layer/tests/test_image_providers.py -q
```

Expected: FAIL — module does not exist. (If `pytest-asyncio` is not configured for `@pytest.mark.asyncio`, check `pyproject.toml`; the repo's e2e suite uses asyncio markers. Fallback: wrap those two coroutine tests in `_run(...)` like the others.)

- [ ] **Step 4: Create `packages/data-layer/src/monitor_data/llm/image_providers.py`:**

```python
"""
Image generation provider adapters for MONITOR Data Layer.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries only (httpx, base64) + monitor_data.schemas
CALLED BY: UI backend image_gen router (Layer 2/3 boundary)

One interface — ``generate_image(prompt, *, aspect_ratio) -> bytes`` — with
implementations for MiniMax (``image-01``) and Google Gemini's image-capable
"nano-banana" models (``gemini-2.5-flash-image``). Provider selection reuses
the LLM registry tables: any ``llm_providers`` row with ``role='image'`` is a
candidate; ``resolve_image_adapter`` picks the default/connected one.
"""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

import httpx

from monitor_data.schemas.llm_config import LLMProviderType, ModelRole

_MINIMAX_DEFAULT_BASE = "https://api.minimaxi.com"
_GEMINI_DEFAULT_BASE = "https://generativelanguage.googleapis.com"
_GEMINI_DEFAULT_MODEL = "gemini-2.5-flash-image"
_TIMEOUT = 90.0  # image generation is slow; chat timeouts don't apply


class ImageProviderError(RuntimeError):
    """Raised for provider misconfiguration or unusable provider responses."""


@runtime_checkable
class ImageProviderAdapter(Protocol):
    """One method: prompt (+ aspect ratio) in, image bytes out."""

    async def generate_image(self, prompt: str, *, aspect_ratio: str = "1:1") -> bytes: ...


def _minimax_base(base_url: str | None) -> str:
    """Normalise a MiniMax base URL for the image endpoint.

    Chat providers store the Anthropic-compatible base (``.../anthropic``);
    image generation lives at the host root (``/v1/image_generation``).
    """
    base = (base_url or "").strip().rstrip("/") or _MINIMAX_DEFAULT_BASE
    if base.endswith("/anthropic"):
        base = base[: -len("/anthropic")]
    return base


@dataclass
class MiniMaxImageAdapter:
    """MiniMax ``POST /v1/image_generation`` (model ``image-01``)."""

    api_key: str
    base_url: str = _MINIMAX_DEFAULT_BASE
    model: str = "image-01"

    async def generate_image(self, prompt: str, *, aspect_ratio: str = "1:1") -> bytes:
        base = _minimax_base(self.base_url)
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                f"{base}/v1/image_generation",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "aspect_ratio": aspect_ratio,
                    "response_format": "url",
                },
            )
            resp.raise_for_status()
            data = (resp.json() or {}).get("data") or {}

            # Base64 payloads arrive inline regardless of requested format.
            b64_list = data.get("image_base64") or []
            if b64_list:
                return base64.b64decode(b64_list[0])

            # URL payloads are temporary — download immediately.
            urls = data.get("image_urls") or []
            if urls:
                dl = await client.get(urls[0])
                dl.raise_for_status()
                return bytes(dl.content)

        raise ImageProviderError("MiniMax image response contained no image data")


@dataclass
class GeminiImageAdapter:
    """Gemini ``:generateContent`` with IMAGE response modality (nano-banana)."""

    api_key: str
    model: str = _GEMINI_DEFAULT_MODEL
    base_url: str = _GEMINI_DEFAULT_BASE

    async def generate_image(self, prompt: str, *, aspect_ratio: str = "1:1") -> bytes:
        # aspect_ratio is accepted for interface parity; Gemini infers framing
        # from the prompt text, so the router bakes it into the prompt.
        url = f"{self.base_url.rstrip('/')}/v1beta/models/{self.model}:generateContent"
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                url,
                headers={"x-goog-api-key": self.api_key},
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
                },
            )
            resp.raise_for_status()
            payload = resp.json() or {}

        for candidate in payload.get("candidates") or []:
            for part in (candidate.get("content") or {}).get("parts") or []:
                inline = part.get("inlineData") or part.get("inline_data") or {}
                if inline.get("data"):
                    return base64.b64decode(inline["data"])
        raise ImageProviderError("Gemini response contained no inline image part")


def _env_key_for(provider: LLMProviderType) -> str:
    """Fallback credential lookup, mirroring llm_mgmt's env seeding."""
    if provider is LLMProviderType.MINIMAX:
        return os.getenv("MINIMAX_TOKEN", "").strip() or os.getenv("MINIMAX_API_KEY", "").strip()
    if provider is LLMProviderType.GOOGLE_AI_STUDIO:
        return os.getenv("GOOGLE_API_KEY", "").strip()
    return ""


def adapter_for_provider_row(row: dict[str, Any]) -> ImageProviderAdapter:
    """Build the image adapter for one ``llm_providers`` row.

    Raises ``ImageProviderError`` when the provider type has no image support
    or no credential is available (row key first, then env fallback).
    """
    provider = LLMProviderType(str(row.get("provider") or ""))
    api_key = (row.get("api_key") or "").strip() or _env_key_for(provider)
    if not api_key:
        raise ImageProviderError(f"No API key configured for image provider '{row.get('id')}'")

    if provider is LLMProviderType.MINIMAX:
        return MiniMaxImageAdapter(
            api_key=api_key,
            base_url=_minimax_base(row.get("base_url")),
            model=(row.get("model") or "").strip() or "image-01",
        )
    if provider is LLMProviderType.GOOGLE_AI_STUDIO:
        return GeminiImageAdapter(
            api_key=api_key,
            model=(row.get("model") or "").strip() or _GEMINI_DEFAULT_MODEL,
        )
    raise ImageProviderError(f"Provider '{provider.value}' does not support image generation")


async def resolve_image_adapter(postgres: Any) -> ImageProviderAdapter | None:
    """Pick the configured image provider from the LLM registry tables.

    Preference: is_default image row → connected image row → any image row.
    Returns None when no row carries ``role='image'`` (router maps to 400).
    """
    rows = await postgres.providers_list()
    image_rows = [r for r in rows if (r.get("role") or "").strip().lower() == ModelRole.IMAGE.value]
    if not image_rows:
        return None
    image_rows.sort(
        key=lambda r: (
            not r.get("is_default"),
            (r.get("status") or "").lower() != "connected",
        )
    )
    return adapter_for_provider_row(image_rows[0])
```

- [ ] **Step 5: Run the data-layer tests, expect pass:**

```bash
uv run pytest packages/data-layer/tests/test_image_providers.py -q
```

- [ ] **Step 6: Write the failing router tests** — `packages/ui/backend/tests/test_image_gen.py` (idiom from `test_llm_mgmt.py`: bare FastAPI app + TestClient + patch/AsyncMock):

```python
"""Tests for the image generation router (provider + storage fully mocked)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import monitor_ui.routers.image_gen as image_gen
from monitor_ui.routers.image_gen import build_portrait_prompt, build_scene_prompt, router

app = FastAPI()
app.include_router(router, prefix="/api/image")
client = TestClient(app)

CHAR = {
    "id": "c-1",
    "name": "Wisp",
    "description": "A fox-spirit guide with ember eyes.",
    "personality": "playful, evasive",
    "gm_notes": "",
    "avatar_url": None,
}

PNG = b"\x89PNG-fake"


class _FakeAdapter:
    def __init__(self):
        self.calls: list[dict] = []

    async def generate_image(self, prompt: str, *, aspect_ratio: str = "1:1") -> bytes:
        self.calls.append({"prompt": prompt, "aspect_ratio": aspect_ratio})
        return PNG


@pytest.fixture
def fake_adapter():
    return _FakeAdapter()


@pytest.fixture
def mock_storage():
    minio = AsyncMock()
    minio.presigned_url.return_value = "https://minio.example.com/presigned/abc"
    with (
        patch.object(image_gen, "get_minio_client", return_value=minio),
        patch.object(image_gen, "get_postgres_client", return_value=AsyncMock()),
    ):
        yield minio


def test_build_portrait_prompt_uses_character_fields():
    prompt = build_portrait_prompt(CHAR)
    assert "Wisp" in prompt
    assert "fox-spirit guide" in prompt
    assert "playful, evasive" in prompt


def test_build_scene_prompt_includes_excerpt_and_speakers():
    messages = [
        {"speaker_role": "player", "entity_name": None, "text": "I light the lantern."},
        {"speaker_role": "npc", "entity_name": "Wisp", "text": "The dark notices."},
    ]
    prompt = build_scene_prompt(messages, CHAR)
    assert "I light the lantern." in prompt
    assert "Wisp" in prompt
    assert "The dark notices." in prompt


def test_portrait_happy_path(fake_adapter, mock_storage):
    with (
        patch.object(image_gen, "get_character", return_value=dict(CHAR)),
        patch.object(image_gen, "update_character", return_value=dict(CHAR)) as upd,
        patch.object(image_gen, "resolve_image_adapter", new=AsyncMock(return_value=fake_adapter)),
    ):
        res = client.post("/api/image/portrait", json={"character_id": "c-1"})

    assert res.status_code == 200
    body = res.json()
    assert body["avatar_url"] == "https://minio.example.com/presigned/abc"
    assert body["key"].startswith("portraits/c-1/")
    # avatar_url is set to the *object key*, not the expiring presigned URL
    assert upd.call_args[0][1]["avatar_url"] == body["key"]
    mock_storage.upload.assert_awaited_once()
    assert mock_storage.upload.call_args[0][1] == PNG


def test_portrait_400_when_no_image_provider(mock_storage):
    with (
        patch.object(image_gen, "get_character", return_value=dict(CHAR)),
        patch.object(image_gen, "resolve_image_adapter", new=AsyncMock(return_value=None)),
    ):
        res = client.post("/api/image/portrait", json={"character_id": "c-1"})
    assert res.status_code == 400
    assert "/config" in res.json()["detail"]


def test_portrait_404_for_unknown_character(mock_storage):
    with patch.object(image_gen, "get_character", return_value=None):
        res = client.post("/api/image/portrait", json={"character_id": "nope"})
    assert res.status_code == 404


def test_portrait_502_on_provider_failure(fake_adapter, mock_storage):
    async def _boom(prompt, *, aspect_ratio="1:1"):
        raise RuntimeError("rate limited")

    failing = AsyncMock()
    failing.generate_image.side_effect = _boom
    with (
        patch.object(image_gen, "get_character", return_value=dict(CHAR)),
        patch.object(image_gen, "resolve_image_adapter", new=AsyncMock(return_value=failing)),
    ):
        res = client.post("/api/image/portrait", json={"character_id": "c-1"})
    assert res.status_code == 502


def test_scene_from_conversation_turns(fake_adapter, mock_storage):
    mongo = MagicMock()  # pymongo calls are synchronous
    mongo.get_collection.return_value.find_one.return_value = {
        "conversation_id": "conv-1",
        "turns": [
            {"speaker_role": "player", "entity_name": None, "text": "I light the lantern."},
            {"speaker_role": "npc", "entity_name": "Wisp", "text": "The dark notices."},
        ],
    }
    with (
        patch.object(image_gen, "get_mongodb_client", return_value=mongo),
        patch.object(image_gen, "resolve_image_adapter", new=AsyncMock(return_value=fake_adapter)),
    ):
        res = client.post("/api/image/scene", json={"conversation_id": "conv-1", "last_n": 12})

    assert res.status_code == 200
    assert res.json()["key"].startswith("scenes/conversation-conv-1/")
    assert fake_adapter.calls[0]["aspect_ratio"] == "16:9"
    assert "I light the lantern." in fake_adapter.calls[0]["prompt"]


def test_scene_from_play_session(fake_adapter, mock_storage):
    rows = [
        {"role": "player", "content": "I open the gate.", "timestamp": "t1"},
        {"role": "gm", "content": "The courtyard is flooded.", "timestamp": "t2"},
    ]
    with (
        patch.object(image_gen, "db_load_messages", return_value=rows),
        patch.object(image_gen, "resolve_image_adapter", new=AsyncMock(return_value=fake_adapter)),
    ):
        res = client.post("/api/image/scene", json={"session_id": "s-1", "last_n": 12})

    assert res.status_code == 200
    assert res.json()["key"].startswith("scenes/session-s-1/")
    assert "courtyard is flooded" in fake_adapter.calls[0]["prompt"]


def test_scene_400_without_any_source(mock_storage):
    res = client.post("/api/image/scene", json={"last_n": 12})
    assert res.status_code == 400


def test_scene_404_for_unknown_conversation(fake_adapter, mock_storage):
    mongo = MagicMock()  # pymongo calls are synchronous
    mongo.get_collection.return_value.find_one.return_value = None
    with (
        patch.object(image_gen, "get_mongodb_client", return_value=mongo),
        patch.object(image_gen, "resolve_image_adapter", new=AsyncMock(return_value=fake_adapter)),
    ):
        res = client.post("/api/image/scene", json={"conversation_id": "ghost", "last_n": 12})
    assert res.status_code == 404


def test_avatar_redirects_to_presigned_url(mock_storage):
    with patch.object(
        image_gen, "get_character", return_value={**CHAR, "avatar_url": "portraits/c-1/x.png"}
    ):
        res = client.get("/api/image/avatar/c-1", follow_redirects=False)
    assert res.status_code in (302, 307)
    assert res.headers["location"] == "https://minio.example.com/presigned/abc"


def test_avatar_404_without_avatar(mock_storage):
    with patch.object(image_gen, "get_character", return_value=dict(CHAR)):
        res = client.get("/api/image/avatar/c-1")
    assert res.status_code == 404
```

- [ ] **Step 7: Run, expect failure:**

```bash
uv run pytest packages/ui/backend/tests/test_image_gen.py -q
```

Expected: FAIL — module does not exist.

- [ ] **Step 8: Create `packages/ui/backend/src/monitor_ui/routers/image_gen.py`:**

```python
"""
Image generation router — portraits and scene illustrations.

Principle (spec §6): no standalone image tool; generate where content lives.
Provider config lives in the LLM registry (a ``llm_providers`` row with
``role='image'``); generated images are stored in MinIO and served through
short-lived presigned URLs. Character ``avatar_url`` stores the MinIO object
*key* — ``GET /avatar/{id}` issues a fresh presigned redirect for ``<img>``
tags, so expiring URLs never get persisted.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse
from monitor_data.db.minio import get_minio_client
from monitor_data.db.mongodb import get_mongodb_client
from monitor_data.db.postgres import get_postgres_client
from monitor_data.llm.image_providers import resolve_image_adapter
from pydantic import BaseModel, Field

from .character_storage import get_character, update_character
from .chat_persistence import db_load_messages

router = APIRouter()

_NO_PROVIDER_DETAIL = (
    "No image provider configured. Add a MiniMax (image-01) or Google "
    "(gemini-2.5-flash-image) provider and assign it the 'image' role under "
    "/config → LLM Providers."
)

# ---------------------------------------------------------------------------
# Request/response models
# ---------------------------------------------------------------------------


class PortraitRequest(BaseModel):
    character_id: str


class PortraitResponse(BaseModel):
    avatar_url: str
    key: str


class SceneRequest(BaseModel):
    conversation_id: str | None = None
    session_id: str | None = None
    last_n: int = Field(default=12, ge=1, le=50)


class SceneResponse(BaseModel):
    image_url: str
    key: str


# ---------------------------------------------------------------------------
# Prompt builders (pure — unit-testable without any I/O)
# ---------------------------------------------------------------------------


def build_portrait_prompt(character: dict[str, Any]) -> str:
    """Portrait prompt from card fields: name + description + personality."""
    parts = [f"Character portrait of {character.get('name') or 'a fictional character'}."]
    description = (character.get("description") or "").strip()
    if description:
        parts.append(description)
    personality = (character.get("personality") or "").strip()
    if personality:
        parts.append(f"Personality: {personality}.")
    parts.append(
        "Head-and-shoulders fantasy character portrait, expressive, "
        "painterly, high detail, no text, no watermark."
    )
    return " ".join(parts)


def build_scene_prompt(
    messages: list[dict[str, Any]], character: dict[str, Any] | None = None
) -> str:
    """Scene-illustration prompt summarising the last N chat messages."""
    lines: list[str] = []
    for m in messages:
        text = (m.get("text") or m.get("content") or "").strip()
        if not text:
            continue
        speaker = m.get("entity_name") or m.get("speaker_role") or m.get("role") or "narrator"
        lines.append(f"{speaker}: {text}")
    excerpt = "\n".join(lines)[-3000:]
    featuring = f" featuring {character['name']}" if character and character.get("name") else ""
    return (
        f"Cinematic scene illustration{featuring}, 16:9 composition, based on "
        f"this roleplay excerpt:\n{excerpt}\n"
        "Atmospheric, painterly, dramatic lighting, no text, no watermark."
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _adapter():
    postgres = get_postgres_client()
    adapter = await resolve_image_adapter(postgres)
    if adapter is None:
        raise HTTPException(status_code=400, detail=_NO_PROVIDER_DETAIL)
    return adapter


async def _generate(adapter: Any, prompt: str, aspect_ratio: str) -> bytes:
    try:
        return await adapter.generate_image(prompt, aspect_ratio=aspect_ratio)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Image provider failed (retryable): {exc}")


def _load_scene_messages(body: SceneRequest) -> tuple[list[dict[str, Any]], str]:
    """Return (messages, storage-prefix) for either a play session or a
    light-RP conversation. Raises 404 when the source doesn't exist or is empty."""
    if body.session_id:
        rows = db_load_messages(body.session_id)
        if not rows:
            raise HTTPException(status_code=404, detail="Session has no messages")
        messages = [
            {"speaker_role": r.get("role"), "entity_name": None, "text": r.get("content") or ""}
            for r in rows[-body.last_n :]
        ]
        return messages, f"session-{body.session_id}"

    doc = get_mongodb_client().get_collection("conversations").find_one(
        {"conversation_id": body.conversation_id}
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Conversation not found")
    turns = list(doc.get("turns") or [])[-body.last_n :]
    if not turns:
        raise HTTPException(status_code=404, detail="Conversation has no turns")
    return turns, f"conversation-{body.conversation_id}"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/portrait", response_model=PortraitResponse)
async def generate_portrait(body: PortraitRequest) -> PortraitResponse:
    """Generate a portrait for a standalone character and set its avatar."""
    char = get_character(body.character_id)
    if not char:
        raise HTTPException(status_code=404, detail="Character not found")

    adapter = await _adapter()
    png = await _generate(adapter, build_portrait_prompt(char), "1:1")

    key = f"portraits/{body.character_id}/{uuid4().hex}.png"
    minio = get_minio_client()
    await minio.upload(key, png, content_type="image/png")
    update_character(body.character_id, {"avatar_url": key})
    url = await minio.presigned_url(key, expires_in=3600)
    return PortraitResponse(avatar_url=url, key=key)


@router.post("/scene", response_model=SceneResponse)
async def generate_scene_image(body: SceneRequest) -> SceneResponse:
    """Generate a scene illustration from the last N messages of a chat."""
    if not body.conversation_id and not body.session_id:
        raise HTTPException(
            status_code=400,
            detail="Provide conversation_id (light RP) or session_id (play chat).",
        )

    messages, source = _load_scene_messages(body)
    adapter = await _adapter()
    png = await _generate(adapter, build_scene_prompt(messages), "16:9")

    key = f"scenes/{source}/{uuid4().hex}.png"
    minio = get_minio_client()
    await minio.upload(key, png, content_type="image/png")
    url = await minio.presigned_url(key, expires_in=3600)
    return SceneResponse(image_url=url, key=key)


@router.get("/avatar/{character_id}")
async def character_avatar(character_id: str) -> RedirectResponse:
    """Redirect to a fresh presigned URL for the character's avatar image."""
    char = get_character(character_id)
    if not char:
        raise HTTPException(status_code=404, detail="Character not found")
    avatar = char.get("avatar_url") or ""
    if not avatar:
        raise HTTPException(status_code=404, detail="Character has no avatar")
    if avatar.startswith(("http://", "https://", "data:")):
        return RedirectResponse(avatar)
    url = await get_minio_client().presigned_url(avatar, expires_in=3600)
    return RedirectResponse(url)
```

- [ ] **Step 9: Register the router in `packages/ui/backend/src/monitor_ui/main.py`** — add `image_gen` to the `from monitor_ui.routers import (...)` list (alphabetical, after `graph`) and mount it after the `forge` router:

```python
    app.include_router(image_gen.router, prefix="/api/image", tags=["image"])
```

- [ ] **Step 10: Suggest image models in `packages/ui/backend/src/monitor_ui/routers/llm_mgmt.py`** — extend `AVAILABLE_MODELS` so the add-provider form offers them:

```python
    "minimax": [
        "MiniMax-M2.7",
        "M2-her",
        "MiniMax-Text-01",
        "image-01",
        "abab6.5s-chat",
        "abab6.5g-chat",
        "abab5.5s-chat",
    ],
```

```python
    "google_ai_studio": [
        "gemini-2.5-flash",
        "gemini-2.5-pro",
        "gemini-2.5-flash-image",
        "gemini-2.0-flash",
        "gemini-1.5-pro",
    ],
```

- [ ] **Step 11: Run backend tests + layer check, expect pass:**

```bash
uv run pytest packages/ui/backend/tests/test_image_gen.py -q
uv run pytest packages/data-layer -q
python scripts/check_layer_dependencies.py
uv run ruff check packages
```

Expected: all pass; layer check clean (`image_gen.py` imports data-layer only, like its sibling routers).

- [ ] **Step 12: Commit**

```bash
git add packages/data-layer/src/monitor_data/schemas/llm_config.py packages/data-layer/src/monitor_data/llm/image_providers.py packages/data-layer/tests/test_image_providers.py packages/ui/backend/src/monitor_ui/routers/image_gen.py packages/ui/backend/src/monitor_ui/main.py packages/ui/backend/src/monitor_ui/routers/llm_mgmt.py packages/ui/backend/tests/test_image_gen.py
git commit -m "feat(image): image role, minimax/gemini adapters, /api/image portrait+scene endpoints"
```

---

## Task 8: Image generation frontend — portrait button on cards, scene button in chat, `imageApi`

**Files:**

- Modify: `packages/ui/frontend/src/lib/api.ts` (add `imageApi`)
- Modify: `packages/ui/frontend/src/app/light-rp/page.tsx` (wire `onGeneratePortrait`)
- Modify: `packages/ui/frontend/src/components/characters/CharacterChat.tsx` (scene-image button + inline image rendering)
- Test: `packages/ui/frontend/src/components/characters/CharacterChat.test.tsx` (new)
- Test: `packages/ui/frontend/src/app/light-rp/page.test.tsx` (append portrait test)

**Interfaces:**

- Consumes: `POST /api/image/portrait {character_id}` → `{avatar_url, key}`; `POST /api/image/scene {conversation_id?, session_id?, last_n?}` → `{image_url, key}` (Task 7).
- Produces:
  - `imageApi.generatePortrait(characterId: string): Promise<{ avatar_url: string; key: string }>`
  - `imageApi.generateScene(data: { conversation_id?: string; session_id?: string; last_n?: number }): Promise<{ image_url: string; key: string }>`
  - `CharacterChat` gains a header "Generate scene image" action (aria-label `Generate scene image`) that appends an image message to the chat flow; `ChatMessage` gains `image_url?: string`.

**Steps:**

- [ ] **Step 1: Add `imageApi` to `packages/ui/frontend/src/lib/api.ts`** — append after the `entitiesApi` block:

```ts
// ─── Image generation (portraits & scene illustrations) ───────

export const imageApi = {
  generatePortrait: (characterId: string) =>
    req<{ avatar_url: string; key: string }>("/image/portrait", {
      method: "POST",
      body: JSON.stringify({ character_id: characterId }),
      timeout: 120_000, // image generation is slow — mirrors the chat timeouts
    }),
  generateScene: (data: { conversation_id?: string; session_id?: string; last_n?: number }) =>
    req<{ image_url: string; key: string }>("/image/scene", {
      method: "POST",
      body: JSON.stringify(data),
      timeout: 120_000,
    }),
};
```

- [ ] **Step 2: Write the failing tests** — `packages/ui/frontend/src/components/characters/CharacterChat.test.tsx`:

```tsx
// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CharacterChat } from "./CharacterChat";
import * as api from "@/lib/api";
import type { StandaloneCharacter } from "@/lib/types";

vi.mock("@/components/NotificationProvider", () => ({
  useNotify: () => ({ notify: vi.fn() }),
}));

const char = {
  id: "c-1",
  name: "Wisp",
  description: "A fox-spirit guide.",
  avatar_url: null,
  personality: "playful",
  gm_notes: "",
  first_message: "Well met, traveller.",
  is_ooc_persona: false,
  entity_id: "e-1",
  default_universe_id: null,
  versions: [],
  memory_count: 7,
  created_at: "2026-07-01T00:00:00Z",
  updated_at: "2026-07-30T00:00:00Z",
} as StandaloneCharacter;

beforeEach(() => {
  vi.restoreAllMocks();
  vi.spyOn(api.entitiesApi, "startCharacterConversation").mockResolvedValue({
    conversation_id: "conv-1",
    character_id: "c-1",
    version_id: "v-1",
    entity_id: "e-1",
    universe_id: "u-1",
    opening: "Well met, traveller.",
  });
  vi.spyOn(api.entitiesApi, "endCharacterConversation").mockResolvedValue({ ended: true, proposals: 0 });
  vi.spyOn(api.imageApi, "generateScene").mockResolvedValue({
    image_url: "https://minio.example.com/scene.png",
    key: "scenes/conversation-conv-1/x.png",
  });
});

describe("CharacterChat — scene image", () => {
  it("calls the scene endpoint for the active conversation and shows the image inline", async () => {
    const user = userEvent.setup();
    render(<CharacterChat character={char} onBack={() => {}} />);

    // Wait for the conversation to open
    expect(await screen.findByText("Well met, traveller.")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /generate scene image/i }));

    await waitFor(() =>
      expect(api.imageApi.generateScene).toHaveBeenCalledWith({
        conversation_id: "conv-1",
        last_n: 12,
      }),
    );
    const img = await screen.findByAltText("Scene illustration");
    expect(img).toHaveAttribute("src", "https://minio.example.com/scene.png");
  });

  it("disables the scene button until a conversation is open", () => {
    vi.spyOn(api.entitiesApi, "startCharacterConversation").mockReturnValue(new Promise(() => {}));
    render(<CharacterChat character={char} onBack={() => {}} />);
    expect(screen.getByRole("button", { name: /generate scene image/i })).toBeDisabled();
  });
});
```

And append to `packages/ui/frontend/src/app/light-rp/page.test.tsx` (inside the existing `describe`):

```tsx
  it("generates a portrait from the card overflow menu", async () => {
    vi.spyOn(api.imageApi, "generatePortrait").mockResolvedValue({
      avatar_url: "https://minio.example.com/p.png",
      key: "portraits/c-1/p.png",
    });
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole("button", { name: /actions for wisp/i }));
    await user.click(screen.getByRole("button", { name: /generate portrait/i }));
    expect(api.imageApi.generatePortrait).toHaveBeenCalledWith("c-1");
  });
```

- [ ] **Step 3: Run the tests, expect failure:**

```bash
cd packages/ui/frontend && npx vitest run src/components/characters/CharacterChat.test.tsx src/app/light-rp/page.test.tsx
```

Expected: FAIL — no scene button / portrait wiring yet.

- [ ] **Step 4: Update `packages/ui/frontend/src/components/characters/CharacterChat.tsx`** — full replacement (adds the scene-image action; everything else unchanged from the current component):

```tsx
"use client";

import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ArrowLeft, Send, Heart, ShieldAlert, Sparkles, ImagePlus, Loader2 } from "lucide-react";
import { entitiesApi, imageApi } from "@/lib/api";
import type { StandaloneCharacter } from "@/lib/types";
import { useNotify } from "@/components/NotificationProvider";
import { cn } from "@/lib/utils";
import { errorMessage } from "@/lib/errors";

type ChatMessage = {
  id: string;
  role: "user" | "char";
  text: string;
  emotional_state?: string | null;
  snapshot?: Record<string, unknown>;
  image_url?: string;
};

function num(snapshot: Record<string, unknown> | undefined, key: string): number {
  const v = snapshot?.[key];
  return typeof v === "number" ? v : 0;
}

/** Story-less conversatory with a single MONITOR-backed character. */
export function CharacterChat({
  character,
  onBack,
}: {
  character: StandaloneCharacter;
  onBack: () => void;
}) {
  const { notify } = useNotify();
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [starting, setStarting] = useState(true);
  const [sending, setSending] = useState(false);
  const [sceneBusy, setSceneBusy] = useState(false);
  // Character Versions: broaden memory recall to other universes of this
  // character when the user opts in (default off — strict universe scope).
  const [includeCrossIncarnation, setIncludeCrossIncarnation] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const convRef = useRef<string | null>(null);

  // Open a session on mount; end it on unmount (best-effort).
  useEffect(() => {
    let active = true;
    setStarting(true);
    entitiesApi
      .startCharacterConversation(character.id)
      .then((res) => {
        if (!active) return;
        convRef.current = res.conversation_id;
        setConversationId(res.conversation_id);
        setMessages([{ id: "opening", role: "char", text: res.opening }]);
      })
      .catch((e) => active && notify("error", `Couldn't start chat: ${errorMessage(e)}`))
      .finally(() => active && setStarting(false));
    return () => {
      active = false;
      const cid = convRef.current;
      if (cid) entitiesApi.endCharacterConversation(character.id, cid).catch(() => {});
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [character.id]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, sending]);

  const lastRead = [...messages].reverse().find((m) => m.role === "char" && m.snapshot);

  async function send() {
    const text = draft.trim();
    if (!text || !conversationId || sending) return;
    setDraft("");
    setMessages((m) => [...m, { id: `u-${Date.now()}`, role: "user", text }]);
    setSending(true);
    try {
      const reply = await entitiesApi.sendCharacterMessage(
        character.id,
        conversationId,
        text,
        { include_cross_incarnation: includeCrossIncarnation },
      );
      setMessages((m) => [
        ...m,
        {
          id: `c-${Date.now()}`,
          role: "char",
          text: reply.text || "…",
          emotional_state: reply.emotional_state,
          snapshot: reply.relationship_snapshot,
        },
      ]);
    } catch (e) {
      notify("error", `Reply failed: ${errorMessage(e)}`);
    } finally {
      setSending(false);
    }
  }

  /** Summarise the recent chat into a scene illustration (never blocks chat). */
  async function generateScene() {
    if (!conversationId || sceneBusy) return;
    setSceneBusy(true);
    try {
      const res = await imageApi.generateScene({ conversation_id: conversationId, last_n: 12 });
      setMessages((m) => [
        ...m,
        { id: `img-${Date.now()}`, role: "char", text: "", image_url: res.image_url },
      ]);
    } catch (e) {
      notify("error", `Scene image failed: ${errorMessage(e)}`);
    } finally {
      setSceneBusy(false);
    }
  }

  const stance = (lastRead?.snapshot?.["stance"] as string) ?? "neutral";

  return (
    <div className="flex h-full min-h-0">
      {/* Conversation column */}
      <div className="flex flex-1 flex-col min-h-0">
        <div className="flex items-center gap-3 border-b border-border p-3">
          <button className="btn-ghost p-1.5" onClick={onBack} title="Back to roster">
            <ArrowLeft className="h-4 w-4" />
          </button>
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-accent-primary/15 text-accent-primary text-xs font-bold">
            {character.name.slice(0, 2).toUpperCase()}
          </div>
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold text-fg-primary">{character.name}</div>
            <div className="truncate text-xs text-fg-muted">{character.description || "Conversatory"}</div>
          </div>
          <button
            className="btn-ghost ml-auto p-1.5"
            onClick={() => void generateScene()}
            disabled={!conversationId || sceneBusy}
            aria-label="Generate scene image"
            title="🖼 Generate scene image from the recent chat"
          >
            {sceneBusy ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <ImagePlus className="h-4 w-4" />
            )}
          </button>
        </div>

        <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto p-4">
          {starting && <div className="text-center text-xs text-fg-muted">Opening conversation…</div>}
          <AnimatePresence initial={false}>
            {messages.map((m) => (
              <motion.div
                key={m.id}
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                className={cn("flex", m.role === "user" ? "justify-end" : "justify-start")}
              >
                <div
                  className={cn(
                    "max-w-[78%] rounded-2xl px-3.5 py-2 text-sm leading-relaxed whitespace-pre-wrap",
                    m.role === "user"
                      ? "bg-accent-primary/20 text-fg-primary rounded-br-sm"
                      : "glass text-fg-secondary rounded-bl-sm",
                  )}
                >
                  {m.image_url && (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={m.image_url}
                      alt="Scene illustration"
                      className="mb-1 max-w-full rounded-lg"
                    />
                  )}
                  {m.text}
                  {m.role === "char" && m.emotional_state && (
                    <div className="mt-1 text-[10px] uppercase tracking-wide text-fg-dim">
                      {m.emotional_state}
                    </div>
                  )}
                </div>
              </motion.div>
            ))}
          </AnimatePresence>
          {sending && (
            <div className="flex justify-start">
              <div className="glass flex items-center gap-1 rounded-2xl rounded-bl-sm px-4 py-3">
                <span className="typing-dot h-1.5 w-1.5 rounded-full bg-fg-muted" />
                <span className="typing-dot h-1.5 w-1.5 rounded-full bg-fg-muted" />
                <span className="typing-dot h-1.5 w-1.5 rounded-full bg-fg-muted" />
              </div>
            </div>
          )}
        </div>

        <div className="flex flex-col gap-2 border-t border-border p-3">
          <label className="flex items-center gap-2 text-[11px] text-fg-muted">
            <input
              type="checkbox"
              checked={includeCrossIncarnation}
              onChange={(e) => setIncludeCrossIncarnation(e.target.checked)}
              className="h-3 w-3 accent-accent-primary"
            />
            Remember across incarnations
            <span className="text-fg-dim">
              (broadens memory recall to other universes of this character)
            </span>
          </label>
          <div className="flex items-end gap-2">
            <textarea
              className="input-cyber max-h-32 min-h-[42px] flex-1 resize-none"
              placeholder={`Message ${character.name}…`}
              value={draft}
              rows={1}
              disabled={starting || !conversationId}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  send();
                }
              }}
            />
            <button
              className="btn-cyber px-3 py-2.5"
              onClick={send}
              disabled={sending || starting || !draft.trim()}
              title="Send"
            >
              <Send className="h-4 w-4" />
            </button>
          </div>
        </div>
      </div>

      {/* Live state side panel */}
      <aside className="hidden w-60 shrink-0 border-l border-border p-4 lg:block">
        <div className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-fg-muted">
          <Sparkles className="h-3.5 w-3.5 text-accent-primary" /> Live read
        </div>
        <div className="space-y-3 text-sm">
          <div>
            <div className="text-xs text-fg-dim">Emotional state</div>
            <div className="text-fg-primary">{lastRead?.emotional_state ?? "—"}</div>
          </div>
          <div>
            <div className="text-xs text-fg-dim">Stance toward you</div>
            <div className="font-medium capitalize text-fg-primary">{stance}</div>
          </div>
          <Meter icon={Heart} label="Trust" value={num(lastRead?.snapshot, "trust")} />
          <Meter icon={Heart} label="Affinity" value={num(lastRead?.snapshot, "affinity")} />
          <Meter icon={ShieldAlert} label="Fear" value={num(lastRead?.snapshot, "fear")} />
          <Meter icon={Sparkles} label="Familiarity" value={num(lastRead?.snapshot, "familiarity")} />
        </div>
        {!character.entity_id && (
          <p className="mt-4 text-xs text-fg-dim">
            This character will be expanded into a full MONITOR profile when you start chatting.
          </p>
        )}
      </aside>
    </div>
  );
}

function Meter({
  icon: Icon,
  label,
  value,
}: {
  icon: React.ElementType;
  label: string;
  value: number;
}) {
  const pct = Math.round(((value + 1) / 2) * 100); // -1..1 → 0..100
  return (
    <div>
      <div className="mb-1 flex items-center justify-between text-xs text-fg-dim">
        <span className="flex items-center gap-1">
          <Icon className="h-3 w-3" /> {label}
        </span>
        <span className="tabular-nums">{value >= 0 ? "+" : ""}{value.toFixed(2)}</span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-bg-base">
        <div
          className={cn("h-full rounded-full", value < 0 ? "bg-red-400/70" : "bg-accent-primary")}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Wire portrait generation in `packages/ui/frontend/src/app/light-rp/page.tsx`** — two edits:

5a — import change:

```tsx
import { entitiesApi, imageApi } from "@/lib/api";
```

5b — add the handler next to `deleteChar` and pass the prop:

```tsx
  async function generatePortrait(c: StandaloneCharacter) {
    try {
      await imageApi.generatePortrait(c.id);
      await qc.invalidateQueries({ queryKey: ["standalone-characters"] });
      notify("success", `Portrait updated for ${c.name}`);
    } catch (e) {
      notify("error", `Portrait failed: ${errorMessage(e)}`);
    }
  }
```

```tsx
        <CharacterCardGrid
          characters={charactersQ.data ?? []}
          onChat={setActive}
          onGeneratePortrait={(c) => void generatePortrait(c)}
          onDelete={(c) => void deleteChar(c)}
        />
```

- [ ] **Step 6: Run tests + typecheck, expect pass:**

```bash
cd packages/ui/frontend && npx vitest run src/components/characters/CharacterChat.test.tsx src/app/light-rp/page.test.tsx && npx tsc --noEmit
```

Expected: all pass; tsc clean.

- [ ] **Step 7: Commit**

```bash
git add packages/ui/frontend/src/lib/api.ts packages/ui/frontend/src/app/light-rp packages/ui/frontend/src/components/characters
git commit -m "feat(ui): portrait + scene image buttons wired to /api/image"
```

---

## Task 9: End-to-end coverage + docs + full verification

**Files:**

- Create: `tests/e2e/test_05_lobby_lightrp_image.py`
- Modify: `docs/USE_CASES.md` (add lobby/light-RP/config/image use cases)
- Modify: `STRUCTURE.md` (new frontend routes: `/` lobby, `/light-rp`, `/config`; new backend router `image_gen.py`; new data-layer module `image_providers.py`)
- Modify: `AGENTS.md` (documentation map stays valid; add the `/config` route + `image_gen` router to the file-locations table if the table's contents changed meaning)

**Interfaces:**

- Consumes: the shared `tests/e2e/conftest.py` fixtures (`e2e_databases`, `e2e_env_bootstrap` — folder storage at `/tmp/monitor_e2e_storage`); `monitor_ui.main.create_app`; `monitor_agents.loops.conversation_loop.ConversationLoop`.
- Produces: a gated e2e (`@pytest.mark.e2e`, run with `RUN_INTEGRATION=1 RUN_E2E=1`) covering: lobby data endpoints return 200 against real containers; a light-RP chat round trip (create card → start conversation → send → reply) with the LLM-dependent loop boundary stubbed; the image endpoints with a fake adapter and real folder storage.

**Steps:**

- [ ] **Step 1: Write the e2e test** — `tests/e2e/test_05_lobby_lightrp_image.py`:

```python
"""
E2E Test 05 — Two-tier hub: lobby data, light-RP round trip, image endpoints.

Covers the 2026-07-31 UI redesign (docs/superpowers/specs/2026-07-31-ui-two-tier-hub-design.md):
  - Lobby load: universe + session list endpoints against real containers.
  - Light RP: create a card, open a conversatory, send one line, get a reply.
    The LLM boundary (ConversationLoop.start/step/finish) is stubbed — LLM
    behaviour is covered elsewhere; this test proves the wiring.
  - Image generation: fake adapter (no network), real folder storage —
    portrait sets avatar_url to the MinIO key, scene returns a stored image.

Run with::

    RUN_INTEGRATION=1 RUN_E2E=1 uv run pytest tests/e2e/test_05_lobby_lightrp_image.py -v
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

PNG = b"\x89PNG-e2e-fake"


class _FakeLoop:
    """Minimal ConversationLoop stand-in (router only touches these members)."""

    def __init__(self) -> None:
        self.state = SimpleNamespace(conversation_id=uuid4())

    async def step(self, text: str) -> list[dict]:
        return [
            {
                "text": f"*the fox grins at '{text}'*",
                "emotional_state": "amused",
                "relationship_snapshot": {"trust": 0.1},
            }
        ]

    async def finish(self) -> list:
        return []


class _FakeImageAdapter:
    async def generate_image(self, prompt: str, *, aspect_ratio: str = "1:1") -> bytes:
        return PNG


@pytest.mark.e2e
class TestTwoTierHub:
    async def test_lobby_lightrp_and_image_flow(self, e2e_databases):
        from monitor_agents.loops.conversation_loop import ConversationLoop

        import monitor_ui.routers.image_gen as image_gen
        from monitor_ui.main import create_app

        with (
            patch.object(
                ConversationLoop,
                "start",
                new=AsyncMock(side_effect=lambda **kwargs: _FakeLoop()),
            ),
            patch.object(
                image_gen,
                "resolve_image_adapter",
                new=AsyncMock(return_value=_FakeImageAdapter()),
            ),
        ):
            with TestClient(create_app()) as client:
                # ── Lobby load ────────────────────────────────────────────
                res = client.get("/api/universes/universes")
                assert res.status_code == 200
                assert isinstance(res.json(), list)

                res = client.get("/api/chat")
                assert res.status_code == 200
                assert isinstance(res.json(), list)

                # ── Light-RP round trip ───────────────────────────────────
                res = client.post(
                    "/api/entities/characters",
                    json={
                        "name": "E2E Wisp",
                        "description": "A fox-spirit guide.",
                        "personality": "playful",
                        "first_message": "Well met, traveller.",
                    },
                )
                assert res.status_code == 201, res.text
                char_id = res.json()["id"]

                res = client.post(f"/api/entities/characters/{char_id}/conversations", json={})
                assert res.status_code == 200, res.text
                conv = res.json()
                assert conv["opening"] == "Well met, traveller."
                conv_id = conv["conversation_id"]

                res = client.post(
                    f"/api/entities/characters/{char_id}/conversations/{conv_id}/send",
                    json={"text": "Hello, fox.", "include_cross_incarnation": False},
                )
                assert res.status_code == 200, res.text
                reply = res.json()
                assert "fox grins" in reply["text"]
                assert reply["emotional_state"] == "amused"

                client.post(f"/api/entities/characters/{char_id}/conversations/{conv_id}/end")

                # ── Image endpoints (fake adapter, real folder storage) ───
                res = client.post("/api/image/portrait", json={"character_id": char_id})
                assert res.status_code == 200, res.text
                portrait = res.json()
                assert portrait["key"].startswith(f"portraits/{char_id}/")
                assert portrait["avatar_url"]  # presigned (or file://) URL

                # avatar_url persisted as the object key, not the URL
                res = client.get(f"/api/entities/characters/{char_id}")
                assert res.json()["avatar_url"] == portrait["key"]

                res = client.get(f"/api/image/avatar/{char_id}", follow_redirects=False)
                assert res.status_code in (302, 307)

                # Scene image needs turns — the conversation ended, so point at
                # a fresh fake adapter call with a missing conversation → 404.
                res = client.post("/api/image/scene", json={"conversation_id": str(uuid4())})
                assert res.status_code == 404

    async def test_image_portrait_400_without_provider(self, e2e_databases):
        import monitor_ui.routers.image_gen as image_gen
        from monitor_ui.main import create_app

        with patch.object(image_gen, "resolve_image_adapter", new=AsyncMock(return_value=None)):
            with TestClient(create_app()) as client:
                res = client.post(
                    "/api/entities/characters",
                    json={"name": "E2E NoPic", "description": "x"},
                )
                assert res.status_code == 201, res.text
                res = client.post("/api/image/portrait", json={"character_id": res.json()["id"]})
                assert res.status_code == 400
                assert "/config" in res.json()["detail"]
```

Notes for the executor:

- If `create_app()`'s lifespan startup (ingest runtime, builtin seeding) proves too heavy/flaky under testcontainers, mirror `tests/e2e/test_00_mvp_smoke.py`'s approach to app construction — but try `TestClient(create_app())` first; the startup helpers are all best-effort (`suppress`/`try` guarded).
- `ConversationLoop.start` is called with kwargs only, so the `AsyncMock(side_effect=lambda **kwargs: _FakeLoop())` shape is load-bearing — do not pass positional args.

- [ ] **Step 2: Run the e2e (gated):**

```bash
RUN_INTEGRATION=1 RUN_E2E=1 uv run pytest tests/e2e/test_05_lobby_lightrp_image.py -v
```

Expected: 2 tests pass. (Skipped silently without the env gates, like the rest of `tests/e2e`.)

- [ ] **Step 3: Update docs** — in `docs/USE_CASES.md` append a section for the new surface area (lobby browsing, light-RP chats, image generation, configuration at `/config`), in `STRUCTURE.md` update the frontend route list and the backend router list, and in `AGENTS.md` refresh the "File Locations Quick Reference" row for settings → `/config` plus a row for `routers/image_gen.py` if the table mentions routers. Keep each edit minimal and factual.

- [ ] **Step 4: Full verification sweep:**

```bash
uv run pytest packages/data-layer -q
uv run pytest packages/ui/backend -q
uv run pytest packages/agents -q
uv run pytest tests/api -q
cd packages/ui/frontend && npm test && npx tsc --noEmit
uv run ruff check packages && uv run ruff format --check packages
uv run mypy packages/*/src --cache-dir /tmp/mypy-cache
python scripts/check_layer_dependencies.py
```

Expected: everything green. Fix forward any fallout in suites touched by the moved settings page or the sidebar changes — do not loosen existing assertions.

- [ ] **Step 5: Commit**

```bash
git add tests/e2e/test_05_lobby_lightrp_image.py docs/USE_CASES.md STRUCTURE.md AGENTS.md
git commit -m "test+docs: two-tier hub e2e, use cases, structure updates"
```

---

## Spec coverage

Mapping of `docs/superpowers/specs/2026-07-31-ui-two-tier-hub-design.md` requirements to tasks:

| Spec item | Task |
|---|---|
| §1 IA: Lobby landing at `/` with Campaigns tab | Task 2 |
| §1 IA: Light RP as separate screen/route `/light-rp` | Task 4 |
| §1 IA: Workbench = World Forge + GM Assistant only | Tasks 1, 5 |
| §1 IA: Configuration top-level section at `/config` | Task 6 |
| §1 Nav: three labeled sidebar tiers | Task 1 |
| §1 Nav: remove `WorldPicker`/`ModeSwitcher` footer dropdowns | Task 1 |
| §1 Nav: fix dead `/universes` link in SetupPanel | Task 1 (link now points straight at `/forge/worlds`; the edge redirect already existed) |
| §2 `ContinuePlayingRail` | Task 2 |
| §2 `UniverseCardGrid` with playable-state + latest story, Play/Stories buttons | Task 2 (`ready`/`needs review` derived from `is_active` — no backend playable-state field exists; `ingesting` state deferred) |
| §2 `NewCampaignWizard` replacing the dropdown chain | Task 3 |
| §2 Data via existing endpoints; no aggregation endpoint unless profiling demands | Tasks 2–3 (three existing list endpoints, client-side join) |
| §3 `CharacterCardGrid` (portrait, name, 1-line summary, memory badge, overflow: Generate portrait/Delete) | Tasks 4, 8 (Export card already exists via `entitiesApi.exportCharacterCardUrl`; Edit stays in the character editor, out of this task's scope) |
| §3 `ImportCardButton` (chara_card_v2 JSON/PNG via existing import endpoint) | Task 4 |
| §3 Recent light chats (resume) rail | Not implemented; deferred — backing endpoint `entitiesApi.listCharacterConversations` exists, follow-up work |
| §3 Future use cases (light-RP→world data, memory inspector) recorded, not implemented | Not implemented; noted in Task 4/9 docs |
| §4 Forge functionally unchanged under Workbench | Task 1 (routes kept; nav group) |
| §4 GM panels + new ask-the-world chat panel querying canon | Task 5 (scoped semantic search endpoint) |
| §4 Panels modifiable (show/hide/reorder, localStorage, no backend change) | Task 5 |
| §5 `/config` reusing LLM registry UI; new image role assignable per provider | Task 6 |
| §5 Image config single place = LLM registry, keys in env/provider store | Task 7 (`adapter_for_provider_row` env fallback mirrors `llm_mgmt` seeding) |
| §6 Data-layer adapter `generate_image(prompt, ...) -> bytes` for MiniMax + nano-banana | Task 7 |
| §6 Portrait endpoint: prompt from card fields → MinIO → set `avatar_url` → return URL | Task 7 (`POST /api/image/portrait`; route shape per approved plan convention, spec's `/characters/{id}/generate-portrait` superseded) |
| §6 Conversation scene endpoint, no card mutation | Task 7 (`POST /api/image/scene`) |
| §6 Pure prompt builders `build_portrait_prompt` / `build_scene_prompt` | Task 7 |
| §6 Frontend: "✨ Generate portrait" on cards, "🖼 Generate scene image" in chat | Task 8 |
| §6 Errors: missing provider → actionable message linking `/config`; provider failure → retryable, never blocks chat | Tasks 7 (400/502) + 8 (notify, chat keeps working) |
| §7 No new databases; images in MinIO; layer rules; `check_layer_dependencies.py` | Tasks 7, 9 |
| §8 Unit tests (adapters, prompt builders), API tests (image router), frontend component tests, e2e lobby path with mocked provider | Tasks 2–8 (unit/component/API), Task 9 (e2e) |
| §8 Existing suites stay green | Task 9 (full sweep) |
| §9 Out of scope (conversion pipeline, memory inspector, streaming/swipes, multiplayer) | Not implemented anywhere in this plan |
