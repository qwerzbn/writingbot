---
name: paper-summary
description: Use this skill when the user asks for a structured summary of one or more papers, including research question, method, experiment setup, findings, and limitations.
metadata:
  id: /paper-summary
  domain: research
  label_cn: 论文总结
  description_cn: 提炼研究问题、方法、实验设置与核心结论。
  enabled: true
  requires_kb: false
  critical: false
  timeout_ms: 2000
  order: 10
  instruction: 按论文粒度总结研究问题、方法、实验设置、核心结论与局限，使用 Markdown 结构化输出并优先给出证据引用。
---

# 论文总结

当用户要求“总结论文/快速读懂论文/提炼核心贡献”时使用。

## 输出要求

- 仅使用 Markdown，禁止输出 HTML 标签。
- 优先使用知识库证据，引用格式使用 `[1][2]`。
- 无证据结论必须标注“（推断）”。

## 输出模板

### 1. 研究问题
- 论文试图解决什么问题，为什么重要。

### 2. 方法与创新
- 方法框架与关键机制。
- 与已有工作的主要差异。

### 3. 实验设置
- 数据集、指标、基线、训练/评测设定。

### 4. 核心结果
- 主要结果与改进幅度。
- 稳健性或泛化结论。

### 5. 局限与风险
- 适用边界、潜在偏差、失败场景。

### 6. 给科研实践的建议
- 复现实验、选型、后续研究方向。
