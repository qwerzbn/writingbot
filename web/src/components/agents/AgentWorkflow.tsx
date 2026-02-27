'use client';

import { useState } from 'react';
import { ChevronDown, ChevronUp, Loader2, CheckCircle2, XCircle } from 'lucide-react';
import { getAgent } from './AgentRegistry';

export interface WorkflowStep {
    agent: string;
    status: 'working' | 'done' | 'error';
    message: string;
    duration?: number;
}

interface AgentWorkflowProps {
    steps: WorkflowStep[];
    isActive: boolean;
}

/**
 * Collapsible agent collaboration workflow timeline.
 * Shows each agent's step with status, message, and timing.
 */
export default function AgentWorkflow({ steps, isActive }: AgentWorkflowProps) {
    const [expanded, setExpanded] = useState(true);

    if (steps.length === 0) return null;

    // Summary line: count of active/done agents
    const doneCount = steps.filter((s) => s.status === 'done').length;
    const workingStep = steps.find((s) => s.status === 'working');

    return (
        <div className="mb-2">
            {/* Toggle header */}
            <button
                onClick={() => setExpanded(!expanded)}
                className="flex items-center gap-2 text-xs text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 transition-colors w-full"
            >
                {expanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                <span className="font-medium">
                    智能体协作
                </span>
                <span className="text-slate-400 dark:text-slate-500">
                    {isActive && workingStep
                        ? `${getAgent(workingStep.agent).name} 工作中...`
                        : `${doneCount} 个智能体参与`}
                </span>
            </button>

            {/* Steps timeline */}
            {expanded && (
                <div className="mt-2 ml-1 border-l-2 border-slate-200 dark:border-slate-700 pl-3 space-y-1.5">
                    {steps.map((step, i) => {
                        const agent = getAgent(step.agent);
                        return (
                            <div key={i} className="flex items-center gap-2 text-xs">
                                {/* Status indicator */}
                                <div className="shrink-0">
                                    {step.status === 'working' ? (
                                        <Loader2 size={12} className="animate-spin" style={{ color: agent.color }} />
                                    ) : step.status === 'done' ? (
                                        <CheckCircle2 size={12} className="text-emerald-500" />
                                    ) : (
                                        <XCircle size={12} className="text-red-500" />
                                    )}
                                </div>

                                {/* Agent emoji + name */}
                                <span>{agent.emoji}</span>
                                <span className="font-medium" style={{ color: agent.color }}>
                                    {agent.name}
                                </span>

                                {/* Message */}
                                <span className="text-slate-500 dark:text-slate-400 truncate flex-1">
                                    {step.message}
                                </span>

                                {/* Duration */}
                                {step.duration !== undefined && (
                                    <span className="text-slate-400 dark:text-slate-500 tabular-nums shrink-0">
                                        {step.duration}s
                                    </span>
                                )}
                            </div>
                        );
                    })}
                </div>
            )}
        </div>
    );
}
