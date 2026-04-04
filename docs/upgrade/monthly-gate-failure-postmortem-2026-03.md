# Monthly Gate Failure Drill Postmortem (2026-03)

Generated at: 2026-03-16 18:19:34 +0800

## 1) Drill Scope

- Architecture guard failure branch（锚点缺失触发阻断 + `::error`）
- Dependency guard failure branch（模拟新增循环依赖触发阻断 + `::error`）
- Drift dashboard refresh

## 2) Evidence

- Architecture failure drill summary:
  - `artifacts/monthly-gate-failure-drill-2026-03/summary.md`
- Dependency guard drill:
  - `bash scripts/simulate_dependency_guard_ci.sh`（failure path verified）
- Drift dashboard:
  - `docs/upgrade/structure-drift-dashboard.md`

## 3) Timeline

1. 执行 `bash scripts/rehearse_arch_guard_pr.sh artifacts/monthly-gate-failure-drill-2026-03`
2. 执行 `bash scripts/simulate_dependency_guard_ci.sh`
3. 执行 `bash scripts/generate_structure_drift_dashboard.sh docs/upgrade/structure-drift-dashboard.md`
4. 复核输出：`failure_exit_code=1`、`::error`、`::notice`、看板状态 `GREEN`

## 4) Results

- 失败阻断：通过（failure branch 非零退出）
- 告警输出：通过（`::error title=Architecture Guard::...` / `::error title=Dependency Guard::...`）
- 日志可读性：通过（均包含 `summary: passed=... failed=... total=...`）
- 看板刷新：通过（已更新到最新演练）

## 5) Root Cause Category (Drill)

- 本次为“演练注入故障”，非真实生产缺陷。
- 架构守卫故障注入方式：文档锚点缺失。
- 依赖守卫故障注入方式：`--simulate-new-cycle` 注入新循环依赖 SCC。

## 6) Governance Actions

| Action | Owner | SLA | Status |
|---|---|---|---|
| 保持 `architecture-ownership-sla` 与实际负责人同步 | Architecture Steward | Monthly | Open |
| 月度演练后 24h 内更新复盘 | DevEx Owner | 24h | Done |
| 每次演练产出 drift dashboard artifact | DevEx Owner | Monthly | Done |
| 发现新增循环依赖时提供拆环计划 | Backend Oncall | 4h 响应 | Ready |

## 7) Follow-up Links

- `docs/upgrade/architecture-ownership-sla.md`
- `.github/workflows/architecture-guard-monthly.yml`
- `.github/pull_request_template.md`
