#!/usr/bin/env bash
# Run mutation tests locally against one or all configured modules.
#
# Usage:
#   ./scripts/run_mutations.sh              # run all modules sequentially
#   ./scripts/run_mutations.sh resolver     # run one module
#   ./scripts/run_mutations.sh --list       # print available targets
#
# Requires: uv, cosmic-ray (uv pip install "cosmic-ray>=8.0")
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

declare -A CONFIGS=(
    [canonkeeper]="cosmic-ray.toml"
    [resolver]="cosmic-ray-resolver.toml"
    [npc-voice]="cosmic-ray-npc-voice.toml"
    [scene-loop]="cosmic-ray-scene-loop.toml"
    [story-loop]="cosmic-ray-story-loop.toml"
    [resource-engine]="cosmic-ray-resource-engine.toml"
    [world-architect]="cosmic-ray-world-architect.toml"
    [plot-hooks]="cosmic-ray-plot-hooks.toml"
    [delta-detection]="cosmic-ray-delta-detection.toml"
    [contradiction]="cosmic-ray-contradiction.toml"
    [context-assembly]="cosmic-ray-context-assembly.toml"
    [narrator]="cosmic-ray-narrator.toml"
    [simulacrum]="cosmic-ray-simulacrum.toml"
)

# Print targets and exit
if [[ "${1:-}" == "--list" ]]; then
    echo "Available mutation targets:"
    for name in "${!CONFIGS[@]}"; do
        printf "  %-22s %s\n" "$name" "${CONFIGS[$name]}"
    done | sort
    exit 0
fi

TARGET="${1:-}"

# Collect scores for summary
declare -A SCORES

run_one() {
    local name="$1"
    local toml="${CONFIGS[$name]}"
    local session="session-${name}.sqlite"

    echo ""
    echo "════════════════════════════════════════"
    echo "  $name  ($toml)"
    echo "════════════════════════════════════════"
    rm -f "$session"
    uv run cosmic-ray init "$toml" "$session"
    uv run cosmic-ray exec "$toml" "$session"
    echo ""
    REPORT=$(uv run cr-report "$session") || exit 1
    echo "$REPORT"
    SCORE=$(echo "$REPORT" | python3 -c "
import sys, re
text = sys.stdin.read()
pct = re.search(r'kill rate[:\s]+(\d+\.?\d*)\s*%', text, re.IGNORECASE)
dec = re.search(r'score[:\s]+(\d+\.\d+)', text, re.IGNORECASE)
if pct:   print(round(float(pct.group(1))))
elif dec: print(round(float(dec.group(1)) * 100))
else:     print('FAIL')
")
    if [ "$SCORE" = "FAIL" ]; then
        echo "Failed to parse mutation score from cr-report output."
        exit 1
    fi
    SCORES[$name]=$SCORE
}

if [[ -n "$TARGET" ]]; then
    if [[ -z "${CONFIGS[$TARGET]+_}" ]]; then
        echo "Unknown target '$TARGET'. Run --list to see available targets." >&2
        exit 1
    fi
    run_one "$TARGET"
else
    for name in $(echo "${!CONFIGS[@]}" | tr ' ' '\n' | sort); do
        run_one "$name"
    done
fi

# Summary table
if [[ ${#SCORES[@]} -gt 1 ]]; then
    echo ""
    echo "════════ SUMMARY ════════"
    TOTAL=0
    COUNT=0
    for name in $(echo "${!SCORES[@]}" | tr ' ' '\n' | sort); do
        score="${SCORES[$name]}"
        bar=$(python3 -c "n=$score; print('█'*(n//5) + '░'*(20-n//5))")
        printf "  %-22s %s %d%%\n" "$name" "$bar" "$score"
        TOTAL=$((TOTAL + score))
        COUNT=$((COUNT + 1))
    done
    AVG=$((TOTAL / COUNT))
    echo "  ─────────────────────────────────────"
    printf "  %-22s %d%% across %d modules\n" "AGGREGATE" "$AVG" "$COUNT"
fi
