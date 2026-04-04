# Architecture Guard PR Rehearsal Summary

- artifact_dir: `artifacts/architecture-guard-pr-rehearsal-closed-loop`
- failure_exit_code: `1`

## Success Path (tail)

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
::notice title=Architecture Guard::verify_architecture_chat_refs passed (11/11)
```

## Failure Path (tail)

```text
[verify-arch-chat] validating code anchors
[verify-arch-chat] arch_doc=/var/folders/6x/r1zsj0h94kd1s9cgmyh88pt40000gn/T/tmp.lzH4Wub3FV
[verify-arch-chat] total_checks=11
[verify-arch-chat] FAIL doc missing file reference: src/api/main.py (chat router mounted)
[verify-arch-chat] summary: passed=0 failed=1 total=11
::error title=Architecture Guard::doc missing file reference: src/api/main.py (chat router mounted)
```

## Simulation (tail)

```text
[simulate-arch-guard] success path
[simulate-arch-guard] success path notice verified
[simulate-arch-guard] failure path
[simulate-arch-guard] failure path error annotation verified
[simulate-arch-guard] passed
```
