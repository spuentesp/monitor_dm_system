#!/usr/bin/env bash
# Fail if TODO or FIXME markers are present outside docs and license files.

set -euo pipefail

if git grep -InE "TODO|FIXME" -- ':!docs/**' ':!LICENSE' ':!**/*.md'; then
  echo "❌ Found TODO/FIXME markers. Remove or resolve before merging."
  exit 1
fi

echo "✓ No TODO/FIXME markers found."
