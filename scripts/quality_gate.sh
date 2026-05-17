#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "[quality-gate] running backend tests"
pytest -q

echo "[quality-gate] checking architecture anchors"
bash scripts/verify_architecture_chat_refs.sh

echo "[quality-gate] checking module dependency cycles"
python scripts/generate_module_dependency_graph.py --baseline config/dependency-cycles-baseline.txt

echo "[quality-gate] linting web"
npm --prefix web run lint

echo "[quality-gate] typechecking web"
(cd web && npx tsc --noEmit)

echo "[quality-gate] running web e2e"
npm --prefix web run test:e2e

echo "[quality-gate] building web"
npm --prefix web run build

if [[ -f FastWrite/package.json ]]; then
  echo "[quality-gate] testing embedded FastWrite"
  (cd FastWrite && bun run test)

  echo "[quality-gate] typechecking embedded FastWrite"
  (cd FastWrite && bun run typecheck)
else
  echo "[quality-gate] embedded FastWrite package not found; degraded mode accepted"
fi

echo "[quality-gate] passed"
