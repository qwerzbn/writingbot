#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

OUT_PATH="${1:-docs/upgrade/structure-drift-dashboard.md}"
STRICT_MODE="${STRICT_MODE:-0}"

TMP_DIR="$(mktemp -d)"
ARCH_LOG="$TMP_DIR/arch_guard.log"
DEP_LOG="$TMP_DIR/dependency_guard.log"
DEP_GRAPH_TMP="$TMP_DIR/module-dependency-graph.md"

ARCH_STATUS="PASS"
ARCH_CODE=0
if ! bash scripts/verify_architecture_chat_refs.sh >"$ARCH_LOG" 2>&1; then
  ARCH_CODE=$?
  ARCH_STATUS="FAIL"
fi

DEP_STATUS="PASS"
DEP_CODE=0
if ! python scripts/generate_module_dependency_graph.py \
  --output "$DEP_GRAPH_TMP" \
  --baseline config/dependency-cycles-baseline.txt >"$DEP_LOG" 2>&1; then
  DEP_CODE=$?
  DEP_STATUS="FAIL"
fi

DEP_SUMMARY_LINE="$(grep -F '[dep-guard] summary:' "$DEP_LOG" | tail -n1 || true)"
DETECTED="$(echo "$DEP_SUMMARY_LINE" | sed -nE 's/.*detected=([0-9]+).*/\1/p')"
BASELINE="$(echo "$DEP_SUMMARY_LINE" | sed -nE 's/.*baseline=([0-9]+).*/\1/p')"
NEW_CYCLES="$(echo "$DEP_SUMMARY_LINE" | sed -nE 's/.*new=([0-9]+).*/\1/p')"
RESOLVED="$(echo "$DEP_SUMMARY_LINE" | sed -nE 's/.*resolved=([0-9]+).*/\1/p')"

DETECTED="${DETECTED:-n/a}"
BASELINE="${BASELINE:-n/a}"
NEW_CYCLES="${NEW_CYCLES:-n/a}"
RESOLVED="${RESOLVED:-n/a}"

LATEST_DRILL_SUMMARY="$(ls -t artifacts/*/summary.md 2>/dev/null | head -n1 || true)"
LATEST_DRILL_CODE="n/a"
if [[ -n "$LATEST_DRILL_SUMMARY" ]]; then
  LATEST_DRILL_CODE="$(grep -E 'failure_exit_code' "$LATEST_DRILL_SUMMARY" | head -n1 | sed -E 's/.*`([0-9]+)`.*/\1/' || true)"
  LATEST_DRILL_CODE="${LATEST_DRILL_CODE:-n/a}"
fi

OVERALL="GREEN"
if [[ "$ARCH_STATUS" != "PASS" || "$DEP_STATUS" != "PASS" ]]; then
  OVERALL="RED"
fi

mkdir -p "$(dirname "$OUT_PATH")"
{
  echo "# Structure Drift Dashboard"
  echo
  echo "Generated at: $(date '+%Y-%m-%d %H:%M:%S %z')"
  echo
  echo "## Guard Health"
  echo
  echo "| Check | Status | Exit Code |"
  echo "|---|---|---:|"
  echo "| Architecture anchor guard | ${ARCH_STATUS} | ${ARCH_CODE} |"
  echo "| Dependency cycle guard | ${DEP_STATUS} | ${DEP_CODE} |"
  echo
  echo "## Cycle Metrics"
  echo
  echo "| Metric | Value |"
  echo "|---|---:|"
  echo "| Detected cycle SCC | ${DETECTED} |"
  echo "| Baseline cycle SCC | ${BASELINE} |"
  echo "| New cycle SCC | ${NEW_CYCLES} |"
  echo "| Resolved cycle SCC | ${RESOLVED} |"
  echo
  echo "## Drill Status"
  echo
  echo "- Overall: \`${OVERALL}\`"
  echo "- Latest drill summary: \`${LATEST_DRILL_SUMMARY:-n/a}\`"
  echo "- Latest drill failure_exit_code: \`${LATEST_DRILL_CODE}\`"
  echo
  echo "## Logs (tail)"
  echo
  echo "### Architecture Guard"
  echo
  echo '```text'
  tail -n 20 "$ARCH_LOG" || true
  echo '```'
  echo
  echo "### Dependency Guard"
  echo
  echo '```text'
  tail -n 20 "$DEP_LOG" || true
  echo '```'
} >"$OUT_PATH"

echo "[drift-dashboard] output=$OUT_PATH"
echo "[drift-dashboard] overall=$OVERALL arch=${ARCH_STATUS} dep=${DEP_STATUS} new_cycles=${NEW_CYCLES}"

if [[ "$STRICT_MODE" == "1" && "$OVERALL" == "RED" ]]; then
  exit 1
fi
