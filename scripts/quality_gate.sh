#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "[quality-gate] running backend tests"
pytest -q

echo "[quality-gate] linting web"
npm --prefix web run lint

echo "[quality-gate] building web"
npm --prefix web run build

echo "[quality-gate] passed"
