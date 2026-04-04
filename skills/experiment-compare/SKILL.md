---
name: experiment-compare
description: How to compare experiments across different academic papers and methods. Make sure to use this skill whenever the user asks to compare methods A and B, asks for experimental differences across papers, or wants to know the reasons why results differ between different approaches. 
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

# 实验对比 (Experiment Compare)

This skill is designed to help users quickly grasp the empirical differences between multiple academic papers or methods by structuring the comparison into a clear table followed by an analysis.

## Output Guidelines & Philosophy

When structuring your comparison, follow these guidelines to maximize utility for the user:

- **Format in Markdown:** Please use Markdown exclusively for your output (especially for tables and headings). This avoids rendering issues caused by raw HTML tags.
- **Respond completely in Chinese (中文):** Even though these instructions and section titles are written in English (to help you understand the logical structure better), your FINAL output MUST be written entirely in Chinese, including the table headers. You may keep English technical terms if appropriate.
- **Provide a High-Level Table First:** Users usually want a quick birds-eye view before diving into the details. Provide a comparison table first, and then follow up with a detailed explanation of the differences.
- **Evidence-Based Explanations:** When discussing why two methods perform differently, quote evidence from the text if available (using bracketed citations like `[1]`). If you are inferring the cause of a performance difference based on your own knowledge, kindly mark it with "（推断）" (Inference) so the user knows it's an educated guess rather than a verified claim from the authors.

## Expected Report Structure

ALWAYS structure your answer using the following sections:

### 1. 对比范围 (Scope of Comparison)
- State what is being compared and the underlying premise (e.g., the specific task, datasets involved, or model versions).

### 2. 关键对比表 (Key Comparison Table)
Provide a table outlining the differences. Use this template:

| 维度 (Dimension) | 方法A (Method A) | 方法B (Method B) | 差异结论 (Conclusion of Difference) |
| --- | --- | --- | --- |
| 数据集 (Datasets) |  |  |  |
| 指标 (Metrics) |  |  |  |
| 结果 (Results) |  |  |  |
| 资源成本 (Resource Cost) |  |  |  |

### 3. 差异原因分析 (Analysis of Differences)
- Explain the possible reasons for the differences in the table. Provide a logical chain of evidence.

### 4. 选型建议 (Selection Recommendation)
- Provide recommendations on which method to choose under different constraints (e.g., accuracy vs. cost vs. latency).

## 参考样例 (Example Output)

Here is an illustrative example of the expected table and analysis:

### 2. 关键对比表

| 维度 | FlashAttention-2 | PagedAttention | 差异结论 |
| --- | --- | --- | --- |
| **内存池化** | 无，固定尺寸切块 | 有，非连续内存分页 | 显存利用率 PagedAttention 显著更高 |
| **IO 成本** | 极低（SRAM优化） | 中等（需管理页表） | 加密/计算密集场合适用 FlashAttention-2 |

### 3. 差异原因分析
- PagedAttention 在应对不定长请求时极大地缓解了显存碎片问题，从而实现了高达 40% 的吞吐量提升 [2]。这主要得益于其将操作系统中的虚拟内存分页思想引入了 KV Cache 管理。
