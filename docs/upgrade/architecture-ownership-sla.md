# Architecture Ownership & SLA

> 目标：把“文档-代码同步”从个人习惯升级为可追责的团队治理机制。

## 1) 关键模块 Owner

| Module | Scope | Primary Owner | Backup Owner |
|---|---|---|---|
| `src/api/routers/chat.py` | chat / chat_stream 入口、异常与幂等控制 | Backend Oncall | Platform Oncall |
| `src/orchestrator/*` | 编排状态机、阶段事件流 | Agent Platform | Backend Oncall |
| `src/retrieval/*` + `src/rag/*` | 检索与生成链路、证据质量 | Retrieval Owner | Agent Platform |
| `src/services/llm/*` | 模型调用与 provider 兼容层 | LLM Infra Owner | Backend Oncall |
| `docs/upgrade/architecture.md` | `api/chat` 深挖文档 | Architecture Steward | Backend Oncall |
| `.github/workflows/quality-gate.yml` | pre-merge 架构与依赖守卫门禁 | DevEx Owner | Architecture Steward |

## 2) SLA 定义

| SLA ID | Target | SLO |
|---|---|---|
| SLA-ARCH-UPDATE | 关键运行链路变更后的文档同步 | `T+1` 工作日内更新 `architecture.md`/相关升级文档 |
| SLA-ARCH-GUARD | pre-merge 门禁失败响应 | `4h` 内完成 owner 响应并给出处理路径 |
| SLA-DRIFT-BOARD | 结构漂移看板刷新 | 每次月度演练必须产出最新 dashboard artifact |
| SLA-MONTHLY-DRILL | 月度失败演练与复盘 | 每月 1 次；失败演练后 `24h` 内补充复盘文档 |

## 3) 触发规则（什么时候必须更新文档）

- 修改 `src/api/routers/chat.py` 的请求入口、异常处理、重试/降级策略。
- 修改 `src/orchestrator/service.py` 的阶段顺序、事件契约、重试逻辑。
- 修改 `src/retrieval/*`、`src/services/llm/*` 导致依赖关系/调用关系变化。
- 修改 CI 守卫脚本或 baseline 策略。

## 4) 执行入口

- PR Checklist：`.github/pull_request_template.md`
- pre-merge guard：`.github/workflows/quality-gate.yml`
- 月度 drill：`.github/workflows/architecture-guard-monthly.yml`
- 漂移看板生成：`scripts/generate_structure_drift_dashboard.sh`
