# WritingBot

WritingBot 是一个面向学术写作场景的本地协同写作与知识库系统。当前版本以 FastAPI 后端、Next.js 前端、RAG 检索链路和统一 Agent Runtime 为核心，支持文献知识库、智能问答、研究笔记、协同写作、运行诊断与评估报告。

![项目总览截图](docs/assets/dashboard-overview.png)

## 当前进度

- 主后端已切换到 FastAPI，统一从 `src/api/main.py` 注册知识库、聊天、笔记本、协同写作、检索、编排、评估、设置和技能接口。
- Agent 运行时正在收敛到 `src/agent_runtime/`，当前以 typed state、运行记录、事件流和内容工作流作为主链路。
- 聊天与协同写作能力由 `ContentAgent` 和共享能力层承接，旧的 `ChatAgent` / `CoWriterAgent` import path 保留为兼容适配器。
- 研究技能注册已经从历史技能包向 Anthropic-style skill folder 结构迁移；当前 `config/skills.yaml` 为空列表，后续技能应按新的注册约束补回。
- 前端主站保留总览、知识库、智能问答、笔记本、协同写作和设置页面；旧研究页已从主导航移除。
- 证据链能力仍是核心约束：检索结果、图表资产、引用绑定、推理标记、评估指标和运行日志用于支撑可追溯输出。

## 功能模块

| 模块 | 说明 |
|---|---|
| 知识库 | 创建知识库、上传 PDF、解析文本与图表资产、构建向量索引。 |
| 智能问答 | 基于知识库检索结果生成回答，支持流式输出、来源引用、图表证据补充。 |
| 笔记本 | 管理研究资料、笔记、工作区输出、来源导入和相关内容发现。 |
| 协同写作 | 提供 LaTeX 论文编辑、文本改写、扩写、缩写、润色和证据辅助写作入口。 |
| Agent Runtime | 统一运行记录、事件流、状态模型、内容生成和评估指标。 |
| 评估与诊断 | 输出运行指标、评估报告、质量门禁和架构演练材料。 |

## 技术栈

| 层级 | 当前选择 |
|---|---|
| 后端 | Python 3.11+、FastAPI、Uvicorn、Pydantic |
| LLM 接入 | OpenAI SDK 兼容接口，可接 Ollama、OpenAI-compatible 服务、DeepSeek 等 |
| RAG | PyMuPDF、Sentence-Transformers / Ollama / OpenAI Embedding、ChromaDB、混合检索 |
| 前端 | Next.js 16、React 19、TypeScript、Tailwind CSS 4、Radix UI、lucide-react |
| 协同写作模块 | Bun、Vite、React、独立编辑器服务，通过主站桥接入口集成 |
| 测试与质量 | pytest、Playwright、项目脚本化质量门禁 |

更完整的技术说明见 [docs/technical-selection.md](docs/technical-selection.md)。

## 项目结构

```text
writingbot/
├── src/
│   ├── api/                  # FastAPI 应用与业务路由
│   ├── agent_runtime/        # 统一 Agent Runtime、typed state、事件与运行存储
│   ├── agent_workflows/      # 内容类工作流
│   ├── agents/               # 对外保留的 Agent import path 与兼容适配
│   ├── compat/               # 旧接口适配器
│   ├── knowledge/            # 知识库与向量库管理
│   ├── rag/                  # RAG pipeline 与组件
│   ├── retrieval/            # 混合检索与索引访问
│   ├── services/             # 配置、LLM、Notebook、Prompt 服务
│   ├── shared_capabilities/  # 检索、提示词、渲染、证据、校验等共享能力
│   └── skills/               # 技能注册与运行
├── web/                      # Next.js 主前端
├── config/                   # YAML 配置
├── data/                     # 本地运行数据
├── docs/                     # 项目文档
├── scripts/                  # 启动、演练、质量门禁脚本
└── tests/                    # 后端测试
```

更详细的架构图见 [docs/project-architecture.md](docs/project-architecture.md)。

## 快速开始

### 环境要求

- Python 3.11+
- Node.js 18+ 与 npm
- Bun：仅在启用协同写作模块时需要
- Ollama 或 OpenAI-compatible LLM 服务：用于本地/远程模型推理

### 安装依赖

```bash
pip install -r requirements.txt
cd web && npm install
```

如需启用协同写作模块，请额外安装 Bun 并安装该模块依赖。

### 配置环境变量

```bash
cp .env.example .env
```

常用 LLM 配置：

| 提供商 | `LLM_PROVIDER` | `LLM_BASE_URL` | `LLM_MODEL` |
|---|---|---|---|
| Ollama | `ollama` | `http://localhost:11434/v1` | `qwen3:0.6b` |
| OpenAI | `openai` | `https://api.openai.com/v1` | `gpt-4o-mini` |
| DeepSeek | `openai` | `https://api.deepseek.com/v1` | `deepseek-chat` |

### 启动开发环境

```bash
bash start_dev.sh
```

默认服务：

| 服务 | 地址 |
|---|---|
| 主前端 | http://localhost:3000 |
| 后端 API | http://localhost:5001 |
| API 文档 | http://localhost:5001/docs |
| 协同写作模块 UI | http://localhost:3002 |
| 协同写作模块 API | http://localhost:3003 |

也可以单独启动主前端：

```bash
cd web
npm run dev -- --hostname 127.0.0.1 --port 3000
```

## API 入口

| 路由组 | 说明 |
|---|---|
| `/api/kbs` | 知识库、文件、图表资产、索引修复 |
| `/api/chat` | 聊天、流式问答、会话管理、运行指标 |
| `/api/notebooks` | 笔记本、来源、笔记、工作区、事件、洞察 |
| `/api/co-writer` | 协同写作证据检索与文本编辑 |
| `/api/orchestrator` | 运行创建、查询和事件流 |
| `/api/retrieval` | 混合检索调试入口 |
| `/api/evaluation` | 评估任务与报告 |
| `/api/settings` | LLM 配置读取、更新和连通性测试 |
| `/api/skills` | 技能注册信息 |

## 文档导航

- [docs/README.md](docs/README.md)：项目文档索引
- [docs/technical-selection.md](docs/technical-selection.md)：技术选型
- [docs/project-architecture.md](docs/project-architecture.md)：项目架构
- [docs/agent-design.md](docs/agent-design.md)：Agent 设计
- [docs/project-screenshots.md](docs/project-screenshots.md)：项目截图
- [docs/upgrade/](docs/upgrade/)：历史升级、演练和架构守卫材料

## 测试与质量门禁

```bash
pytest
cd web && npm run lint
```

项目也保留脚本化门禁：

```bash
bash scripts/quality_gate.sh
```

## 许可证

MIT
