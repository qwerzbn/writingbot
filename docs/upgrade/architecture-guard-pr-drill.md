# Architecture Guard PR Drill

## Purpose

验证 `architecture-guard` 在 pre-merge 场景中的三个点：

1. 失败阻断（job fail）
2. 日志可读性（summary + artifact）
3. 告警输出（`::error` / `::notice`）

## Preconditions

- CI workflow: `.github/workflows/quality-gate.yml`
- Monthly drill workflow: `.github/workflows/architecture-guard-monthly.yml`
- PR template checklist: `.github/pull_request_template.md`
- Ownership & SLA: `docs/upgrade/architecture-ownership-sla.md`
- Guard scripts:
  - `scripts/verify_architecture_chat_refs.sh`
  - `scripts/print_repo_structure.sh`
  - `scripts/generate_module_dependency_graph.py`
  - `scripts/simulate_arch_guard_ci.sh`
  - `scripts/simulate_dependency_guard_ci.sh`
  - `scripts/rehearse_arch_guard_pr.sh`

## Drill Modes

### A) Real PR Drill (recommended)

1. 新建分支并故意制造锚点不一致（例如移除 `docs/upgrade/architecture.md` 中某个 `src/...` 文件引用）。
2. 提交并发起 PR。
3. 观察 `Quality Gate / Architecture Guard`：
   - 预期失败（阻断合并）
   - 日志中可见 `FAIL ...` 和 `::error title=Architecture Guard::...`
4. 检查 artifacts：
   - `architecture-guard.log`
   - （若前置步骤通过）`repo-structure-snapshot.md`

### B) Tagged PR Drill (optional)

1. PR 标题加前缀：`[arch-drill] ...`
2. 触发 `Architecture Guard Drill` job（模拟成功+失败路径）。
3. 预期：
   - job 通过（因为脚本内部同时验证成功与失败分支，最终应 `passed`）
   - Step Summary 展示 drill 日志尾部
   - artifact: `architecture-guard-drill.log`

### C) Local Equivalent Drill

```bash
bash scripts/simulate_arch_guard_ci.sh
bash scripts/simulate_dependency_guard_ci.sh
bash scripts/simulate_full_guard_ci.sh
```

预期输出包含：

- `success path notice verified`
- `failure path error annotation verified`
- `passed`
- `failure path error annotation verified`（dependency guard）

### D) Local PR-Rehearsal Wrapper (artifact-friendly)

```bash
bash scripts/rehearse_arch_guard_pr.sh
```

输出目录默认在 `artifacts/architecture-guard-pr-rehearsal/`，包含：

- `repo-structure-snapshot.md`
- `verify-success.log`
- `verify-failure.log`
- `simulate.log`
- `summary.md`

### E) Monthly Drill (scheduled)

- Trigger: 每月 UTC `03:00`（每月 1 日），或手动触发 `workflow_dispatch`
- Workflow: `.github/workflows/architecture-guard-monthly.yml`
- 核验点：
  - 失败分支必须出现 `failure_exit_code: 1`
  - 成功分支必须包含 `::notice`
  - 失败分支必须包含 `::error`
  - 依赖守卫演练必须包含 `simulate-dep-guard` 成功/失败路径日志
  - 必须产出结构漂移看板：`artifacts/structure-drift-dashboard.md`
  - 必须补充月度失败演练复盘文档（按当月命名）
  - `summary.md` 与 run 日志应上传为 artifact

## Readability Checklist

- 失败日志包含：
  - `FAIL ...`
  - `summary: passed=... failed=... total=...`
  - `::error title=Architecture Guard::...`
- 成功日志包含：
  - `passed`
  - `summary: passed=... failed=0 total=...`
  - `::notice title=Architecture Guard::...`

## Latest Local Drill Evidence

- `docs/upgrade/architecture-guard-drill-report.md`
