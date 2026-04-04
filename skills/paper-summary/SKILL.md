---
name: paper-summary
description: How to provide a structured and comprehensive summary of one or more academic papers. Make sure to use this skill whenever the user asks to summarize a paper, quickly understand research, extract core contributions, or asks for a breakdown of a paper's research question, method, experiment setup, findings, and limitations.
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

# 论文总结 (Paper Summary)

This skill is designed to extract and structure the core information from academic papers when the user wants to quickly digest them.

## Output Guidelines & Philosophy

When formatting your answer, please keep the following guidelines in mind so the user gets the most reliable and readable output:

- **Format in Markdown:** Exclusively use Markdown for formatting (e.g., headings, lists, bold text). Avoid HTML tags, as the frontend rendering engine may not parse raw HTML correctly and it helps keep the output clean.
- **Respond completely in Chinese (中文):** Even though these instructions and section titles are written in English (to help you understand the logical structure better), your FINAL output MUST be written entirely in Chinese. You may keep English technical terms if appropriate.
- **Provide Evidence:** Academic writing is about rigor. Whenever possible, base your summaries on direct evidence from the provided knowledge base or document, and cite your sources using bracketed numbers like `[1]`, `[2]`.
- **Distinguish Facts from Inferences:** If you are drawing a conclusion or extrapolating a thought that is not explicitly stated in the source text, politely indicate this by appending "（推断）" (Inference) so the user knows this is an AI-generated insight rather than a direct author claim.

## Expected Report Structure

ALWAYS use the following structure to organize your summary. This consistency helps the user scan and compare multiple papers easily.

### 1. 研究问题 (Research Question)
- What specific problem is the paper trying to solve, and why is this problem important?

### 2. 方法与创新 (Method & Innovation)
- What is the core methodological framework and its key mechanisms?
- How does it differ from existing or previous work?

### 3. 实验设置 (Experimental Setup)
- What datasets, evaluation metrics, and baselines were used?
- Briefly outline the training or evaluation setup.

### 4. 核心结果 (Core Results)
- What are the main findings and the margin of improvement?
- Are there conclusions regarding robustness or generalization?

### 5. 局限与风险 (Limitations & Risks)
- What are the boundaries of applicability, potential biases, or failure modes?

### 6. 给科研实践的建议 (Suggestions for Research Practice)
- How easy is it to reproduce? Provide advice on model selection or directions for future follow-up research.

## 参考样例 (Example Output)

Here is a brief, illustrative example of how a section should be formatted in your final Chinese response:

### 4. 核心结果
- **主要结论:** 该模型在 MMLU 基准测试上较上一代 SOTA 提升了 4.2%，尤其在复杂推理任务中表现更优 [1]。
- **稳健性:** 在带有严重噪声的输入下，性能下降幅度仅为 2%（推断：这可能归功于其引入的全新自适应归一化策略）。
