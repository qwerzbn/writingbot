#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

ARCH_DOC="${ARCH_DOC_PATH:-docs/upgrade/architecture.md}"
TOTAL_CHECKS=0
PASSED_CHECKS=0

fail() {
  local msg="$1"
  echo "[verify-arch-chat] FAIL ${msg}" >&2
  echo "[verify-arch-chat] summary: passed=${PASSED_CHECKS} failed=1 total=${TOTAL_CHECKS}" >&2
  if [[ "${GITHUB_ACTIONS:-}" == "true" ]]; then
    echo "::error title=Architecture Guard::${msg}" >&2
  fi
  exit 1
}

if [[ ! -f "$ARCH_DOC" ]]; then
  fail "missing doc: ${ARCH_DOC}"
fi

declare -a CHECKS=(
  "src/api/main.py|app.include_router(chat.router|chat router mounted"
  "src/api/routers/chat.py|async def chat_stream(|chat stream entry"
  "src/api/routers/chat.py|def _stream_orchestrator_with_retry(|chat stream worker"
  "src/orchestrator/service.py|def stream_run(|orchestrator run stream"
  "src/orchestrator/service.py|def _step_retrieve(|orchestrator retrieve stage"
  "src/retrieval/hybrid.py|def retrieve_by_sub_questions(|hybrid retrieval fan-out"
  "src/knowledge/vector_store.py|def search(|vector search call"
  "src/skills/registry.py|def resolve_skill_chain(|skills registry resolution"
  "src/skills/runtime.py|def run_research_skill_chain(|skills runtime execution"
  "src/services/llm/client.py|def chat_stream(|llm streaming call"
  "src/session/manager.py|def save(|session persistence"
)
TOTAL_CHECKS="${#CHECKS[@]}"

echo "[verify-arch-chat] validating code anchors"
echo "[verify-arch-chat] arch_doc=${ARCH_DOC}"
echo "[verify-arch-chat] total_checks=${TOTAL_CHECKS}"
for row in "${CHECKS[@]}"; do
  file="${row%%|*}"
  rest="${row#*|}"
  pattern="${rest%%|*}"
  label="${rest#*|}"

  if [[ ! -f "$file" ]]; then
    fail "missing file: ${file} (${label})"
  fi

  if ! grep -Fq "$pattern" "$file"; then
    fail "pattern not found: '${pattern}' in ${file} (${label})"
  fi

  if ! grep -Fq "$file" "$ARCH_DOC"; then
    fail "doc missing file reference: ${file} (${label})"
  fi

  PASSED_CHECKS=$((PASSED_CHECKS + 1))
  echo "[verify-arch-chat] OK $label"
done

echo "[verify-arch-chat] passed"
echo "[verify-arch-chat] summary: passed=${PASSED_CHECKS} failed=0 total=${TOTAL_CHECKS}"
if [[ "${GITHUB_ACTIONS:-}" == "true" ]]; then
  echo "::notice title=Architecture Guard::verify_architecture_chat_refs passed (${PASSED_CHECKS}/${TOTAL_CHECKS})"
fi
