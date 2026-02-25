'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { BookOpen, MessageSquare, Settings } from 'lucide-react';

const navItems = [
    { href: '/knowledge', icon: BookOpen, label: '知识库' },
    { href: '/chat', icon: MessageSquare, label: '对话' },
];

export default function Sidebar() {
    const pathname = usePathname();

    return (
        <aside className="w-16 bg-slate-800 flex flex-col items-center py-6 shrink-0">
            {/* Logo */}
            <div className="w-10 h-10 bg-blue-500 rounded-lg flex items-center justify-center text-white font-bold mb-8 shadow-lg shadow-blue-500/30">
                <svg viewBox="0 0 24 24" fill="currentColor" className="w-5 h-5">
                    <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" />
                </svg>
            </div>

            {/* Nav */}
            <nav className="flex-1 flex flex-col gap-3">
                {navItems.map(({ href, icon: Icon, label }) => {
                    const isActive = pathname.startsWith(href);
                    return (
                        <Link
                            key={href}
                            href={href}
                            title={label}
                            className={`w-10 h-10 rounded-lg flex items-center justify-center transition-all ${isActive
                                    ? 'bg-blue-500 text-white shadow-lg shadow-blue-500/30'
                                    : 'text-slate-400 hover:bg-slate-700 hover:text-white'
                                }`}
                        >
                            <Icon size={20} />
                        </Link>
                    );
                })}
            </nav>

            {/* Settings */}
            <button className="w-10 h-10 rounded-lg flex items-center justify-center text-slate-400 hover:bg-slate-700 hover:text-white transition-all" title="设置">
                <Settings size={20} />
            </button>
        </aside>
    );
}
