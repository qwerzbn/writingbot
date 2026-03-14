# WritingBot 升级版彩排报告

更新时间：2026-03-13

## 已验证（通过）

- 后端核心模块可导入与编译：`python -m compileall src`
- 前端主站静态检查：`npm --prefix web run lint`
- 前端主站构建：`npm --prefix web run build`
- 新增与兼容测试：`pytest -q`（16 passed）
- 覆盖范围：
  - Orchestrator 状态机与 run store TTL
  - 混合检索融合、证据裁决、上下文预算裁剪
  - FastWrite handoff/callback token 校验与回填闭环
  - 旧 `/chat/stream`、`/research/stream`、`/co-writer/edit/stream` 兼容层与 `x-orchestrated: true`
  - 新 `/api/orchestrator/run`、`/api/orchestrator/stream/{run_id}`、`/api/retrieval/hybrid`、`/api/evaluation/*` smoke

## 风险与说明

- FastWrite 仓库内存在历史 TypeScript 类型问题，`bun run typecheck` 目前失败；本轮桥接接口已落地，但不建议将该命令作为当前发布阻断。
- 当前工作区仍存在历史改动与部分已跟踪 `.pyc` 文件变更，本报告未对其做回滚操作。

## 答辩现场建议执行顺序

1. 启动后端与主站前端。
2. 运行研究链路并生成含引用内容。
3. 发送至协同写作并展示证据绑定/“推断”标记。
4. 保存到笔记并展示证据视图（引用次数、最近使用、来源片段）。
5. 点击发送到 FastWrite，完成回填后展示主站内容更新。
6. 触发离线评测接口并展示报告闸门字段（`Citation Precision >= 0.85`、`Faithfulness >= 0.80`）。
