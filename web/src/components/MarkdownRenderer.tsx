'use client';

import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import 'katex/dist/katex.min.css';
import CitationCard, { CitationSource } from './common/CitationCard';

interface MarkdownRendererProps {
    content: string;
    className?: string;
    sources?: CitationSource[];
    onCitationClick?: (source: CitationSource) => void;
}

function preprocessMarkdownContent(raw: string): string {
    if (!raw) return '';
    let output = raw.replace(/\r\n?/g, '\n');
    output = output.replace(/&lt;br\s*\/?&gt;/gi, '  \n');
    output = output.replace(/<br\s*\/?>/gi, '  \n');
    output = output.replace(/<\/?(?:p|div|section|article|header|footer|main)\b[^>]*>/gi, '\n');
    output = output.replace(/<\/?(?:span|font)\b[^>]*>/gi, '');
    output = output.replace(/<\/?(?:ul|ol|li|table|thead|tbody|tr|th|td|blockquote)\b[^>]*>/gi, '\n');
    output = output.replace(/<\/?(?:strong|b|em|i|u)\b[^>]*>/gi, '');
    output = output.replace(/<[^>\n]+>/g, '');
    output = output.replace(/&nbsp;/gi, ' ');
    output = output.replace(/&lt;(\/?)(?:p|div|span|br|section|article|table|tr|td|th)&gt;/gi, '');
    output = output.replace(/\n{3,}/g, '\n\n');
    return output.trim();
}

export default function MarkdownRenderer({ content, className = '', sources = [], onCitationClick }: MarkdownRendererProps) {
    const normalizedContent = preprocessMarkdownContent(content);
    // Only convert [N] markers into citation links when we have actual source data.
    // Limit the conversion to indices that exist in the sources array.
    const processedContent = sources.length > 0
        ? normalizedContent.replace(/\[(\d+)\]/g, (match, num) => {
            const idx = parseInt(num, 10);
            return idx >= 1 && idx <= sources.length
                ? `[${num}](#citation-${num})`
                : match; // leave as plain text if no matching source
        })
        : normalizedContent;

    return (
        <div className={`prose prose-sm prose-slate dark:prose-invert max-w-none 
            prose-headings:font-semibold prose-headings:text-slate-800 dark:prose-headings:text-slate-100
            prose-p:my-2 prose-p:text-slate-700 dark:prose-p:text-slate-300 prose-p:leading-relaxed
            prose-ul:my-2 prose-ol:my-2 prose-li:my-0.5
            prose-a:text-blue-500 prose-a:no-underline hover:prose-a:underline
            prose-code:text-rose-500 dark:prose-code:text-rose-400 prose-code:bg-slate-100 dark:prose-code:bg-slate-800 prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded prose-code:text-xs prose-code:before:content-none prose-code:after:content-none
            prose-pre:bg-slate-900 dark:prose-pre:bg-slate-950 prose-pre:rounded-lg prose-pre:text-sm
            prose-pre:my-2 prose-table:my-2 prose-table:text-sm
            prose-th:bg-slate-100 dark:prose-th:bg-slate-800 prose-th:px-3 prose-th:py-2
            prose-td:px-3 prose-td:py-2 prose-td:align-top prose-td:border-slate-200 dark:prose-td:border-slate-700 prose-td:break-words
            prose-li:text-slate-700 dark:prose-li:text-slate-300 prose-li:leading-relaxed
            prose-blockquote:border-blue-400 prose-blockquote:bg-blue-50 dark:prose-blockquote:bg-blue-900/20 prose-blockquote:rounded-r-lg prose-blockquote:py-1
            ${className}`}
        >
            <ReactMarkdown
                remarkPlugins={[remarkGfm, remarkMath]}
                rehypePlugins={[rehypeKatex]}
                components={{
                    p: ({ children }) => <p className="whitespace-pre-wrap break-words">{children}</p>,
                    table: ({ children }) => (
                        <div className="my-2 overflow-x-auto rounded-lg border border-slate-200 dark:border-slate-700">
                            <table className="w-full border-collapse text-sm">{children}</table>
                        </div>
                    ),
                    th: ({ children }) => (
                        <th className="whitespace-nowrap border border-slate-200 bg-slate-100 px-3 py-2 text-left align-top dark:border-slate-700 dark:bg-slate-800">
                            {children}
                        </th>
                    ),
                    td: ({ children }) => (
                        <td className="border border-slate-200 px-3 py-2 align-top break-words dark:border-slate-700">
                            {children}
                        </td>
                    ),
                    a: ({ href, children, ...props }) => {
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
