#!/usr/bin/env bash
# Serve the production standalone build for Playwright smokes (T-041).
set -e
cd "$(dirname "$0")"
[ -d .next/standalone ] || { echo "Run 'npm run build' first"; exit 1; }
rm -rf .next/standalone/.next/static .next/standalone/public
cp -r .next/static .next/standalone/.next/static
[ -d public ] && cp -r public .next/standalone/public || true
PORT=${PORT:-3100} HOSTNAME=127.0.0.1 exec node .next/standalone/server.js
