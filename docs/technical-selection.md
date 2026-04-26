# 技术选型

## 选型目标

WritingBot 的技术选型服务于三个目标：本地可运行、证据可追溯、模块可收敛。系统不追求复杂平台化，而是优先保证学术写作流程中的文献导入、检索问答、笔记沉淀和协同写作能够稳定串起来。

## 后端

| 技术 | 用途 | 选择原因 |
|---|---|---|
| Python 3.11+ | 主后端语言 | 生态适合 RAG、PDF 处理、模型接入和测试。 |
| FastAPI | HTTP API | 类型友好，天然支持 OpenAPI 文档，适合拆分多个业务路由。 |
| Uvicorn | ASGI 服务 | 与 FastAPI 配套，开发环境启动简单。 |
| Pydantic | typed state 与请求响应模型 | Agent Runtime 需要清晰状态边界和可序列化结构。 |
| PyYAML / python-dotenv | 配置读取 | 支持 YAML 项目配置和本地环境变量。 |

## 检索与知识库

| 技术 | 用途 | 选择原因 |
|---|---|---|
| PyMuPDF | PDF 文本与页面内容解析 | 对学术 PDF 解析直接，便于提取页码、文本块和图表线索。 |
| ChromaDB | 向量存储 | 本地部署成本低，适合知识库原型和单机演示。 |
| Sentence-Transformers | 本地 embedding | 支持离线向量化，降低演示环境对外部服务依赖。 |
| Ollama / OpenAI-compatible embedding | 可选 embedding | 允许按硬件和模型资源切换。 |
| 混合检索 | vector + BM25 + graph 召回融合 | 提高论文问答中术语、标题、概念和证据片段的命中率。 |

## LLM 接入

系统通过 OpenAI SDK 兼容接口接入模型服务。这样可以在 Ollama、本地代理、OpenAI-compatible 云服务和 DeepSeek 等服务之间切换，而不需要在业务层绑定某一家供应商。

当前配置重点：

- `LLM_PROVIDER`：模型提供方标识。
- `LLM_BASE_URL`：OpenAI-compatible 接口地址。
- `LLM_MODEL`：聊天或写作模型。
- Embedding 配置：由知识库导入流程按 provider/model 选择。

## 前端

| 技术 | 用途 | 选择原因 |
|---|---|---|
| Next.js 16 | 主前端框架 | 文件路由和 API proxy 简洁，适合主站多页面组织。 |
| React 19 | UI 组件 | 与 Next.js 配套，方便组织知识库、聊天、笔记本和写作页面。 |
| TypeScript | 前端类型 | 降低 API payload、流式事件和状态 store 的维护成本。 |
| Tailwind CSS 4 | 样式 | 快速构建统一界面，便于局部迭代。 |
| Radix UI | 对话框、菜单、Tabs、Tooltip 等 | 使用成熟无障碍组件，减少手写交互细节。 |
| lucide-react | 图标 | 与当前侧边栏和按钮风格一致。 |
| Zustand | 局部状态 | 适合笔记本工作区这类轻量持久化 UI 状态。 |

## 协同写作模块

协同写作模块采用 Bun、Vite 和 React 组成独立编辑器服务，并通过主站页面和后端桥接入口集成。这样做的好处是编辑器可以保持较快的前端迭代速度，同时主系统仍然把知识库、证据和运行记录掌握在统一后端内。

该模块在文档中被视为项目内能力，不作为外部产品或第三方依赖描述。

## 质量与验证

| 工具 | 用途 |
|---|---|
| pytest | 后端单元测试与 API smoke 测试。 |
| Playwright | 前端端到端测试与截图生成。 |
| ESLint | 前端静态检查。 |
| 项目脚本 | 质量门禁、架构演练、结构快照和演示前检查。 |

## 当前取舍

- 保留一个主 FastAPI 后端，避免 Flask、脚本入口和多套服务长期并行扩张。
- 保留一个主 Next.js 前端，协同写作模块作为独立编辑器能力接入。
- Agent 侧优先收敛 typed state、事件流、运行存储和共享能力，再扩展更多 Agent 类型。
- RAG 与证据链优先保证可解释性，性能优化后置。
