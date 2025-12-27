#!/usr/bin/env bash
#
# Sync local documentation into the GitHub wiki for this repository.
# Requires: git, gh (authenticated), and write access to the repo wiki.
#
# Usage:
#   scripts/sync_docs_to_wiki.sh
#
# The script clones the repo's wiki into a temp directory, copies docs and key
# root files, commits, and pushes the changes. It preserves any existing wiki
# pages not touched by the sync.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export GIT_TERMINAL_PROMPT=0

if ! git -C "$(pwd)" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "❌ Must run inside a git repository."
    exit 1
fi

REMOTE_URL="$(git config --get remote.origin.url)"
if [[ "$REMOTE_URL" =~ github.com[:/]{1,2}([^/]+)/([^/.]+)(\.git)?$ ]]; then
    OWNER="${BASH_REMATCH[1]}"
    REPO="${BASH_REMATCH[2]}"
else
    echo "❌ Could not parse GitHub remote from: $REMOTE_URL"
    exit 1
fi

WIKI_URL="https://github.com/${OWNER}/${REPO}.wiki.git"
TMP_DIR="$(mktemp -d)"
cleanup() {
    rm -rf "$TMP_DIR"
}
trap cleanup EXIT

echo "→ Cloning wiki from $WIKI_URL"
git clone "$WIKI_URL" "$TMP_DIR/wiki"

copy_docs() {
    local src="$1"
    local dest="$2"

    mkdir -p "$dest"

    if command -v rsync >/dev/null 2>&1; then
        rsync -av --exclude ".git" "$src/" "$dest/"
    else
        cp -a "$src/." "$dest/"
    fi
}

flatten_docs() {
    local src="$ROOT/docs"
    local dest="$TMP_DIR/wiki"
    mkdir -p "$dest"
    find "$src" -name "*.md" | while read -r path; do
        rel="${path#$src/}"
        dir="$(dirname "$rel")"
        base="$(basename "$rel")"
        case "$dir" in
            architecture) prefix="Architecture - " ;;
            ontology) prefix="Ontology - " ;;
            *) prefix="" ;;
        esac
        cp "$path" "$dest/${prefix}${base}"
    done
}

flatten_docs

# Key root documents
for file in README.md SYSTEM.md ARCHITECTURE.md STRUCTURE.md CLAUDE.md AGENT_SETUP.md; do
    if [[ -f "$ROOT/$file" ]]; then
        cp "$ROOT/$file" "$TMP_DIR/wiki/"
    fi
done

# Set wiki Home to WIKI_HOME if present, else README
if [[ -f "$ROOT/WIKI_HOME.md" ]]; then
    cp "$ROOT/WIKI_HOME.md" "$TMP_DIR/wiki/Home.md"
elif [[ -f "$ROOT/README.md" ]]; then
    cp "$ROOT/README.md" "$TMP_DIR/wiki/Home.md"
fi

push_changes() {
    cd "$TMP_DIR/wiki"
    git add .
    if git diff --cached --quiet; then
        echo "✓ Wiki already up to date."
        return
    fi

    git commit -m "Sync project docs from main repository"
    git push origin HEAD
    echo "✓ Wiki updated at $WIKI_URL"
}

push_changes
