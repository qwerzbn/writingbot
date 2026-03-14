#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "[release-gate] running pytest"
pytest -q

echo "[release-gate] running api smoke"
pytest -q tests/test_new_api_endpoints_smoke.py tests/test_fastwrite_bridge.py

echo "[release-gate] linting web"
npm --prefix web run lint

echo "[release-gate] building web"
npm --prefix web run build

echo "[release-gate] checking latest evaluation report"
python - <<'PY'
import json
from pathlib import Path

reports_dir = Path("data/evaluation/reports")
if not reports_dir.exists():
    raise SystemExit("release gate failed: data/evaluation/reports not found")

reports = sorted(reports_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
if not reports:
    raise SystemExit(
        "release gate failed: no evaluation report found; "
        "run /api/evaluation/run or trigger it from Settings first"
    )

latest = reports[0]
with latest.open(encoding="utf-8") as f:
    report = json.load(f)

summary = report.get("summary", {})
gate = report.get("gate", {})
status = report.get("status")

cp = float(summary.get("Citation Precision", 0.0))
faith = float(summary.get("Faithfulness", 0.0))
if status == "blocked" or cp < 0.85 or faith < 0.80:
    raise SystemExit(
        f"release gate failed: latest report {latest.name} blocked "
        f"(Citation Precision={cp:.4f}, Faithfulness={faith:.4f}, gate={gate})"
    )

print(
    f"release gate passed with {latest.name}: "
    f"Citation Precision={cp:.4f}, Faithfulness={faith:.4f}"
)
PY
