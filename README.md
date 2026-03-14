# WritingBot 📚

> Multi-Agent 学术论文写作助手 —— 基于 RAG 的智能文献问答、协同写作与 LaTeX 编辑平台

## ✨ 功能特性

- **📖 知识库管理** — 导入 PDF 文献，自动解析、分块、向量化存储，支持多知识库
- **💬 智能问答** — 基于 RAG（检索增强生成）的文献问答，支持实时流式输出与来源引用
- **📝 笔记本** — 结构化笔记管理，关联知识库内容
- **🔬 深度研究** — 多轮自主 Agent 深度调研模式
- **✍️ 协同写作** — AI 辅助的论文撰写功能
- **📄 FastWrite** — 集成 LaTeX 编辑器，支持 Section/Paragraph/Sentence 视图与 AI 润色
- **⚙️ 灵活配置** — 支持 Ollama / OpenAI / DeepSeek 等多种 LLM 和 Embedding 模型

## 🏗️ 系统架构

```
WritingBot/
├── src/                    # Python 后端源码
│   ├── api/                # FastAPI 路由（知识库、对话、笔记、研究等）
│   ├── agents/             # Multi-Agent 系统（Chat / Research / Co-Writer）
│   ├── rag/                # RAG 引擎 & Pipeline
│   ├── knowledge/          # 知识库管理 & ChromaDB 向量存储
│   ├── parsing/            # PDF 解析（PyMuPDF）
│   ├── processing/         # 语义分块
│   ├── services/           # LLM 客户端 & 配置管理
│   └── session/            # 会话管理
├── web/                    # Next.js 前端（React + TailwindCSS）
├── FastWrite/              # LaTeX 编辑器子项目（Bun + React + Vite）
├── config/                 # YAML 配置文件
├── data/                   # 运行时数据（知识库、会话）
├── main.py                 # CLI 交互入口
├── server.py               # 旧版 Flask 服务（已弃用）
└── start_dev.sh            # 一键启动脚本
```

## 🚀 快速开始

### 环境要求

- **Python 3.11**（推荐通过 Conda 管理）
- **Node.js ≥ 18** + npm
- **Bun**（用于 FastWrite 子项目）
- **Ollama**（可选，用于本地 LLM 推理）

### 1. 安装 Python 依赖

```bash
# 方式一：使用 Conda（推荐）
conda env create -f environment.yml
conda activate writingbot

# 方式二：使用 pip
pip install -r requirements.txt
```

### 2. 安装前端依赖

```bash
# WritingBot 前端
cd web && npm install && cd ..

# FastWrite 编辑器
cd FastWrite && bun install && cd ..
```

### 3. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，配置 LLM 提供商和 API Key
```

支持的 LLM 配置示例：

| 提供商 | LLM_PROVIDER | LLM_BASE_URL | LLM_MODEL |
|--------|-------------|--------------|-----------|
| Ollama（本地） | `ollama` | `http://localhost:11434/v1` | `qwen3:0.6b` |
| OpenAI | `openai` | `https://api.openai.com/v1` | `gpt-4o-mini` |
| DeepSeek | `openai` | `https://api.deepseek.com/v1` | `deepseek-chat` |

### 4. 一键启动

```bash
bash start_dev.sh
```

启动后可访问：

| 服务 | 地址 |
|------|------|
| WritingBot 前端 | http://localhost:3000 |
| WritingBot API | http://localhost:5001 |
| API 文档（Swagger） | http://localhost:5001/docs |
| FastWrite 编辑器 | http://localhost:3002 |
| FastWrite API | http://localhost:3003 |

## 📖 使用指南

### 知识库管理

1. 进入「知识库」页面，点击 **创建知识库**
2. 上传 PDF 文献，系统自动完成：解析 → 语义分块 → 向量化存储
3. 支持选择不同的 Embedding 模型（本地 Sentence-Transformers / Ollama / OpenAI）

### 智能问答

1. 进入「聊天」页面，选择目标知识库
2. 输入问题，AI 基于文献内容提供回答，附带来源引用
3. 支持多轮对话，自动保存历史

### LaTeX 编辑（FastWrite）

1. 导入 LaTeX 项目
2. 选择 `.tex` 文件，切换 Section / Paragraph / Sentence 视图
3. 使用 AI 诊断、润色、快速修复功能
4. 查看词级别 Diff，选择接受或拒绝修改

## 🛠️ 技术栈

| 层级 | 技术 |
|------|------|
| 后端框架 | FastAPI + Uvicorn |
| 向量数据库 | ChromaDB |
| Embedding 模型 | Sentence-Transformers / Ollama / OpenAI |
| PDF 解析 | PyMuPDF |
| LLM 集成 | OpenAI SDK（兼容 Ollama、DeepSeek 等） |
| 前端框架 | Next.js 16 + React 19 |
| 前端样式 | TailwindCSS 4 |
| LaTeX 编辑器 | Bun + Vite + React |

## 📁 CLI 模式

除 Web 界面外，也支持命令行使用：

```bash
python main.py
```

可用命令：
- `/ingest <path>` — 导入 PDF 文件
- `/stats` — 查看知识库统计
- `/clear` — 清除对话历史
- `/quit` — 退出

## ✅ 质量门禁

本项目提供企业级基础门禁：

- CI 工作流：`.github/workflows/quality-gate.yml`
- 本地一键门禁脚本：`scripts/quality_gate.sh`

本地执行：

```bash
bash scripts/quality_gate.sh
```

## 📄 License

MIT
