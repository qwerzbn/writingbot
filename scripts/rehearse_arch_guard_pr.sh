#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

ARTIFACT_DIR="${1:-artifacts/architecture-guard-pr-rehearsal}"
mkdir -p "$ARTIFACT_DIR"

SUCCESS_LOG="$ARTIFACT_DIR/verify-success.log"
FAILURE_LOG="$ARTIFACT_DIR/verify-failure.log"
SIM_LOG="$ARTIFACT_DIR/simulate.log"
SUMMARY_MD="$ARTIFACT_DIR/summary.md"
SNAPSHOT_MD="$ARTIFACT_DIR/repo-structure-snapshot.md"

echo "[arch-pr-rehearsal] artifact_dir=$ARTIFACT_DIR"

echo "[arch-pr-rehearsal] generate snapshot"
bash scripts/print_repo_structure.sh --markdown --exclude-open-notebook >"$SNAPSHOT_MD"

echo "[arch-pr-rehearsal] verify success path"
GITHUB_ACTIONS=true bash scripts/verify_architecture_chat_refs.sh >"$SUCCESS_LOG" 2>&1
grep -Fq "::notice title=Architecture Guard::" "$SUCCESS_LOG"

echo "[arch-pr-rehearsal] verify failure path"
TMP_DOC="$(mktemp)"
echo "# bad doc for rehearsal" >"$TMP_DOC"

set +e
ARCH_DOC_PATH="$TMP_DOC" GITHUB_ACTIONS=true bash scripts/verify_architecture_chat_refs.sh >"$FAILURE_LOG" 2>&1
FAIL_CODE=$?
set -e

if [[ "$FAIL_CODE" -eq 0 ]]; then
  echo "[arch-pr-rehearsal] expected non-zero exit in failure path" >&2
  exit 1
fi
grep -Fq "::error title=Architecture Guard::" "$FAILURE_LOG"

echo "[arch-pr-rehearsal] run local ci-equivalent simulation"
bash scripts/simulate_arch_guard_ci.sh >"$SIM_LOG" 2>&1

{
  echo "# Architecture Guard PR Rehearsal Summary"
  echo
  echo "- artifact_dir: \`$ARTIFACT_DIR\`"
  echo "- failure_exit_code: \`$FAIL_CODE\`"
  echo
  echo "## Success Path (tail)"
  echo
  echo '```text'
  tail -n 20 "$SUCCESS_LOG"
  echo '```'
  echo
  echo "## Failure Path (tail)"
  echo
  echo '```text'
  tail -n 20 "$FAILURE_LOG"
  echo '```'
  echo
  echo "## Simulation (tail)"
  echo
  echo '```text'
  tail -n 20 "$SIM_LOG"
  echo '```'
} >"$SUMMARY_MD"

echo "[arch-pr-rehearsal] done"
echo "[arch-pr-rehearsal] summary=$SUMMARY_MD"
