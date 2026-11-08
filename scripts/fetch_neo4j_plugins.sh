#!/usr/bin/env bash
# Fetch the pinned Neo4j plugin jars into infra/neo4j/plugins (gitignored).
# Verifies sha256 after download. Safe to re-run.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLUGINS_DIR="$ROOT/infra/neo4j/plugins"
mkdir -p "$PLUGINS_DIR"

# name | version | sha256
GDS_VERSION="2.6.8"
GDS_SHA256="87311a92b004507b043a6d2ef62ea96f37a6c0aadb5891aa718e9918b8a9e549"
GDS_JAR="neo4j-graph-data-science-${GDS_VERSION}.jar"
GDS_URL="https://github.com/neo4j/graph-data-science/releases/download/${GDS_VERSION}/${GDS_JAR}"

fetch() {
    local url="$1" dest="$2" sha="$3"
    if [[ -f "$dest" ]] && echo "$sha  $dest" | sha256sum --check --quiet 2>/dev/null; then
        echo "ok (cached, checksum verified): $dest"
        return 0
    fi
    echo "downloading $url"
    curl -fL --retry 3 -o "$dest" "$url"
    echo "$sha  $dest" | sha256sum --check
    echo "ok: $dest"
}

# GDS 2.6.x is the line that carries the Neo4j 5.15 adapter. GDS 2.5.x tops out
# at Neo4j 5.13 and fails to load on 5.15 ("not compatible with Neo4j version").
fetch "$GDS_URL" "$PLUGINS_DIR/$GDS_JAR" "$GDS_SHA256"

# APOC core ships bundled with Neo4j 5.x — nothing to fetch.
echo "plugins ready in $PLUGINS_DIR"
