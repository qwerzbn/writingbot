---
name: innovation-summary
description: Use this skill when the user asks for innovation extraction, novelty points, and key differences against prior work.
metadata:
  id: /innovation-summary
  domain: research
  label_cn: 创新总结
  description_cn: 总结论文创新点以及与已有工作的关键区别。
  enabled: true
  requires_kb: false
  critical: false
  timeout_ms: 2000
  order: 30
  instruction: 提炼论文创新点并说明与已有工作的关键区别，区分证据支持结论与推断判断，给出可迁移建议。
---

# 创新总结

当用户要求“创新点总结/新颖性评估/和SOTA差异”时使用。

## 输出要求

- 仅使用 Markdown，禁止输出 HTML 标签。
- 先列创新点，再说明证据与边界。
- 结论必须区分“证据支持”与“推断判断”。

## 输出模板

### 1. 创新点清单
- 创新点1：一句话定义 + 价值。
- 创新点2：一句话定义 + 价值。

### 2. 与已有工作差异
- 与最接近方法的核心差别。
- 为什么这种差别带来性能或效率提升。

### 3. 证据支撑
- 哪些实验或消融支撑上述创新点。

### 4. 创新可信度评估
- 强证据创新 / 弱证据创新 / 可能营销表述。

### 5. 可迁移性建议
- 创新是否可复用到你的任务，迁移成本如何。
