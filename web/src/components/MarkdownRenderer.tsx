'use client';

import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import CitationCard, { CitationSource } from './chat/CitationCard';

interface MarkdownRendererProps {
    content: string;
    className?: string;
    sources?: CitationSource[];
    onCitationClick?: (source: CitationSource) => void;
}

export default function MarkdownRenderer({ content, className = '', sources = [], onCitationClick }: MarkdownRendererProps) {
    // Only convert [N] markers into citation links when we have actual source data.
    // Limit the conversion to indices that exist in the sources array.
    const processedContent = sources.length > 0
        ? content.replace(/\[(\d+)\]/g, (match, num) => {
            const idx = parseInt(num, 10);
            return idx >= 1 && idx <= sources.length
                ? `[${num}](#citation-${num})`
                : match; // leave as plain text if no matching source
        })
        : content;

    return (
        <div className={`prose prose-sm prose-slate dark:prose-invert max-w-none 
            prose-headings:font-semibold prose-headings:text-slate-800 dark:prose-headings:text-slate-100
            prose-p:text-slate-700 dark:prose-p:text-slate-300 prose-p:leading-relaxed
            prose-a:text-blue-500 prose-a:no-underline hover:prose-a:underline
            prose-code:text-rose-500 dark:prose-code:text-rose-400 prose-code:bg-slate-100 dark:prose-code:bg-slate-800 prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded prose-code:text-xs prose-code:before:content-none prose-code:after:content-none
            prose-pre:bg-slate-900 dark:prose-pre:bg-slate-950 prose-pre:rounded-lg prose-pre:text-sm
            prose-table:text-sm
            prose-th:bg-slate-100 dark:prose-th:bg-slate-800 prose-th:px-3 prose-th:py-2
            prose-td:px-3 prose-td:py-2 prose-td:border-slate-200 dark:prose-td:border-slate-700
            prose-li:text-slate-700 dark:prose-li:text-slate-300
            prose-blockquote:border-blue-400 prose-blockquote:bg-blue-50 dark:prose-blockquote:bg-blue-900/20 prose-blockquote:rounded-r-lg prose-blockquote:py-1
            ${className}`}
        >
            <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                    a: ({ node, href, children, ...props }) => {
                        if (href?.startsWith('#citation-')) {
                            const indexStr = href.replace('#citation-', '');
                            const index = parseInt(indexStr, 10);

                            if (!isNaN(index)) {
                                const source = sources[index - 1]; // 1-based index to 0-based array
                                return (
                                    <CitationCard
                                        index={index}
                                        source={source}
                                        onClick={() => onCitationClick && source && onCitationClick(source)}
                                    />
                                );
                            }
                        }
                        return <a href={href} {...props}>{children}</a>;
                    }
                }}
            >
                {processedContent}
            </ReactMarkdown>
        </div>
    );
}
