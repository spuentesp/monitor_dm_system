# Forge Ingestion — Failure Recovery & Troubleshooting

Companion to `docs/FORGE_INGESTION_PLAN.md §A2`. Every ingestion failure mode
is meant to fail *loudly* with a visible reason and a retry path — never a
silent hang. This page documents the recovery controls and the
**backend-restart-mid-job** path, the one matrix row that needs operator
action rather than an automatic guard.

All controls below live on the Forge → **Sources / Jobs** view (added in
T-084): failed jobs render as a red row with the error and failing stage
inline (auto-expanded), plus per-row **Retry (rescan)** and **Cancel**, and a
toolbar **Unlock queue** / **Purge failed**.

## Recovery after a backend restart mid-job

If `ui-backend` is restarted (deploy, crash, OOM) while a job is mid-flight,
that job's MongoDB document can be left in `running`/`pending` with no worker
behind it — an *orphaned* job that would otherwise hold the single-flight
ingestion lock and block new uploads.

Recover it from the UI in two clicks:

1. **Unlock queue** (toolbar) → `POST /api/ingest/unlock`. Force-clears the
   queue lock and marks any orphaned `pending`/`running` jobs as failed, so the
   queue accepts work again. The orphaned job now shows red with a clear
   "force-unlocked" reason instead of spinning forever.
2. **Retry (rescan)** on the source row → `POST /api/ingest/sources/{source_id}/rescan`.
   Re-runs the analysis pipeline against the already-uploaded file — no
   re-upload needed. The original bytes are reused; a fresh job is created.

If you don't need the source anymore, **Purge failed**
(`DELETE /api/ingest/jobs`) clears all failed/cancelled job rows, or the
per-row delete (`DELETE /api/ingest/jobs/{job_id}`) removes a single one.

## Other matrix rows (all auto-guarded)

| Symptom | What happens | Where |
|---|---|---|
| Empty file (0 bytes) | rejected with "The file is empty (0 bytes)." | `pdf_processing._open_pdf` |
| Huge PDF (>50 MB) | rejected: "File exceeds streaming budget. Chunking required." | `pdf_processing._open_pdf` |
| Corrupt / truncated PDF | "This file could not be opened as a PDF (corrupt or truncated)" | `pdf_processing._open_pdf` |
| Encrypted PDF | "This PDF is password-protected. Remove the password and re-upload." | `pdf_processing._open_pdf` |
| Scanned / no text layer | "No extractable text found — looks like a scanned/image-only PDF." | `pdf_processing.extract_pdf_text` |
| Duplicate upload (same filename) | job → `FLAGGED_DUPLICATE`, no queue deadlock | `ingestion_pipeline` duplicate guard |
| Unsupported type (.png/.zip) | rejected client-side before POST | `UploadCard` validation |
| LLM provider down mid-job | job → failed with the failing stage + cause | `ingestion_pipeline` stage errors |
| Embedding/Qdrant down | job → failed clearly, **no empty-vector writes** | embed guard (T-054) |
| Cancel mid-stage | job → cancelled; queue moves on | `POST /api/ingest/jobs/{job_id}/cancel` |

Regression coverage: PDF-guard tests in
`packages/data-layer/tests/test_db/test_pdf_processing.py`; duplicate-flag and
embed-down tests in `packages/agents/tests/test_ingestion_pipeline.py`;
empty-vector guard in
`packages/data-layer/tests/test_tools/test_qdrant_tools.py`.
