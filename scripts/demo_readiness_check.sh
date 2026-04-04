#!/usr/bin/env bash

set -euo pipefail

API_URL="${API_URL:-http://127.0.0.1:5001}"
WEB_URL="${WEB_URL:-http://127.0.0.1:3000}"
FW_URL="${FW_URL:-http://localhost:3002}"

ok() {
  printf "[OK] %s\n" "$1"
}

warn() {
  WARN_COUNT=$((WARN_COUNT + 1))
  printf "[WARN] %s\n" "$1"
}

fail() {
  FAIL_COUNT=$((FAIL_COUNT + 1))
  printf "[FAIL] %s\n" "$1"
}

check_http_up() {
  local name="$1"
  local url="$2"
  local code
  code="$(curl -sS -o /dev/null -m 5 -w "%{http_code}" "$url" || true)"
  if [[ "$code" == "200" || "$code" == "204" || "$code" == "301" || "$code" == "302" || "$code" == "307" ]]; then
    ok "$name reachable ($url, $code)"
  else
    fail "$name not reachable ($url, status=$code)"
  fi
}

echo "=== Demo Readiness Check ==="
FAIL_COUNT=0
WARN_COUNT=0

check_http_up "Web" "$WEB_URL"
check_http_up "API Docs" "$API_URL/docs"
check_http_up "FastWrite" "$FW_URL"

OPENAPI_JSON="$(mktemp)"
trap 'rm -f "$OPENAPI_JSON"' EXIT
OPENAPI_READY=0
if curl -sS -m 5 "$API_URL/openapi.json" > "$OPENAPI_JSON"; then
  ok "OpenAPI schema fetched"
  OPENAPI_READY=1
else
  fail "Cannot fetch OpenAPI schema"
fi

if [[ "$OPENAPI_READY" -eq 1 ]]; then
python - "$OPENAPI_JSON" <<'PY'
import json
import sys

path = sys.argv[1]
with open(path, "r", encoding="utf-8") as f:
    spec = json.load(f)

paths = set(spec.get("paths", {}).keys())
required = {
    "/api/orchestrator/run",
    "/api/orchestrator/stream/{run_id}",
    "/api/research/stream",
    "/api/notebooks/{notebook_id}/imports/kb",
    "/api/notebooks/{notebook_id}/graph",
    "/api/notebooks/{notebook_id}/insights",
    "/api/notebooks/{notebook_id}/notes/{note_id}/extract",
}
missing = sorted(required - paths)
if missing:
    print("[FAIL] Missing required API paths:")
    for p in missing:
        print(f"  - {p}")
    sys.exit(1)

print("[OK] Required API paths present")
PY
else
  warn "Skip API path check because OpenAPI schema is unavailable"
fi

KB_JSON="$(curl -sS -m 5 "$API_URL/api/kbs" || true)"
NB_JSON="$(curl -sS -m 5 "$API_URL/api/notebooks" || true)"

python - <<'PY' "$KB_JSON" "$NB_JSON"
import json
import sys

kb_raw = sys.argv[1]
nb_raw = sys.argv[2]

def parse_count(raw):
    try:
        data = json.loads(raw)
        rows = data.get("data", [])
        return len(rows)
    except Exception:
        return -1

kb_count = parse_count(kb_raw)
nb_count = parse_count(nb_raw)

if kb_count < 0:
    print("[WARN] Unable to parse KB count")
else:
    if kb_count == 0:
        print("[WARN] No knowledge base found; prepare at least one KB before defense")
    else:
        print(f"[OK] Knowledge bases: {kb_count}")

if nb_count < 0:
    print("[WARN] Unable to parse notebook count")
else:
    if nb_count == 0:
        print("[WARN] No notebook found; prepare at least one notebook before defense")
    else:
        print(f"[OK] Notebooks: {nb_count}")
PY

echo
echo "Recommended manual checks:"
echo "1) Chat page: run one query and confirm citations appear."
echo "2) Research page: confirm both plan and report stream."
echo "3) Notebook page: confirm import progress + graph + insights."
echo "4) Co-writer page: confirm FastWrite is ready."
echo

if [[ "$FAIL_COUNT" -gt 0 ]]; then
  printf "[FAIL] Demo readiness check failed with %s blocking issue(s)\n" "$FAIL_COUNT"
  exit 1
fi
ok "Demo readiness check finished"
