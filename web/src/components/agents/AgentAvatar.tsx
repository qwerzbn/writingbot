'use client';

import { getAgent } from './AgentRegistry';

interface AgentAvatarProps {
    agentId: string;
    size?: 'sm' | 'md';
    showName?: boolean;
}

/**
 * Agent identity badge — shows emoji + optional name tag.
 * Used in message bubbles and workflow steps.
 */
export default function AgentAvatar({ agentId, size = 'sm', showName = false }: AgentAvatarProps) {
    const agent = getAgent(agentId);
    const sizeClass = size === 'md' ? 'w-8 h-8 text-base' : 'w-6 h-6 text-sm';

    return (
        <div className="flex items-center gap-1.5">
            <div
                className={`${sizeClass} rounded-lg flex items-center justify-center shrink-0`}
                style={{ backgroundColor: `${agent.color}20` }}
                title={agent.description}
            >
                <span>{agent.emoji}</span>
            </div>
            {showName && (
                <span
                    className="text-xs font-medium"
                    style={{ color: agent.color }}
                >
                    {agent.name}
                </span>
            )}
        </div>
    );
}
