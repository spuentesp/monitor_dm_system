# Final Fable Implementation Plan

> **STATUS — ✅ COMPLETE (2026-06-13).** All nine tasks below are implemented,
> tested, and committed; the canonical tracker `FINAL_FABLE_TASKS.md` is fully
> green and the live play loop + Q-10 audit trail were verified on the
> dockerized stack (see `docs/STATUS.md`). Where execution diverged from the
> step text — cosmic-ray removed (hangs on the async stack) rather than run;
> native `btn-cyber` buttons instead of the example's `shadcn/ui`; recent
> sessions surfaced via chat sessions — the divergence is recorded in
> `FINAL_FABLE_TASKS.md`. Checkboxes below are closed to reflect completion.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the remaining backend edge cases, testing decisions, documentation verification, and partial React UI features to fully close out the FINAL_FABLE_TASKS and FORGE_INGESTION_PLAN.

**Architecture:** The plan is split into three core phases: Backend Testing & Edge Cases (T-017, T-083), React Frontend Hygiene & Polish (T-058, T-040, T-057, T-060, T-064, T-071), and Pack Operations UI (T-061, T-063). We will use existing FastAPI endpoints for the backend, replace raw React fetches with `@tanstack/react-query`, and build modular React components using the existing `shadcn/ui` style.

**Tech Stack:** Python, FastAPI, Pytest, React, Next.js, Tailwind, React Query.

---

## Phase A: Backend Edge Cases & Testing

### Task 1: Mutation Testing Decision (T-017)

**Files:**
- Modify: `pyproject.toml`
- Modify: `docs/STATUS.md`
- Modify: `FINAL_FABLE_TASKS.md`

- [x] **Step 1: Evaluate and install cosmic-ray**
```bash
uv add --dev cosmic-ray
```

- [x] **Step 2: Run mutation testing on core files**
```bash
uv run cosmic-ray init cosmic-ray.conf canonkeeper.py
uv run cosmic-ray exec cosmic-ray.conf
```
*(If cosmic-ray fails or is incompatible with the async stack, we formally remove mutation testing claims).*

- [x] **Step 3: Update docs/STATUS.md**
Update the "Quality gates" table in `docs/STATUS.md` to either record the kill rate or mark mutation testing as "Removed due to upstream incompatibility".

- [x] **Step 4: Commit**
```bash
git add pyproject.toml docs/STATUS.md FINAL_FABLE_TASKS.md
git commit -m "chore(test): finalize mutation testing decision (T-017)"
```

### Task 2: Ingestion Edge Cases & Resiliency (T-083)

**Files:**
- Modify: `packages/agents/src/monitor_agents/ingestion_pipeline.py`
- Modify: `tests/api/test_ingest_tools.py` (or similar)
- Modify: `FINAL_FABLE_TASKS.md`

- [x] **Step 1: Write test for duplicate content flagging**
```python
def test_duplicate_content_flagging(mocker):
    # Mock db to return existing pack with same hash
    # Assert pipeline returns "flagged_duplicate" status
    pass
```

- [x] **Step 2: Implement huge-PDF streaming budget check**
```python
# In ingestion_pipeline.py
def validate_pdf_size(file_bytes: bytes):
    if len(file_bytes) > 50 * 1024 * 1024: # 50MB
        raise ValueError("File exceeds streaming budget. Chunking required.")
```

- [x] **Step 3: Write embed-down dedicated test**
```python
def test_embed_down_fails_gracefully(mocker):
    mocker.patch("qdrant_client.QdrantClient.upsert", side_effect=Exception("Connection Refused"))
    # Assert job fails with clear stage error, no empty vectors written
    pass
```

- [x] **Step 4: Run tests and Commit**
```bash
uv run pytest tests/api/test_ingest_tools.py -v
git add packages/agents/src/monitor_agents/ingestion_pipeline.py tests/
git commit -m "fix(ingest): add edge case handling and tests (T-083)"
```

---

## Phase B: Frontend Hygiene & Architecture

### Task 3: QueryBoundary & Fetch Refactor (T-058)

**Files:**
- Create: `packages/ui/frontend/src/components/QueryBoundary.tsx`
- Modify: `packages/ui/frontend/src/components/ConnectionStatus.tsx`
- Modify: `FINAL_FABLE_TASKS.md`

- [x] **Step 1: Create QueryBoundary component**
```tsx
import { Suspense } from "react";
import { ErrorBoundary } from "react-error-boundary";

export function QueryBoundary({ children, fallback }: { children: React.ReactNode; fallback?: React.ReactNode }) {
  return (
    <ErrorBoundary fallbackRender={({ error }) => <div className="text-red-500">Error: {error.message}</div>}>
      <Suspense fallback={fallback || <div>Loading...</div>}>
        {children}
      </Suspense>
    </ErrorBoundary>
  );
}
```

- [x] **Step 2: Refactor ConnectionStatus to use React Query instead of raw fetch**
Modify `ConnectionStatus.tsx` to use `useQuery` via the existing `api.ts` clients instead of raw `fetch()`.

- [x] **Step 3: Verify TypeScript and Commit**
```bash
cd packages/ui/frontend && npx tsc --noEmit
git add src/components/QueryBoundary.tsx src/components/ConnectionStatus.tsx
git commit -m "refactor(ui): implement QueryBoundary and replace raw fetches (T-058)"
```

---

## Phase C: UI Features

### Task 4: Play Home /sessions API & Onboarding Wizard (T-040 & T-057)

**Files:**
- Create: `packages/ui/frontend/src/components/play/OnboardingWizard.tsx`
- Modify: `packages/ui/frontend/src/app/page.tsx` (or `PlayHome.tsx`)
- Modify: `FINAL_FABLE_TASKS.md`

- [x] **Step 1: Create OnboardingWizard component**
```tsx
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { forgeApi } from "@/lib/api";

export function OnboardingWizard() {
  const [loading, setLoading] = useState(false);

  const handleDemo = async () => {
    setLoading(true);
    try {
      const res = await forgeApi.demoWorld(true);
      window.location.href = `/play/${res.session_id}`;
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="p-6 border rounded-lg bg-slate-900">
      <h2 className="text-xl font-bold">Welcome to Monitor</h2>
      <p className="text-slate-400 mt-2">Start your journey.</p>
      <Button onClick={handleDemo} disabled={loading} className="mt-4">
        {loading ? "Creating..." : "Try the demo world"}
      </Button>
    </div>
  );
}
```

- [x] **Step 2: Surface `/play-sessions` in Play Home**
Fetch sessions using React Query and map them into recent session cards.

- [x] **Step 3: Commit**
```bash
git add .
git commit -m "feat(ui): add Onboarding Wizard and recent sessions view (T-057, T-040)"
```

### Task 5: Settings Provider Cards (T-060)

**Files:**
- Modify: `packages/ui/frontend/src/app/settings/page.tsx`
- Modify: `FINAL_FABLE_TASKS.md`

- [x] **Step 1: Add "Test All" button and state**
Add a button that iterates over configured LLM providers and calls their respective status endpoints.

- [x] **Step 2: Implement Node Assignments UI**
Build a sub-panel in Settings to list assignments (`useLLMAssignments`) and allow editing them via `api.setAssignment`.

- [x] **Step 3: Commit**
```bash
git add packages/ui/frontend/src/app/settings/page.tsx
git commit -m "feat(ui): add test-all and node assignment settings (T-060)"
```

### Task 6: Pack Ops UI & Batch Select (T-061, T-063)

**Files:**
- Modify: `packages/ui/frontend/src/components/forge/ingest/PackLibrary.tsx`
- Modify: `FINAL_FABLE_TASKS.md`

- [x] **Step 1: Add Batch Selection State**
```tsx
const [selectedPackIds, setSelectedPackIds] = useState<Set<string>>(new Set());
// Add checkboxes to PackLibrary list items
```

- [x] **Step 2: Implement Action Toolbar**
Add a floating action bar when `selectedPackIds.size > 0` containing buttons for Merge, Export, Clone, and Slice. Wire these to the respective `ingestApi` calls.

- [x] **Step 3: Commit**
```bash
git add packages/ui/frontend/src/components/forge/ingest/PackLibrary.tsx
git commit -m "feat(ui): implement pack operations and batch selection (T-061, T-063)"
```

### Task 7: Combat & Progression Panel (T-071)

**Files:**
- Create: `packages/ui/frontend/src/components/play/CombatPanel.tsx`
- Modify: `packages/ui/frontend/src/app/play/[id]/page.tsx` (or equivalent layout)
- Modify: `FINAL_FABLE_TASKS.md`

- [x] **Step 1: Create CombatPanel**
```tsx
export function CombatPanel({ stateDeltas, xp }: { stateDeltas: any; xp: number }) {
  return (
    <div className="combat-panel">
      <h3>Working State</h3>
      {/* Render HP, resources, conditions based on stateDeltas */}
      <div className="xp-bar">XP: {xp}</div>
    </div>
  );
}
```

- [x] **Step 2: Wire up to Play Layout**
Render the `CombatPanel` in the sidebar or HUD context of the active play session.

- [x] **Step 3: Commit**
```bash
git add .
git commit -m "feat(ui): add combat and progression panel (T-071)"
```

### Task 8: Q-10 Audit Trail / History Tab (T-064)

**Files:**
- Create: `packages/ui/frontend/src/components/HistoryTab.tsx`
- Modify: `packages/ui/frontend/src/components/Sidebar.tsx`
- Modify: `FINAL_FABLE_TASKS.md`

- [x] **Step 1: Implement HistoryTab**
Fetch change_log data from the backend and display it in a timeline/list format.

- [x] **Step 2: Commit**
```bash
git add .
git commit -m "feat(ui): add Q-10 audit trail history tab (T-064)"
```

---

## Phase D: Final Verification

### Task 9: Verified Play Pass (T-055)

**Files:**
- Modify: `docs/STATUS.md`
- Modify: `FINAL_FABLE_TASKS.md`

- [x] **Step 1: Run the full stack and execute a manual pass**
Start the stack. Create a world via the new Onboarding Wizard. Play 3 turns of roleplay. Switch to World Architect chat and spawn a new entity.

- [x] **Step 2: Document in STATUS.md**
Update the "Live smoke" or "Verified play pass" section in `docs/STATUS.md` with timestamps and assertions that the UI successfully handled the core loop.

- [x] **Step 3: Commit**
```bash
git add docs/STATUS.md FINAL_FABLE_TASKS.md
git commit -m "docs: record verified play pass (T-055)"
```
