#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

MODE="plain"
DEPTH=2
INCLUDE_OPEN_NOTEBOOK=1

usage() {
  cat <<'EOF'
Usage: scripts/print_repo_structure.sh [options]

Options:
  --markdown                Output markdown-friendly format.
  --plain                   Output plain format (default).
  --depth <n>               Directory scan depth (default: 2).
  --exclude-open-notebook   Hide open-notebook subtree.
  --include-open-notebook   Show open-notebook subtree (default).
  -h, --help                Show this help.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --markdown)
      MODE="markdown"
      shift
      ;;
    --plain)
      MODE="plain"
      shift
      ;;
    --depth)
      if [[ $# -lt 2 ]]; then
        echo "missing value for --depth" >&2
        exit 1
      fi
      DEPTH="$2"
      shift 2
      ;;
    --exclude-open-notebook)
      INCLUDE_OPEN_NOTEBOOK=0
      shift
      ;;
    --include-open-notebook)
      INCLUDE_OPEN_NOTEBOOK=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if ! [[ "$DEPTH" =~ ^[0-9]+$ ]]; then
  echo "depth must be a non-negative integer: $DEPTH" >&2
  exit 1
fi

print_dirs() {
  if [[ "$INCLUDE_OPEN_NOTEBOOK" -eq 1 ]]; then
    find . -maxdepth "$DEPTH" -type d \
      \( -path './.git' -o -path './web/node_modules' -o -path './web/.next' -o -path './FastWrite/node_modules' -o -path './FastWrite/web/node_modules' -o -path './open-notebook/.git' \) -prune \
      -o -maxdepth "$DEPTH" -type d -print \
      | sed 's|^\./||' \
      | sort
  else
    find . -maxdepth "$DEPTH" -type d \
      \( -path './.git' -o -path './web/node_modules' -o -path './web/.next' -o -path './FastWrite/node_modules' -o -path './FastWrite/web/node_modules' -o -path './open-notebook' -o -path './open-notebook/*' \) -prune \
      -o -maxdepth "$DEPTH" -type d -print \
      | sed 's|^\./||' \
      | sort
  fi
}

echo "# Repository Structure Snapshot"
echo
echo "## Directory Layer (depth<=$DEPTH, filtered)"
echo
if [[ "$MODE" == "markdown" ]]; then
  echo '```text'
  print_dirs
  echo '```'
else
  print_dirs
fi

echo
echo "## Runtime Chain (high-level)"
echo
if [[ "$MODE" == "markdown" ]]; then
  echo "- 1) start_dev.sh -> FastAPI(5001) + Next.js(3000) + FastWrite API(3003) + FastWrite UI(3002)"
  echo "- 2) web/src/app/api/[...path]/route.ts -> proxy /api/* to 127.0.0.1:5001"
  echo "- 3) src/api/main.py -> include routers(chat/knowledge/notebook/research/co_writer/retrieval/...)"
  echo "- 4) src/api/routers/chat.py -> orchestrator -> retrieval/llm/session persistence"
  echo "- 5) docs/upgrade/repo-structure-overview.md -> repository-level map"
  echo "- 6) docs/upgrade/architecture.md -> deep-dive for api/chat"
else
  echo "1) start_dev.sh -> FastAPI(5001) + Next.js(3000) + FastWrite API(3003) + FastWrite UI(3002)"
  echo "2) web/src/app/api/[...path]/route.ts -> proxy /api/* to 127.0.0.1:5001"
  echo "3) src/api/main.py -> include routers(chat/knowledge/notebook/research/co_writer/retrieval/...)"
  echo "4) src/api/routers/chat.py -> orchestrator -> retrieval/llm/session persistence"
  echo "5) docs/upgrade/repo-structure-overview.md -> repository-level map"
  echo "6) docs/upgrade/architecture.md -> deep-dive for api/chat"
fi

echo
echo "## Anchor Check"
declare -a ANCHORS=(
  "src/api/main.py|app.include_router(chat.router"
  "src/api/routers/chat.py|async def chat_stream("
  "src/orchestrator/service.py|def stream_run("
  "src/retrieval/hybrid.py|def retrieve_by_sub_questions("
  "src/services/llm/client.py|def chat_stream("
  "src/session/manager.py|def save("
)

for item in "${ANCHORS[@]}"; do
  file="${item%%|*}"
  pattern="${item#*|}"
  if grep -Fq "$pattern" "$file"; then
    echo "OK  $file :: $pattern"
  else
    echo "MISS $file :: $pattern"
    exit 1
  fi
done

echo
echo "done"
