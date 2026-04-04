#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "[simulate-full-guard] architecture guard drill"
bash scripts/simulate_arch_guard_ci.sh

echo "[simulate-full-guard] dependency guard drill"
bash scripts/simulate_dependency_guard_ci.sh

echo "[simulate-full-guard] passed"
