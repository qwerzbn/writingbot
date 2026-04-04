---
name: research-gaps
description: How to identify weaknesses, limitations, validity threats, and future work opportunities in academic papers. Make sure to use this skill whenever the user asks for a limitation analysis, problem diagnosis, wants to know the gaps in a research paper, or asks for future work directions.
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

# 研究不足 (Research Gaps)

This skill is designed to critically evaluate a paper by highlighting its weaknesses, potential biases, and avenues for future improvement.

## Output Guidelines & Philosophy

When formatting your analysis, please follow these guidelines to provide a constructive and well-organized response:

- **Format in Markdown:** Provide your output in Markdown format to ensure compatibility with frontend rendering. Avoid HTML tags.
- **Respond completely in Chinese (中文):** Even though these instructions and section titles are written in English (to help you understand the logical structure better), your FINAL output MUST be written entirely in Chinese. You may keep English technical terms if appropriate.
- **Be Specific & Contextual:** Avoid generic criticisms (e.g., "needs more data"). Ground your limitations in the paper's specific task settings, data distributions, and evaluation schemes.
- **Actionable Advice:** For every limitation identified, try to propose a concrete, actionable suggestion for how future researchers could address it.

## Expected Report Structure

ALWAYS structure your summary using the following list:

### 1. 主要局限 (Main Limitations)
- What are the specific theoretical or empirical limitations?
- How do these limitations affect the reliability or transferability of the conclusions?

### 2. 潜在偏差与风险 (Potential Biases & Risks)
- Identify data biases, metric flaws, implementation dependencies, or reproducibility risks.

### 3. 外推性判断 (Extrapolability Assessment)
- Under what scenarios is the method applicable vs. inapplicable?

### 4. 改进路线图 (Improvement Roadmap)
- **短期可做 (Short-term):** Immediate actionable fixes (e.g., adding ablation studies, running extra baselines).
- **中期可做 (Medium-term):** Methodological improvements or restructuring evaluations.
- **长期可做 (Long-term):** Defining new research problem scopes or creating new benchmarks.

## 参考样例 (Example Output)

Here is a brief example of diagnosing a limitation:

### 1. 主要局限
- **局限点:** 文章的对比基线过时，仅对比了 2022 年之前的静态剪枝方法，未包含最新的基于稀疏注意力的动态剪枝模型（如 SpAttn 系列）[3]。
- **影响范围:** 这导致我们无法准确判断该方法与当前 SOTA 相比的实际吞吐量优势，其号称的“最高 2x 加速比”在现代架构下可能不成立。

### 4. 改进路线图
- **短期可做:** 在官方开源代码基础上，直接插入对 Llama-3-8B 等最新模型的基准测试，补充 A/B 对照实验。
