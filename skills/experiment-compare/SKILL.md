---
name: experiment-compare
description: Use this skill when the user asks to compare experiments across papers or methods, especially datasets, metrics, baselines, and result differences.
metadata:
  id: /experiment-compare
  domain: research
  label_cn: 实验对比
  description_cn: 对比不同论文或方法在数据集、指标和结果上的差异。
  enabled: true
  requires_kb: false
  critical: false
  timeout_ms: 2000
  order: 20
  instruction: 比较不同论文或方法在数据集、指标、结果和成本上的差异，先给对比表再解释原因，并标注证据引用。
---

# 实验对比

当用户要求“方法A和B对比/多篇论文实验差异/结果差异原因”时使用。

## 输出要求

- 仅使用 Markdown，禁止输出 HTML 标签。
- 先给对比表，再给差异解释。
- 有证据必须标注引用 `[1][2]`，无证据需标注“（推断）”。

## 输出模板

### 1. 对比范围
- 对比对象与前提（任务、数据、版本）。

### 2. 关键对比表
| 维度 | 方法A | 方法B | 差异结论 |
| --- | --- | --- | --- |
| 数据集 |  |  |  |
| 指标 |  |  |  |
| 结果 |  |  |  |
| 资源成本 |  |  |  |

### 3. 差异原因分析
- 可能原因与证据链。

### 4. 选型建议
- 在不同约束（精度/成本/时延）下的推荐方案。
