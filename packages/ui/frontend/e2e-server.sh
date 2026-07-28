#!/usr/bin/env bash
# Serve the production standalone build for Playwright smokes (T-041).
set -e
cd "$(dirname "$0")"

# Locate standalone server.js — Next emits it at one of two paths
# depending on whether the project sits at the repo root or is nested.
if [ -f .next/standalone/server.js ]; then
  BASE_DIR=".next/standalone"
elif [ -f .next/standalone/packages/ui/frontend/server.js ]; then
  BASE_DIR=".next/standalone/packages/ui/frontend"
else
  echo "ERROR: standalone server.js not found in either of:"
  echo "  .next/standalone/server.js"
  echo "  .next/standalone/packages/ui/frontend/server.js"
  echo "Available under .next/standalone/:"
  find .next/standalone -maxdepth 3 -name 'server.js' 2>/dev/null || true
  echo "Run 'npm run build' first."
  exit 1
fi

# Stage static + public into the standalone dir (Next requires these
# to be colocated with server.js at runtime).
rm -rf "$BASE_DIR/.next/static" "$BASE_DIR/public"
mkdir -p "$BASE_DIR/.next"
[ -d .next/static ] && cp -r .next/static "$BASE_DIR/.next/static"
[ -d public ] && cp -r public "$BASE_DIR/public"

PORT=${PORT:-3100} HOSTNAME=127.0.0.1 exec node "$BASE_DIR/server.js"
