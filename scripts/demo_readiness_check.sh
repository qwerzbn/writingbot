#!/usr/bin/env bash

set -euo pipefail

API_URL="${WRITINGBOT_API_URL:-${API_URL:-http://127.0.0.1:5001}}"
WEB_URL="${WEB_URL:-http://127.0.0.1:3000}"
FW_URL="${FASTWRITE_URL:-${FW_URL:-http://127.0.0.1:3002}}"

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
FW_CODE="$(curl -sS -o /dev/null -m 5 -w "%{http_code}" "$FW_URL" || true)"
if [[ "$FW_CODE" == "200" || "$FW_CODE" == "204" || "$FW_CODE" == "301" || "$FW_CODE" == "302" || "$FW_CODE" == "307" ]]; then
  ok "FastWrite UI reachable ($FW_URL, $FW_CODE)"
else
  warn "FastWrite UI not reachable ($FW_URL, status=$FW_CODE). Degraded co-writer demo path should be used."
fi

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
if python - "$OPENAPI_JSON" <<'PY'
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
    "/api/kbs/{kb_id}/assets",
    "/api/kbs/{kb_id}/assets/{asset_id}/interpret",
    "/api/notebooks/{notebook_id}/imports/kb",
    "/api/notebooks/{notebook_id}/graph-view",
    "/api/notebooks/{notebook_id}/insights",
    "/api/notebooks/{notebook_id}/notes/{note_id}/extract",
    "/api/notebooks/{notebook_id}/migrate-records",
    "/api/notebooks/{notebook_id}/events",
    "/api/fastwrite/health",
}
missing = sorted(required - paths)
if missing:
    print("Missing required API paths:")
    for p in missing:
        print(f"  - {p}")
    sys.exit(1)
PY
then
  ok "Required API paths present"
else
  fail "OpenAPI required path check failed"
fi
else
  warn "Skip API path check because OpenAPI schema is unavailable"
fi

if python - "$API_URL" <<'PY'
import json
import sys
import uuid
import urllib.error
import urllib.request

api = sys.argv[1].rstrip("/")

def request(path: str, method: str = "GET", payload=None, timeout: float = 6.0):
    body = None
    headers = {}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(f"{api}{path}", data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read().decode("utf-8")
            return resp.status, data
    except urllib.error.HTTPError as exc:
        data = exc.read().decode("utf-8")
        return exc.code, data


name = f"demo-check-{uuid.uuid4().hex[:8]}"
status, body = request("/api/notebooks", method="POST", payload={"name": name})
if status != 200:
    print(f"create notebook failed: {status} {body}")
    sys.exit(1)
notebook_id = json.loads(body)["data"]["id"]

try:
    status, body = request(
        f"/api/notebooks/{notebook_id}/notes",
        method="POST",
        payload={"title": "check-note", "content": "demo readiness"},
    )
    if status != 200:
        print(f"create note failed: {status} {body}")
        sys.exit(1)
    note = json.loads(body)["data"]

    status, body = request(
        f"/api/notebooks/{notebook_id}/notes/{note['id']}",
        method="PUT",
        payload={"title": "check-note-updated", "expected_updated_at": note["updated_at"]},
    )
    if status != 200:
        print(f"note optimistic update failed: {status} {body}")
        sys.exit(1)

    status, body = request(
        f"/api/notebooks/{notebook_id}/notes/{note['id']}",
        method="PUT",
        payload={"title": "stale-write", "expected_updated_at": note["updated_at"]},
    )
    if status != 409:
        print(f"expected conflict status 409, got {status}: {body}")
        sys.exit(1)

    status, body = request(
        f"/api/notebooks/{notebook_id}/workspace?search=check&tag=check",
        method="GET",
    )
    if status != 200:
        print(f"workspace filter check failed: {status} {body}")
        sys.exit(1)

    req = urllib.request.Request(
        f"{api}/api/notebooks/{notebook_id}/events?cursor=0",
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=6.0) as resp:
        chunk = resp.read(2048).decode("utf-8", errors="ignore")
        if "data:" not in chunk and ": ping" not in chunk:
            print("events stream did not emit SSE payload")
            sys.exit(1)
finally:
    request(f"/api/notebooks/{notebook_id}", method="DELETE")
PY
then
  ok "Notebook contract behavior checks passed"
else
  fail "Notebook behavior checks failed"
fi

if python - "$API_URL" <<'PY'
import json
import sys
import urllib.request

api = sys.argv[1].rstrip("/")
with urllib.request.urlopen(f"{api}/api/fastwrite/health", timeout=4.0) as resp:
    payload = json.loads(resp.read().decode("utf-8"))
available = bool(payload.get("data", {}).get("available"))
if available:
    print("FastWrite health available")
else:
    print("FastWrite health unavailable")
PY
then
  ok "FastWrite health endpoint reachable"
else
  warn "FastWrite health endpoint check failed"
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
echo "4) Co-writer page: verify available mode or degraded explanation."
echo "5) Degraded path rehearsal: FastWrite down / model timeout / offline fallback."
echo

if [[ "$FAIL_COUNT" -gt 0 ]]; then
  printf "[FAIL] Demo readiness check failed with %s blocking issue(s)\n" "$FAIL_COUNT"
  exit 1
fi
ok "Demo readiness check finished"
