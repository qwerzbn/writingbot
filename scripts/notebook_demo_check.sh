#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$ROOT_DIR"

echo "=== Notebook Demo Check ==="
echo

echo "[1/3] Readiness check"
bash scripts/demo_readiness_check.sh

echo
echo "[2/3] Notebook backend tests"
pytest -q tests/test_notebook_service_v2.py tests/test_notebook_router_v2.py

echo
echo "[3/3] Notebook frontend e2e"
(
  cd web
  npx playwright test e2e/notebook.spec.ts
)

echo
echo "[OK] Notebook demo check finished"
