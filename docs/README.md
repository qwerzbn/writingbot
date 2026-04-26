# WritingBot 项目文档

本目录整理当前项目进度下的核心说明文档。根目录 `README.md` 面向快速启动和项目总览；本目录文档面向技术答辩、后续维护和模块交接。

## 文档列表

| 文档 | 内容 |
|---|---|
| [technical-selection.md](technical-selection.md) | 后端、前端、RAG、LLM、协同写作模块、质量工具的技术选型说明。 |
| [project-architecture.md](project-architecture.md) | 当前项目架构、目录边界、运行链路和数据流。 |
| [agent-design.md](agent-design.md) | Agent Runtime、内容 Agent、兼容适配器、共享能力与证据校验设计。 |
| [project-screenshots.md](project-screenshots.md) | 当前主站截图和截图更新方式。 |
| [upgrade/](upgrade/) | 历史升级、演练、架构守卫和复盘资料。 |

## 当前文档口径

- 以当前工作区进度为准：主链路正在从多套历史 Agent 实现收敛到统一运行时。
- 以证据可追溯为核心：检索来源、图表资产、引用绑定、推理标记和评估指标都属于交付边界。
- 以协同写作为项目内模块描述：文档不把它包装成外部品牌或第三方产品。
- 以增量维护为原则：历史升级文档保留背景价值，新文档负责给出当前可读的主说明。
