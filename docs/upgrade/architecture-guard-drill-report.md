# Architecture Guard Drill Report

Generated on: 2026-03-16 17:27:14 +0800

## Commands

- `GITHUB_ACTIONS=true bash scripts/verify_architecture_chat_refs.sh`
- `ARCH_DOC_PATH=<tmp_bad_doc> GITHUB_ACTIONS=true bash scripts/verify_architecture_chat_refs.sh`
- `bash scripts/simulate_arch_guard_ci.sh`

## Exit Codes

- success path exit code: `0`
- failure path exit code: `1`
- simulation script exit code: `0`

## Success Path Log (excerpt)

```text
[verify-arch-chat] validating code anchors
[verify-arch-chat] arch_doc=docs/upgrade/architecture.md
[verify-arch-chat] total_checks=11
...
[verify-arch-chat] passed
[verify-arch-chat] summary: passed=11 failed=0 total=11
::notice title=Architecture Guard::verify_architecture_chat_refs passed (11/11)
```

## Failure Path Log (excerpt)

```text
[verify-arch-chat] validating code anchors
[verify-arch-chat] arch_doc=/tmp/<bad_doc>
[verify-arch-chat] total_checks=11
[verify-arch-chat] FAIL doc missing file reference: src/api/main.py (chat router mounted)
[verify-arch-chat] summary: passed=0 failed=1 total=11
::error title=Architecture Guard::doc missing file reference: src/api/main.py (chat router mounted)
```

## Simulation Script Log

```text
[simulate-arch-guard] success path
[simulate-arch-guard] success path notice verified
[simulate-arch-guard] failure path
[simulate-arch-guard] failure path error annotation verified
[simulate-arch-guard] passed
```

## Result

- Blocking behavior verified: failure path returned non-zero.
- Alert output verified: failure path emits `::error title=Architecture Guard::...`.
- Readability verified: both paths print summary line (`passed/failed/total`).

## Re-run (2026-03-16 17:37:10 +0800)

Commands re-executed in current follow-up:

- `bash scripts/verify_architecture_chat_refs.sh`
- `bash scripts/simulate_arch_guard_ci.sh`

Observed output highlights:

```text
[verify-arch-chat] summary: passed=11 failed=0 total=11
[simulate-arch-guard] success path notice verified
[simulate-arch-guard] failure path error annotation verified
[simulate-arch-guard] passed
```

## Re-run (2026-03-16 17:40:30 +0800)

Commands re-executed in current follow-up:

- `bash scripts/print_repo_structure.sh --markdown --exclude-open-notebook > docs/upgrade/repo-structure-snapshot.md`
- `bash scripts/verify_architecture_chat_refs.sh`
- `bash scripts/simulate_arch_guard_ci.sh`

Observed output highlights:

```text
[verify-arch-chat] summary: passed=11 failed=0 total=11
[simulate-arch-guard] success path notice verified
[simulate-arch-guard] failure path error annotation verified
[simulate-arch-guard] passed
```

## Re-run (2026-03-16 18:00:18 +0800)

Commands re-executed in current follow-up:

- `bash scripts/verify_architecture_chat_refs.sh`
- `bash scripts/rehearse_arch_guard_pr.sh artifacts/architecture-guard-pr-rehearsal-branch-doc`

Observed output highlights:

```text
[verify-arch-chat] summary: passed=11 failed=0 total=11
[arch-pr-rehearsal] artifact_dir=artifacts/architecture-guard-pr-rehearsal-branch-doc
[arch-pr-rehearsal] done
[arch-pr-rehearsal] summary=artifacts/architecture-guard-pr-rehearsal-branch-doc/summary.md
```

## Re-run (2026-03-16 18:03:22 +0800)

Commands re-executed in current follow-up:

- `bash scripts/verify_architecture_chat_refs.sh`
- `bash scripts/rehearse_arch_guard_pr.sh artifacts/architecture-guard-pr-rehearsal-closed-loop`

Observed output highlights:

```text
[verify-arch-chat] summary: passed=11 failed=0 total=11
[arch-pr-rehearsal] artifact_dir=artifacts/architecture-guard-pr-rehearsal-closed-loop
[arch-pr-rehearsal] done
[arch-pr-rehearsal] summary=artifacts/architecture-guard-pr-rehearsal-closed-loop/summary.md
```

## Re-run (2026-03-16 18:08:40 +0800)

Commands re-executed in current follow-up:

- `bash scripts/simulate_dependency_guard_ci.sh`
- `python scripts/generate_module_dependency_graph.py --output docs/upgrade/module-dependency-graph.md --baseline config/dependency-cycles-baseline.txt`

Observed output highlights:

```text
[simulate-dep-guard] success path verified
[simulate-dep-guard] failure path error annotation verified
[simulate-dep-guard] passed
[dep-guard] summary: detected=1 baseline=1 new=0 resolved=0
```
