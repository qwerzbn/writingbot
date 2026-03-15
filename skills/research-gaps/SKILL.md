---
name: research-gaps
description: Use this skill when the user asks for weaknesses, limitations, validity threats, and future work opportunities in paper analysis.
metadata:
  id: /research-gaps
  domain: research
  label_cn: 研究不足
  description_cn: 指出局限、潜在偏差、外推风险与后续改进方向。
  enabled: true
  requires_kb: false
  critical: false
  timeout_ms: 2000
  order: 40
  instruction: 分析论文局限、偏差风险和外推边界，并给出短中长期可执行改进路线。
---

# 研究不足

当用户要求“局限性分析/问题诊断/未来工作方向”时使用。

## 输出要求

- 仅使用 Markdown，禁止输出 HTML 标签。
- 不泛泛而谈，要关联任务设定、数据分布、评估方案。
- 每条不足给出“影响 + 可执行改进建议”。

## 输出模板

### 1. 主要局限
- 局限点：具体描述。
- 影响范围：对结论可靠性或可迁移性的影响。

### 2. 潜在偏差与风险
- 数据偏差、指标偏差、实现依赖、复现风险。

### 3. 外推性判断
- 适用场景与不适用场景。

### 4. 改进路线图
- 短期可做：补实验、补消融、补对照。
- 中期可做：方法改进、评估重构。
- 长期可做：新问题定义或新基准。
