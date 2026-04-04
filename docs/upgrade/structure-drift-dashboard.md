# Structure Drift Dashboard

Generated at: 2026-03-16 18:22:57 +0800

## Guard Health

| Check | Status | Exit Code |
|---|---|---:|
| Architecture anchor guard | PASS | 0 |
| Dependency cycle guard | PASS | 0 |

## Cycle Metrics

| Metric | Value |
|---|---:|
| Detected cycle SCC | 1 |
| Baseline cycle SCC | 1 |
| New cycle SCC | 0 |
| Resolved cycle SCC | 0 |

## Drill Status

- Overall: `GREEN`
- Latest drill summary: `artifacts/monthly-gate-failure-drill-2026-03/summary.md`
- Latest drill failure_exit_code: `1`

## Logs (tail)

### Architecture Guard

```text
[verify-arch-chat] validating code anchors
[verify-arch-chat] arch_doc=docs/upgrade/architecture.md
[verify-arch-chat] total_checks=11
[verify-arch-chat] OK chat router mounted
[verify-arch-chat] OK chat stream entry
[verify-arch-chat] OK chat stream worker
[verify-arch-chat] OK orchestrator run stream
[verify-arch-chat] OK orchestrator retrieve stage
[verify-arch-chat] OK hybrid retrieval fan-out
[verify-arch-chat] OK vector search call
[verify-arch-chat] OK skills registry resolution
[verify-arch-chat] OK skills runtime execution
[verify-arch-chat] OK llm streaming call
[verify-arch-chat] OK session persistence
[verify-arch-chat] passed
[verify-arch-chat] summary: passed=11 failed=0 total=11
```

### Dependency Guard

```text
[dep-guard] output=/private/var/folders/6x/r1zsj0h94kd1s9cgmyh88pt40000gn/T/tmp.zlyS9hpQCX/module-dependency-graph.md
[dep-guard] packages=13 edges=25
[dep-guard] summary: detected=1 baseline=1 new=0 resolved=0
[dep-guard] KNOWN rag <-> retrieval <-> services
```
