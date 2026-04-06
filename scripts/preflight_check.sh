#!/usr/bin/env bash

set -Eeuo pipefail

MISSING_REQUIRED=0

ok() {
  printf "[preflight][ok] %s\n" "$1"
}

warn() {
  printf "[preflight][warn] %s\n" "$1"
}

fail() {
  printf "[preflight][fail] %s\n" "$1"
  MISSING_REQUIRED=1
}

require_cmd() {
  local cmd="$1"
  local install_hint="$2"
  if command -v "${cmd}" >/dev/null 2>&1; then
    ok "${cmd} detected"
  else
    fail "${cmd} is missing. ${install_hint}"
  fi
}

optional_cmd() {
  local cmd="$1"
  local message="$2"
  if command -v "${cmd}" >/dev/null 2>&1; then
    ok "${cmd} detected"
  else
    warn "${cmd} is missing. ${message}"
  fi
}

echo "=== WritingBot preflight check ==="
require_cmd "python" "Install Python 3.11+ and ensure it is on PATH."
require_cmd "node" "Install Node.js 20 LTS: https://nodejs.org/"
require_cmd "npm" "npm should be included with Node.js; reinstall Node.js if missing."
optional_cmd "bun" "FastWrite will run in degraded mode. Install bun: https://bun.sh/"

if command -v python >/dev/null 2>&1; then
  if python -m pytest --version >/dev/null 2>&1; then
    ok "pytest detected"
  else
    warn "pytest is missing. Backend test commands will be unavailable until dependencies are installed."
  fi
fi

if [[ "${MISSING_REQUIRED}" -ne 0 ]]; then
  echo "[preflight] Blocking dependency check failed."
  exit 1
fi

echo "[preflight] Environment is ready."
