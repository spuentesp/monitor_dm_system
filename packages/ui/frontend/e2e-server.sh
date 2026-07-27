#!/usr/bin/env bash
# Serve the production standalone build for Playwright smokes (T-041).
set -e
cd "$(dirname "$0")"
[ -d .next/standalone ] || { echo "Run 'npm run build' first"; exit 1; }

if [ -f .next/standalone/server.js ]; then
  BASE_DIR=".next/standalone"
else
  BASE_DIR=".next/standalone/packages/ui/frontend"
fi

rm -rf "$BASE_DIR/.next/static" "$BASE_DIR/public"
mkdir -p "$BASE_DIR/.next"
cp -r .next/static "$BASE_DIR/.next/static"
[ -d public ] && cp -r public "$BASE_DIR/public" || true

PORT=${PORT:-3100} HOSTNAME=127.0.0.1 exec node "$BASE_DIR/server.js"
