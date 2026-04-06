#!/usr/bin/env bash

set -Eeuo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="${PROJECT_ROOT}/.logs"
mkdir -p "${LOG_DIR}"

WRITINGBOT_API_PORT="${WRITINGBOT_API_PORT:-5001}"
WRITINGBOT_WEB_PORT="${WRITINGBOT_WEB_PORT:-3000}"
FASTWRITE_WEB_PORT="${FASTWRITE_WEB_PORT:-3002}"
FASTWRITE_API_PORT="${FASTWRITE_API_PORT:-3003}"

export WRITINGBOT_API_URL="${WRITINGBOT_API_URL:-http://127.0.0.1:${WRITINGBOT_API_PORT}}"
export FASTWRITE_URL="${FASTWRITE_URL:-http://127.0.0.1:${FASTWRITE_WEB_PORT}}"
export NEXT_PUBLIC_FASTWRITE_URL="${NEXT_PUBLIC_FASTWRITE_URL:-${FASTWRITE_URL}}"

declare -a PIDS=()
FASTWRITE_MODE="disabled"

log() {
  printf "[start_dev] %s\n" "$*"
}

warn() {
  printf "[start_dev][warn] %s\n" "$*"
}

cleanup() {
  log "Stopping background services..."
  for pid in "${PIDS[@]:-}"; do
    if kill -0 "${pid}" >/dev/null 2>&1; then
      kill "${pid}" >/dev/null 2>&1 || true
    fi
  done
}

trap cleanup INT TERM EXIT

kill_port() {
  local port="$1"
  if ! command -v lsof >/dev/null 2>&1; then
    return 0
  fi
  local pid_list
  pid_list="$(lsof -ti ":${port}" || true)"
  if [[ -n "${pid_list}" ]]; then
    warn "Port ${port} is occupied, terminating stale process(es): ${pid_list}"
    while IFS= read -r pid; do
      [[ -z "${pid}" ]] && continue
      kill "${pid}" >/dev/null 2>&1 || true
    done <<< "${pid_list}"
  fi
}

wait_http() {
  local name="$1"
  local url="$2"
  local max_retry="${3:-20}"
  local i
  for ((i = 1; i <= max_retry; i += 1)); do
    if command -v curl >/dev/null 2>&1; then
      if curl -sS -m 2 -o /dev/null "${url}" >/dev/null 2>&1; then
        log "${name} is ready (${url})"
        return 0
      fi
    else
      return 0
    fi
    sleep 1
  done
  warn "${name} did not become ready in time (${url})"
  return 1
}

log "Running dependency preflight check..."
"${PROJECT_ROOT}/scripts/preflight_check.sh"

log "Cleaning stale ports..."
kill_port "${WRITINGBOT_API_PORT}"
kill_port "${WRITINGBOT_WEB_PORT}"
kill_port "${FASTWRITE_WEB_PORT}"
kill_port "${FASTWRITE_API_PORT}"

cd "${PROJECT_ROOT}"

log "Starting WritingBot backend on :${WRITINGBOT_API_PORT}"
python -m uvicorn src.api.main:app \
  --host 0.0.0.0 \
  --port "${WRITINGBOT_API_PORT}" \
  --reload \
  --reload-exclude "data/*" \
  --reload-exclude "web/*" \
  --reload-exclude ".git/*" \
  --reload-exclude "FastWrite/*" \
  --reload-exclude ".env" \
  > "${LOG_DIR}/backend.log" 2>&1 &
PIDS+=("$!")

wait_http "WritingBot API" "${WRITINGBOT_API_URL}/api/health" 30 || true

log "Starting WritingBot web on :${WRITINGBOT_WEB_PORT}"
(
  cd "${PROJECT_ROOT}/web"
  npm run dev
) > "${LOG_DIR}/web.log" 2>&1 &
PIDS+=("$!")

FASTWRITE_ROOT="${PROJECT_ROOT}/FastWrite"
if [[ -d "${FASTWRITE_ROOT}" && -f "${FASTWRITE_ROOT}/package.json" ]]; then
  if command -v bun >/dev/null 2>&1; then
    FASTWRITE_MODE="enabled"
    log "Starting FastWrite API on :${FASTWRITE_API_PORT}"
    (
      cd "${FASTWRITE_ROOT}"
      PORT="${FASTWRITE_API_PORT}" bun run --watch src/server.ts
    ) > "${LOG_DIR}/fastwrite-api.log" 2>&1 &
    PIDS+=("$!")

    if [[ -d "${FASTWRITE_ROOT}/web" ]]; then
      log "Starting FastWrite web on :${FASTWRITE_WEB_PORT}"
      (
        cd "${FASTWRITE_ROOT}/web"
        bun run dev --no-open --port "${FASTWRITE_WEB_PORT}"
      ) > "${LOG_DIR}/fastwrite-web.log" 2>&1 &
      PIDS+=("$!")
    else
      FASTWRITE_MODE="degraded"
      warn "FastWrite web directory not found; co-writer will stay in degraded mode."
    fi
  else
    FASTWRITE_MODE="degraded"
    warn "bun not found; FastWrite skipped. Install bun to enable co-writer."
  fi
else
  FASTWRITE_MODE="degraded"
  warn "FastWrite project unavailable; co-writer page will show degraded mode."
fi

echo
echo "=========================================="
echo " WritingBot development services started"
echo "=========================================="
echo " WritingBot API : ${WRITINGBOT_API_URL}"
echo " WritingBot Web : http://127.0.0.1:${WRITINGBOT_WEB_PORT}"
echo " FastWrite mode : ${FASTWRITE_MODE}"
if [[ "${FASTWRITE_MODE}" == "enabled" ]]; then
  echo " FastWrite API  : http://127.0.0.1:${FASTWRITE_API_PORT}"
  echo " FastWrite Web  : ${FASTWRITE_URL}"
fi
echo " Logs directory : ${LOG_DIR}"
echo "=========================================="
echo " Press Ctrl+C to stop all services."
echo

wait
