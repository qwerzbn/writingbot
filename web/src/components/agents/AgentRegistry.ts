'use client';

/**
 * Agent identity definitions shared across frontend components.
 * Mirrors the backend registry in src/agents/registry.py.
 */

export interface AgentInfo {
    id: string;
    name: string;
    emoji: string;
    color: string;
    description: string;
    capabilities: string[];
}

export const AGENTS: Record<string, AgentInfo> = {
    retriever: {
        id: 'retriever',
        name: '检索智能体',
        emoji: '🔍',
        color: '#3B82F6',
        description: '从知识库中检索相关文献和段落',
        capabilities: ['文献检索', '段落匹配', '相关度排序'],
    },
    reasoner: {
        id: 'reasoner',
        name: '推理智能体',
        emoji: '🧠',
        color: '#8B5CF6',
        description: '基于检索结果进行分析、推理和问答',
        capabilities: ['上下文理解', '逻辑推理', '问答生成'],
    },
    researcher: {
        id: 'researcher',
        name: '研究智能体',
        emoji: '📊',
        color: '#10B981',
        description: '生成结构化研究报告和文献综述',
        capabilities: ['研究计划', '文献综述', '报告生成'],
    },
    reviewer: {
        id: 'reviewer',
        name: '审稿智能体',
        emoji: '🧑‍🏫',
        color: '#F59E0B',
        description: '审阅论文内容并提出修改建议',
        capabilities: ['论文审阅', '问题发现', '改进建议'],
    },
};

export function getAgent(id: string): AgentInfo {
    return AGENTS[id] || AGENTS.reasoner;
}
