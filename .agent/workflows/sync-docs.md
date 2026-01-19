---
description: Sync documentation to GitHub wiki
---

# Sync Documentation to Wiki

Syncs MONITOR documentation from the repository to the GitHub wiki.

## Prerequisites

- `gh` CLI installed and authenticated
- Write access to the repository

## Steps

1. Ensure you're authenticated with GitHub CLI:
   ```bash
   gh auth status
   ```
   If not authenticated, run:
   ```bash
   gh auth login
   ```

// turbo
2. Run the sync script:
   ```bash
   bash scripts/sync_docs_to_wiki.sh
   ```

3. Verify changes on GitHub wiki:
   - Visit: `https://github.com/<org>/<repo>/wiki`
   - Check that documentation pages are updated

## What Gets Synced

The script syncs these files to the wiki:

- `README.md` → Wiki Home
- `SYSTEM.md` → System Overview
- `ARCHITECTURE.md` → Architecture
- `STRUCTURE.md` → Project Structure
- `CLAUDE.md` → AI Agent Instructions
- `CONTRIBUTING.md` → Contributing Guide
- `docs/USE_CASES.md` → Use Cases
- `docs/AI_DOCS.md` → AI Reference
- `docs/IMPLEMENTATION_GUIDE.md` → Implementation Guide
- All files in `docs/architecture/`
- All files in `docs/ontology/`

## Manual Sync

If you need to sync a specific file:

```bash
gh api repos/:owner/:repo/wiki/pages/<page-name> \
  -X PUT \
  -f content=@path/to/file.md \
  -f title="Page Title"
```

## Troubleshooting

**Error**: `gh: command not found`

**Fix**: Install GitHub CLI:
```bash
# macOS
brew install gh

# Windows (with Chocolatey)
choco install gh

# Linux
# See: https://github.com/cli/cli/blob/trunk/docs/install_linux.md
```

**Error**: `HTTP 404: Not Found (wiki not initialized)`

**Fix**: Initialize wiki manually:
1. Go to repository on GitHub
2. Click "Wiki" tab
3. Create first page
4. Run script again

**Error**: `HTTP 403: Forbidden`

**Fix**: Ensure you have write access to the repository

## Wiki vs Repository Docs

| Location | Purpose | Audience |
|----------|---------|----------|
| **Repository** | Source of truth, version controlled | Developers, AI agents |
| **Wiki** | Human-readable docs, easier navigation | Users, contributors |

Changes should be made in the repository, then synced to wiki.

## Frequency

Sync documentation when:
- Adding new documentation files
- Making significant doc updates
- Before major releases
- When onboarding new contributors

## Next Steps

- Verify wiki pages look correct
- Share wiki link with team/contributors
- Update wiki home page if needed
