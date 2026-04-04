---
name: innovation-summary
description: How to extract and summarize the novel contributions of a paper. Make sure to use this skill whenever the user asks for innovation extraction, novelty points, asks "what's new here", or wants to know the key differences between this paper and prior SOTA (State Of The Art) works.
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

# 创新总结 (Innovation Summary)

This skill helps the user quickly identify the core novelties of a paper, assessing what makes it unique and how it differentiates itself from the State of The Art (SOTA).

## Output Guidelines & Philosophy

When formatting your answer, please follow these guidelines to provide an objective and well-structured summary:

- **Format in Markdown:** Use Markdown exclusively for styling (bolding, lists, etc.) to ensure the response displays properly in the frontend. Do not use raw HTML.
- **Respond completely in Chinese (中文):** Even though these instructions and section titles are written in English (to help you understand the logical structure better), your FINAL output MUST be written entirely in Chinese. You may keep English technical terms if appropriate.
- **Differentiate Claims from Evidence:** It is crucial for researchers to know if a claim is backed by strong empirical evidence or if it's merely a theoretical proposal by the authors. When summarizing, clearly distinguish between "Evidence-supported" innovations and "Inferred" or "Author-claimed" points.
- **Maintain Objectivity:** Beware of marketing language from the paper. Try to distill the actual technical contribution rather than just repeating the authors' hyped descriptions.

## Expected Report Structure

ALWAYS structure your summary using the following list:

### 1. 创新点清单 (List of Innovations)
- **Innovation 1:** A one-sentence definition + its core value proposition.
- **Innovation 2:** A one-sentence definition + its core value proposition.

### 2. 与已有工作差异 (Differences from Prior Work)
- What is the core difference compared to the most closely related work (e.g., previous SOTA)?
- Why does this difference lead to improvements in performance, efficiency, or capability?

### 3. 证据支撑 (Supporting Evidence)
- What specific experiments, ablation studies, or theoretical proofs in the paper support the claimed innovations?

### 4. 创新可信度评估 (Credibility Assessment)
- Classify the innovations as: Strong Evidence / Weak Evidence / Potential Marketing Claim. Explain your reasoning briefly.

### 5. 可迁移性建议 (Transferability Suggestions)
- Could this innovation be reused in other tasks or domains? What would be the cost or difficulty of adapting it?

## 参考样例 (Example Output)

Here is a brief example of the innovation listing:

### 1. 创新点清单
- **动态深度路由 (Dynamic Depth Routing):** 允许模型在推理时跳过部分 Transformer 层。**价值:** 大幅降低了简单 tokens 的计算延迟，整体 FLOPs 减少 30% [1]。
- **语义感知词表重构:** 移除了低频死词。**价值:** 减轻了词表 Embedding 层的显存占用。

### 4. 创新可信度评估
- **强证据创新:** 动态深度路由有长达 3 页的消融实验，且在 5 个下游任务上均有一致的加速比。
- **可能营销表述:** “人类水平的常识推理”缺乏足够严谨的测试集支撑（推断：大部分基准测试已经过拟合）。
