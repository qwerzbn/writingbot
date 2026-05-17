# Repository Structure Snapshot

## Directory Layer (depth<=2, filtered)

```text
.
.argusbot
.argusbot/bus
.argusbot/logs
.github
.github/workflows
.logs
.playwright-mcp
.pytest_cache
.pytest_cache/v
.worktrees
.worktrees/codex-architecture-consolidation
FastWrite
FastWrite/.cursor
FastWrite/.github
FastWrite/demo
FastWrite/docs
FastWrite/projs
FastWrite/release
FastWrite/scripts
FastWrite/src
FastWrite/web
artifacts
artifacts/architecture-guard-pr-rehearsal
artifacts/architecture-guard-pr-rehearsal-branch-doc
artifacts/architecture-guard-pr-rehearsal-closed-loop
artifacts/architecture-guard-pr-rehearsal-latest
artifacts/monthly-gate-failure-drill-2026-03
config
data
data/evaluation
data/inputs
data/kb
data/knowledge_bases
data/logs
data/metrics
data/notebooklm
data/notebooks
data/sessions
data/test_tmp
data/uploads
docs
docs/assets
docs/upgrade
scripts
skills
skills/experiment-compare
skills/innovation-summary
skills/paper-summary
skills/research-gaps
src
src/__pycache__
src/agent_runtime
src/agent_workflows
src/agents
src/api
src/compat
src/evaluation
src/knowledge
src/orchestrator
src/parsing
src/processing
src/rag
src/retrieval
src/services
src/session
src/shared_capabilities
src/skills
tests
tests/__pycache__
web
web/.next-playwright
web/e2e
web/public
web/src
web/test-results
```

## Runtime Chain (high-level)

- 1) start_dev.sh -> FastAPI(5001) + Next.js(3000) + FastWrite API(3003) + FastWrite UI(3002)
- 2) web/src/app/api/[...path]/route.ts -> proxy /api/* to 127.0.0.1:5001
- 3) src/api/main.py -> include routers(chat/knowledge/notebook/co_writer/retrieval/...)
- 4) src/api/routers/chat.py -> orchestrator facade -> agent runtime -> retrieval/llm/session persistence
- 5) docs/upgrade/repo-structure-overview.md -> repository-level map
- 6) docs/upgrade/architecture.md -> deep-dive for api/chat

## Anchor Check
OK  src/api/main.py :: app.include_router(chat.router
OK  src/api/routers/chat.py :: async def chat_stream(
OK  src/orchestrator/service.py :: def stream_run(
OK  src/agent_runtime/runtime.py :: def _retrieve_content_bundle(
OK  src/retrieval/hybrid.py :: def retrieve(
OK  src/services/llm/client.py :: def chat_stream(
OK  src/session/manager.py :: def save(

done
