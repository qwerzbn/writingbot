# WritingBot Review Split Plan

更新时间：2026-05-11

## 1. Web / 文档 / 守卫

优先审这组，因为它直接影响 CI、质量门、答辩口径和报告一致性。

- 确认 FastWrite 作为独立嵌入模块：CI、`scripts/quality_gate.sh`、`scripts/release_gate.sh`、`/api/fastwrite/health`、`/api/health` 口径一致。
- 确认 FastWrite 缺失时只记录 degraded，不阻塞主项目聊天、Notebook、主站构建。
- 确认文档和脚本不再引用旧 Research SSE 路由字面量。
- 确认 demo readiness 使用 `single_pass=1`，不会因 Notebook SSE padding 误判失败。

## 2. Runtime / RAG

第二组审答辩主链路：聊天流、统一 Runtime、检索、证据和协同写作桥接。

- `/api/chat/stream` 与 `chat_research` 走统一 Runtime，流式 chunk 由 ContentAgent stream 产生。
- Hybrid retrieval 输出 `vector_ms`、`bm25_ms`、`graph_ms`、`rerank_ms`、`judge_ms`、`context_ms`。
- 本地 BM25/graph 索引读缓存、VectorStore query embedding 缓存用于降低重复检索延迟。
- Evidence judge 结合 rerank/fusion 分数与 query overlap，提高相关证据排序。
- co-writer/FastWrite handoff/callback token 闭环保持独立测试。

## 3. 数据 / Skills / 历史运行态文件

最后单独审，避免误删或误还原。

- 区分必须保留的数据基线、可清理的运行产物、以及不应继续跟踪的缓存/临时文件。
- `data/knowledge_bases` 与 `data/notebooks` 是正式布局；`data/kb` 和 `data/notebooklm` 只作为历史兼容或迁移输入。
- Skills 当前默认为空列表；UI 不展示无效技能选择。是否恢复具体 skills 另开任务。
