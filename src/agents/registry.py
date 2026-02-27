# -*- coding: utf-8 -*-
"""
Agent Registry
===============

Central registry defining all available agents, their identities,
capabilities, and metadata for UI display.
"""

from dataclasses import dataclass, field


@dataclass
class AgentInfo:
    """Agent identity and metadata."""
    id: str
    name: str
    emoji: str
    color: str
    description: str
    capabilities: list[str] = field(default_factory=list)


# Global agent registry
AGENT_REGISTRY: dict[str, AgentInfo] = {
    "retriever": AgentInfo(
        id="retriever",
        name="检索智能体",
        emoji="🔍",
        color="#3B82F6",
        description="从知识库中检索相关文献和段落",
        capabilities=["文献检索", "段落匹配", "相关度排序"],
    ),
    "reasoner": AgentInfo(
        id="reasoner",
        name="推理智能体",
        emoji="🧠",
        color="#8B5CF6",
        description="基于检索结果进行分析、推理和问答",
        capabilities=["上下文理解", "逻辑推理", "问答生成"],
    ),
    "researcher": AgentInfo(
        id="researcher",
        name="研究智能体",
        emoji="📊",
        color="#10B981",
        description="生成结构化研究报告和文献综述",
        capabilities=["研究计划", "文献综述", "报告生成"],
    ),
    "reviewer": AgentInfo(
        id="reviewer",
        name="审稿智能体",
        emoji="🧑‍🏫",
        color="#F59E0B",
        description="审阅论文内容并提出修改建议",
        capabilities=["论文审阅", "问题发现", "改进建议"],
    ),
}


def get_agent_info(agent_id: str) -> AgentInfo | None:
    """Get agent info by ID."""
    return AGENT_REGISTRY.get(agent_id)


def get_all_agents() -> list[dict]:
    """Get all agents as serializable dicts for API responses."""
    return [
        {
            "id": a.id,
            "name": a.name,
            "emoji": a.emoji,
            "color": a.color,
            "description": a.description,
            "capabilities": a.capabilities,
        }
        for a in AGENT_REGISTRY.values()
    ]
