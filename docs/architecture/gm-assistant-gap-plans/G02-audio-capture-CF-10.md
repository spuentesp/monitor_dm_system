# G02 — Audio / hybrid session capture (proposed CF-10)

> **Status:** implemented 2026-11-11 as **CF-10** (pluggable transcription
> registry + upload/transcribe/queue routes + the segment review panel in
> the recorder). The live pass (phase 5) is **not** done. Originally
> proposed 2026-11-11. Gap: CF-1 capture is text-only; audio was
> descoped in P3.1 (2026-11-06) because it needs a transcription vendor,
> diarization, and a new ingest path. But EPIC 7's verb is "listen" — a GM
> cannot type notes while running the game, so real sessions under-capture.

## Goal

Let the GM record the table session (audio) or upload a recording, get a
transcript with speaker diarization, and feed it through the *existing*
CF-1 pipeline (insights → draft scenes → `ProposedChange` → CF-8) with zero
new canon authority: audio is just another input mode of CF-1.

## Use case

Propose **CF-10 "Audio Capture & Transcription"** in
`docs/use-cases/epic-7-copilot-CF/CF-10/`; it *amends* CF-1's "Input Modes"
(undo the P3.1 descope note in `CF-1-specification.md:22-26` once shipped).

## Scope

**In:** browser MediaRecorder upload → MinIO object (pattern from
`image_gen.py` storage); async transcription job (existing jobs infra,
`routers/jobs_health.py` pattern) via a pluggable provider
(`data-layer/src/monitor_data/llm/` — new `transcription_providers.py`
mirroring `image_providers.py`, tiered like the LLM registry, SYS-4 pattern);
optional speaker diarization (GM labels speakers after the fact);
transcript → existing `session_ingest.py` / `capture_insights.py` path;
per-segment review UI before anything becomes a proposal.
**Out (v1):** real-time/live transcription during play, voice biometrics,
automatic speaker identification (GM maps diarized speakers to entities
manually), on-device transcription.

## Phases

| Phase | Work | Notes |
|-------|------|-------|
| 1 | Vendor decision + provider adapter + registry `transcription` role | Decision needed first: hosted API (cost, data egress) vs. local whisper.cpp. Record in `MULTI_TENANCY_PLAN`-style doc since audio is sensitive personal data — owner-scoped storage keys, quota per SYS-6. |
| 2 | Upload + job plumbing (MinIO, job queue, status polling) | Reuse ingest job patterns (`routers/ingest.py`, `jobs_health.py`). 200MB cap precedent from ingestion audit. |
| 3 | Transcription → transcript segments schema in Mongo (`schemas/transcripts.py`), diarization labels | Layer 1 tools: `mongodb_tools/transcripts.py`. |
| 4 | Segment review UI in recorder panel: play segment, confirm/edit text, map speakers, "queue as entry" → CF-1 flow | `components/gm/SessionRecorder.tsx` extension + new `TranscriptReview.tsx`. |
| 5 | Tests + live verification | `test_gm_audio_capture.py` (backend, fake provider), agent tests with FakeLLMClient, vitest for review UI; live pass appended to `docs/testing/live_gm_assistant_*.md`. |

## Acceptance

- GM records audio (or uploads a file), gets a transcript with segments,
  reviews/edits it, and queues segments into the CF-1 capture flow; the
  resulting proposals appear in CF-8 exactly as typed entries do.
- Audio blobs are owner-scoped, quota-metered (SYS-6), and never leave the
  workspace without an explicit provider config.
- PII consideration documented: diarized speech is personal data; retention
  and deletion path defined.

## Which backends can actually transcribe (probed 2026-11-11)

The vendor decision became a *configuration* decision, so the question became
"can the providers this workspace already has transcribe?". Probed against
the live registry (a one-second WAV posted to each candidate endpoint):

| Provider | Base URL | Audio endpoint |
|---|---|---|
| MiMo v2.6 Flash (`custom`) | `token-plan-sgp.xiaomimimo.com/v1` | **404** — the gateway exposes chat only |
| MiniMax M2.7 (`minimax`) | `api.minimax.io/anthropic` | Anthropic-compatible chat; no OpenAI-style audio route. Its registry rows also carry **no credential** — the key never made it into the registry — so they cannot be called at all. |
| Ollama (`ollama`) | `localhost:11434` | no audio models |

**So no configured provider can transcribe today.** That is a configuration
gap, not a code gap: the registry accepts a row with `role='transcription'`
(the /config page has a "Transcription" role tier), and any OpenAI-compatible
audio endpoint works — OpenAI, Groq, Azure, or a self-hosted gateway in front
of the workspace's own models. The local path (`MONITOR_TRANSCRIPTION_COMMAND`)
needs a whisper install and nothing else.

The **live pass** (phase 5) therefore remains open: the capture flow was
verified against the live stack with a scripted local backend, but no real
speech-to-text model was available in this environment to verify the
transcription itself.

## Open decisions

- Real-time vs. post-session only: v1 is post-session; live transcription is
  a later phase.
- This plan **reverses the P3.1 descope**; `GM_ASSISTANT_MODE_PLAN.md` §P3.1
  and the CF-1 spec are updated.
