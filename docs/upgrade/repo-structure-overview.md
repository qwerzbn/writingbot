# WritingBot Repository Structure Overview

## 1) Scope

本文档给出仓库级结构总览（目录层 + 运行时主链路），用于快速定位：

- 代码放在哪里
- 服务如何连起来
- 哪些文档覆盖了更深层细节

## 2) Directory Layer (2-3 Levels)

```text
writingbot/
├─ src/                        # 主 Python 后端
│  ├─ api/                     # FastAPI 入口与路由注册
│  │  └─ routers/              # chat/knowledge/notebook/research/... 路由
│  ├─ orchestrator/            # 多阶段编排（plan/retrieve/synthesize/critique/finalize）
│  ├─ retrieval/               # 混合检索（vector + BM25 + graph）
│  ├─ rag/                     # RAG pipeline 与组件
│  ├─ knowledge/               # KB 管理与向量库接口
│  ├─ session/                 # 会话 JSONL 持久化
│  ├─ services/                # LLM/config/prompt 服务层
│  ├─ agents/                  # research/co_writer/chat agent
│  └─ skills/                  # skills registry/runtime
├─ web/                        # 主前端（Next.js）
│  ├─ src/app/                 # chat/knowledge/notebook/research/settings 页面
│  ├─ src/components/          # 组件层
│  └─ src/lib/                 # API 调用与流式处理工具
├─ FastWrite/                  # LaTeX 子项目（独立前后端）
│  ├─ src/                     # Bun API
│  └─ web/                     # Vite/React UI
├─ open-notebook/              # 独立上游子项目目录（默认不在主启动链路）
├─ config/                     # YAML 配置
├─ data/                       # 运行态数据（knowledge_bases/sessions/metrics/uploads）
├─ docs/upgrade/               # 升级、架构、演示、排练文档
├─ scripts/                    # 质量门禁与校验脚本
├─ skills/                     # 业务技能包（paper-summary 等）
├─ tests/                      # 后端测试
├─ main.py                     # CLI 入口
├─ server.py                   # 旧 Flask 服务（兼容）
└─ start_dev.sh                # 本地一键启动
```

## 3) Core Responsibilities

| Directory | Responsibility |
|---|---|
| `src/api` | FastAPI app 与业务路由入口。 |
| `src/orchestrator` | 统一执行状态机与阶段化事件流。 |
| `src/retrieval` | 证据召回、融合、重排、上下文构建。 |
| `src/knowledge` | 向量存储、知识库实体管理。 |
| `src/services` | LLM 客户端、配置、提示词服务。 |
| `src/session` | 会话读写与 JSONL 落盘。 |
| `web` | 主业务 UI 与 `/api/*` 代理层。 |
| `FastWrite` | 论文编辑子系统，通过 bridge 与主后端交互。 |
| `data` | 系统运行数据与日志产物。 |
| `scripts` | 测试门禁/发布门禁/架构漂移校验。 |

## 4) Runtime Layer (Repository-Level)

```mermaid
flowchart LR
  USER[Browser User]
  WEB[web Next.js]
  PROXY[web/src/app/api/[...path]/route.ts]
  API[src/api/main.py]
  ROUTERS[src/api/routers/*]
  ORCH[src/orchestrator/service.py]
  RET[src/retrieval/*]
  LLM[src/services/llm/*]
  SESS[src/session/manager.py]
  KB[data/knowledge_bases/*]
  FW[FastWrite UI/API]
  BRIDGE[src/api/routers/fastwrite_bridge.py]

  USER --> WEB --> PROXY --> API --> ROUTERS
  ROUTERS --> ORCH
  ORCH --> RET --> KB
  ORCH --> LLM
  ROUTERS --> SESS
  FW --> BRIDGE --> ROUTERS
```

## 5) Main Entrypoints and Wiring

1. `start_dev.sh` 启动 4 个服务：
   - WritingBot FastAPI（5001）
   - WritingBot Next.js（3000）
   - FastWrite API（3003）
   - FastWrite UI（3002）
2. `src/api/main.py` 统一注册业务路由。
3. `web/src/app/api/[...path]/route.ts` 将浏览器 `/api/*` 转发到后端 `127.0.0.1:5001`。
4. `main.py` 提供 CLI 模式（与 Web 并行存在）。

## 6) Relationship with `architecture.md`

- `docs/upgrade/architecture.md` 已包含目录层示意，但其**运行时细化目前重点覆盖 `api/chat` 子模块**（调用流、时序节点、异常分支、漂移校验）。
- 本文档负责仓库级全局视图；`architecture.md` 负责 `api/chat` 深挖视图。

## 7) Snapshot Command

可通过下面脚本快速生成当前仓库结构快照并检查关键锚点：

```bash
bash scripts/print_repo_structure.sh
```

输出可直接粘贴到 Markdown 文档时，可使用：

```bash
bash scripts/print_repo_structure.sh --markdown
```

按场景裁剪视图时，可使用：

```bash
# 只看顶层目录，并隐藏 open-notebook 子树
bash scripts/print_repo_structure.sh --depth 1 --exclude-open-notebook
```

生成并落盘到文档文件（供评审直接查看）：

```bash
bash scripts/print_repo_structure.sh --markdown > docs/upgrade/repo-structure-snapshot.md
```
