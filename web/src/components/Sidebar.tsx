'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
    LayoutDashboard,
    BookOpen,
    MessageSquare,
    Notebook,
    Search,
    PenTool,
    Settings,
    Moon,
    Sun,
} from 'lucide-react';
import { useState, useEffect } from 'react';

const navItems = [
    { href: '/', icon: LayoutDashboard, label: '总览' },
    { href: '/knowledge', icon: BookOpen, label: '知识库' },
    { href: '/chat', icon: MessageSquare, label: '对话' },
    { href: '/notebook', icon: Notebook, label: '笔记本' },
    { href: '/research', icon: Search, label: '研究' },
    { href: '/co-writer', icon: PenTool, label: '写作' },
];

export default function Sidebar() {
    const pathname = usePathname();
    const [dark, setDark] = useState(false);

    useEffect(() => {
        const saved = localStorage.getItem('writingbot_dark');
        if (saved === 'true') {
            setDark(true);
            document.documentElement.classList.add('dark');
        }
    }, []);

    const toggleDark = () => {
        const next = !dark;
        setDark(next);
        document.documentElement.classList.toggle('dark', next);
        localStorage.setItem('writingbot_dark', String(next));
    };

    return (
        <aside className="w-16 bg-slate-800 dark:bg-slate-900 flex flex-col items-center py-6 shrink-0 transition-colors">
            {/* Logo */}
            <div className="w-10 h-10 bg-gradient-to-br from-blue-500 to-indigo-600 rounded-lg flex items-center justify-center text-white font-bold mb-8 shadow-lg shadow-blue-500/30">
                <svg viewBox="0 0 24 24" fill="currentColor" className="w-5 h-5">
                    <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" />
                </svg>
            </div>

            {/* Nav */}
            <nav className="flex-1 flex flex-col gap-2">
                {navItems.map(({ href, icon: Icon, label }) => {
                    const isActive =
                        href === '/'
                            ? pathname === '/'
                            : pathname.startsWith(href);
                    return (
                        <Link
                            key={href}
                            href={href}
                            title={label}
                            className={`w-10 h-10 rounded-lg flex items-center justify-center transition-all duration-200 ${isActive
                                ? 'bg-blue-500 text-white shadow-lg shadow-blue-500/30'
                                : 'text-slate-400 hover:bg-slate-700 hover:text-white'
                                }`}
                        >
                            <Icon size={20} />
                        </Link>
                    );
                })}
            </nav>

            {/* Bottom buttons */}
            <div className="flex flex-col gap-2">
                <button
                    onClick={toggleDark}
                    className="w-10 h-10 rounded-lg flex items-center justify-center text-slate-400 hover:bg-slate-700 hover:text-white transition-all"
                    title={dark ? '浅色模式' : '深色模式'}
                >
                    {dark ? <Sun size={18} /> : <Moon size={18} />}
                </button>
                <Link
                    href="/settings"
                    title="设置"
                    className={`w-10 h-10 rounded-lg flex items-center justify-center transition-all ${pathname === '/settings'
                            ? 'bg-blue-500 text-white shadow-lg shadow-blue-500/30'
                            : 'text-slate-400 hover:bg-slate-700 hover:text-white'
                        }`}
                >
                    <Settings size={20} />
                </Link>
            </div>
        </aside>
    );
}
