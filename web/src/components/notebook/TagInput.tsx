'use client';

import { useState, useRef } from 'react';
import { X } from 'lucide-react';

const TAG_COLORS = [
    'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300',
    'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300',
    'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300',
    'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300',
    'bg-rose-100 text-rose-700 dark:bg-rose-900/30 dark:text-rose-300',
    'bg-cyan-100 text-cyan-700 dark:bg-cyan-900/30 dark:text-cyan-300',
    'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-300',
    'bg-indigo-100 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-300',
];

function getTagColor(tag: string): string {
    let hash = 0;
    for (let i = 0; i < tag.length; i++) {
        hash = tag.charCodeAt(i) + ((hash << 5) - hash);
    }
    return TAG_COLORS[Math.abs(hash) % TAG_COLORS.length];
}

interface TagInputProps {
    tags: string[];
    onChange: (tags: string[]) => void;
    placeholder?: string;
    disabled?: boolean;
}

export default function TagInput({ tags, onChange, placeholder = '添加标签，按 Enter 确认', disabled }: TagInputProps) {
    const [input, setInput] = useState('');
    const inputRef = useRef<HTMLInputElement>(null);

    const addTag = (value: string) => {
        const tag = value.trim();
        if (tag && !tags.includes(tag)) {
            onChange([...tags, tag]);
        }
        setInput('');
    };

    const removeTag = (tag: string) => {
        onChange(tags.filter((t) => t !== tag));
    };

    const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
        if (e.key === 'Enter' && input.trim()) {
            e.preventDefault();
            addTag(input);
        } else if (e.key === 'Backspace' && !input && tags.length > 0) {
            removeTag(tags[tags.length - 1]);
        }
    };

    return (
        <div
            className="flex flex-wrap items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-800 min-h-[36px] cursor-text transition-colors focus-within:ring-2 focus-within:ring-blue-500 focus-within:border-transparent"
            onClick={() => inputRef.current?.focus()}
        >
            {tags.map((tag) => (
                <span
                    key={tag}
                    className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${getTagColor(tag)} transition-all`}
                >
                    {tag}
                    {!disabled && (
                        <button
                            onClick={(e) => {
                                e.stopPropagation();
                                removeTag(tag);
                            }}
                            className="hover:opacity-70 transition-opacity"
                        >
                            <X size={12} />
                        </button>
                    )}
                </span>
            ))}
            {!disabled && (
                <input
                    ref={inputRef}
                    type="text"
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={handleKeyDown}
                    onBlur={() => { if (input.trim()) addTag(input); }}
                    placeholder={tags.length === 0 ? placeholder : ''}
                    className="flex-1 min-w-[80px] bg-transparent outline-none text-sm text-slate-700 dark:text-slate-200 placeholder:text-slate-400"
                />
            )}
        </div>
    );
}

export { getTagColor };
