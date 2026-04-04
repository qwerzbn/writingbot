#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

BASELINE="config/dependency-cycles-baseline.txt"

echo "[simulate-dep-guard] success path"
GITHUB_ACTIONS=true python scripts/generate_module_dependency_graph.py \
  --output /tmp/module-dependency-graph.success.md \
  --baseline "$BASELINE" >/tmp/dependency_guard_success.log 2>&1

grep -Fq "[dep-guard] summary:" /tmp/dependency_guard_success.log
grep -Fq "::warning title=Dependency Guard::known baseline cycles present:" /tmp/dependency_guard_success.log || true
echo "[simulate-dep-guard] success path verified"

echo "[simulate-dep-guard] failure path"
set +e
GITHUB_ACTIONS=true python scripts/generate_module_dependency_graph.py \
  --output /tmp/module-dependency-graph.failure.md \
  --baseline "$BASELINE" \
  --simulate-new-cycle >/tmp/dependency_guard_failure.log 2>&1
FAIL_CODE=$?
set -e

if [[ "$FAIL_CODE" -eq 0 ]]; then
  echo "[simulate-dep-guard] expected non-zero exit code in failure path" >&2
  exit 1
fi

grep -Fq "::error title=Dependency Guard::new cycles detected:" /tmp/dependency_guard_failure.log
echo "[simulate-dep-guard] failure path error annotation verified"

echo "[simulate-dep-guard] passed"
