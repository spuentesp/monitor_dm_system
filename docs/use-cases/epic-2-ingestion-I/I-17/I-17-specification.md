# I-17: Exhaustive Book Decomposition

**Actor:** IngestionPipeline
**Trigger:** A book is ingested, whole or in parts.

**Purpose:** Turn an entire book into a traceable graph, with nothing selected or sampled, so that every claim cites the sentences it came from and every sentence has a recorded outcome.

**Status:** Built, off by default behind `MONITOR_BOOK_DECOMPOSITION`. It runs as a separate background job after a PDF ingest, and can pause and resume. Not yet run with live models.

**Flow:**
1. System decomposes the PDF into book → division → paragraph → sentence, losing no text, with IDs derived from content.
2. System extracts claims from every sentence, citing the sentences they came from, or records why a sentence yields none.
3. A failed or interrupted run resumes from an append-only log, sending only the sentences still missing.
4. System reviews claims: it verifies each against its source, sets examples aside, merges duplicates, and sends doubts to a person.
5. System checks each paragraph for what its claims leave out, and verified gaps go through review as new claims.
6. System builds separate rules and lore trees, and optionally graphs, where every relationship cites its claims.
7. System creates one review-ready KnowledgePack, with source sentences as evidence.

**Output:** Reviewed claims linked to their source sentences and to each other, plus a ledger giving every claim's outcome. Reaching canon goes through the existing pack review and CanonKeeper.

**Design:** [Book Decomposition Plan](../../../architecture/BOOK_DECOMPOSITION_PLAN.md)
