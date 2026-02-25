# -*- coding: utf-8 -*-
"""
ResearchAgent - Deep research with multi-stage generation.

Stages:
1. Plan: Generate research outline/key points
2. Research: Retrieve relevant context from KB
3. Report: Generate structured research report
"""

from typing import Any, Generator

from src.agents.base_agent import BaseAgent


class ResearchAgent(BaseAgent):
    """
    Research agent for generating structured reports.

    Supports streaming for the report generation stage.
    """

    def __init__(self, language: str = "zh"):
        super().__init__(
            module_name="research",
            agent_name="research_agent",
            language=language,
        )

    def plan(self, topic: str) -> str:
        """Generate research plan (key points to investigate)."""
        plan_prompt = self.get_prompt("plan", "").format(topic=topic)
        messages = [
            {"role": "system", "content": self.get_prompt("system", "")},
            {"role": "user", "content": plan_prompt},
        ]
        return self.call_llm(messages)

    def generate_report(
        self,
        topic: str,
        points: str = "",
        context: str = "",
        stream: bool = False,
    ) -> str | Generator[str, None, None]:
        """Generate a research report."""
        report_prompt = self.get_prompt("report", "").format(
            topic=topic, points=points, context=context or "(无参考资料)"
        )
        messages = [
            {"role": "system", "content": self.get_prompt("system", "")},
            {"role": "user", "content": report_prompt},
        ]
        if stream:
            return self.stream_llm(messages)
        return self.call_llm(messages)

    def process(
        self,
        topic: str,
        vector_store: Any = None,
        stream: bool = False,
    ) -> dict:
        """
        Full research pipeline: plan → retrieve → report.

        Args:
            topic: Research topic
            vector_store: Optional VectorStore for context retrieval
            stream: Whether to stream the report

        Returns:
            Dict with 'plan', 'report' (or 'stream'), and 'sources'
        """
        # Stage 1: Plan
        plan = self.plan(topic)

        # Stage 2: Retrieve context (if KB available)
        context = ""
        sources = []
        if vector_store:
            from src.rag.components.retriever import VectorRetriever
            from src.rag.components.context_builder import ContextBuilder

            retriever = VectorRetriever(vector_store, top_k=8)
            builder = ContextBuilder(max_context_length=6000)
            results = retriever.retrieve(topic)
            context, sources = builder.build(results)

        # Stage 3: Generate report
        if stream:
            return {
                "plan": plan,
                "stream": self.generate_report(topic, plan, context, stream=True),
                "sources": sources,
            }
        else:
            report = self.generate_report(topic, plan, context, stream=False)
            return {
                "plan": plan,
                "report": report,
                "sources": sources,
            }
