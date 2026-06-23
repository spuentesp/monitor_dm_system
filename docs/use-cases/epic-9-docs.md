# Epic 9: Documentation (DOC)

> As a maintainer, I want documentation published and governed consistently.

## DOC-1: Publish Docs to Wiki

> Epic: Documentation (DOC)

**Actor:** Maintainer
**Trigger:** Release or documentation update

**Flow:**
1. Sync repo docs to GitHub wiki (flattened structure).
2. Set Home page to `WIKI_HOME`.
3. Validate navigation and key links.
4. Include AI setup and contributing guides.

**Output:** Updated wiki with working navigation.

**Implementation**
- Script: `scripts/sync_docs_to_wiki.sh`
- Optional CI: scheduled doc sync or manual run.

---

