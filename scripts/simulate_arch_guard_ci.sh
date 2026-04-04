#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "[simulate-arch-guard] success path"
GITHUB_ACTIONS=true bash scripts/verify_architecture_chat_refs.sh >/tmp/arch_guard_success.log 2>&1
grep -Fq "::notice title=Architecture Guard::" /tmp/arch_guard_success.log
echo "[simulate-arch-guard] success path notice verified"

echo "[simulate-arch-guard] failure path"
TMP_DOC="$(mktemp)"
echo "# bad doc (no anchors)" > "$TMP_DOC"

set +e
ARCH_DOC_PATH="$TMP_DOC" GITHUB_ACTIONS=true bash scripts/verify_architecture_chat_refs.sh >/tmp/arch_guard_failure.log 2>&1
FAIL_CODE=$?
set -e

if [[ "$FAIL_CODE" -eq 0 ]]; then
  echo "[simulate-arch-guard] expected non-zero exit code in failure path" >&2
  exit 1
fi

grep -Fq "::error title=Architecture Guard::" /tmp/arch_guard_failure.log
echo "[simulate-arch-guard] failure path error annotation verified"

echo "[simulate-arch-guard] passed"
