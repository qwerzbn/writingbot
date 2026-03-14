'use client';

import { useAppContext } from '@/context/AppContext';
import {
  BookOpen,
  MessageCircle,
  Notebook,
  Search,
  PenTool,
  FileText,
  ArrowRight,
} from 'lucide-react';
import Link from 'next/link';

const features = [
  {
    href: '/knowledge',
    icon: BookOpen,
    label: '知识库',
    desc: '管理文档和知识源',
    color: 'from-blue-500 to-cyan-400',
  },
  {
    href: '/chat',
    icon: MessageCircle,
    label: '智能问答',
    desc: '基于知识库进行多轮对话，支持来源引用',
    color: 'from-sky-500 to-blue-400',
  },
  {
    href: '/notebook',
    icon: Notebook,
    label: '笔记本',
    desc: '保存和整理研究记录',
    color: 'from-amber-500 to-orange-400',
  },
  {
    href: '/research',
    icon: Search,
    label: '深度研究',
    desc: '自动生成结构化研究报告',
    color: 'from-emerald-500 to-teal-400',
  },
  {
    href: '/co-writer',
    icon: PenTool,
    label: '协同写作',
    desc: 'LaTeX 论文协同编辑与 AI 辅助写作',
    color: 'from-rose-500 to-pink-400',
  },
];

export default function Dashboard() {
  const { kbs } = useAppContext();

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-900 p-8 transition-colors">
      {/* Header */}
      <div className="mb-10">
        <h1 className="text-3xl font-bold text-slate-800 dark:text-white mb-2">
          WritingBot
        </h1>
        <p className="text-slate-500 dark:text-slate-400 text-lg">
          Multi-Agent 学术写作助手
        </p>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 gap-4 mb-10">
        {[
          { label: '知识库', value: kbs.length, icon: BookOpen },
          { label: '文档', value: kbs.reduce((sum, kb) => sum + (kb.files?.length || 0), 0), icon: FileText },
        ].map(({ label, value, icon: Icon }) => (
          <div
            key={label}
            className="bg-white dark:bg-slate-800 rounded-xl p-5 shadow-sm border border-slate-200 dark:border-slate-700"
          >
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-blue-50 dark:bg-blue-900/30 flex items-center justify-center text-blue-500">
                <Icon size={20} />
              </div>
              <div>
                <p className="text-2xl font-bold text-slate-800 dark:text-white">
                  {value}
                </p>
                <p className="text-sm text-slate-500 dark:text-slate-400">
                  {label}
                </p>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Feature Grid */}
      <h2 className="text-lg font-semibold text-slate-700 dark:text-slate-200 mb-4">
        功能模块
      </h2>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {features.map(({ href, icon: Icon, label, desc, color }) => (
          <Link
            key={href}
            href={href}
            className="group bg-white dark:bg-slate-800 rounded-xl p-6 shadow-sm border border-slate-200 dark:border-slate-700 hover:shadow-md hover:border-slate-300 dark:hover:border-slate-600 transition-all duration-200"
          >
            <div
              className={`w-12 h-12 rounded-xl bg-gradient-to-br ${color} flex items-center justify-center text-white mb-4 shadow-lg`}
            >
              <Icon size={22} />
            </div>
            <h3 className="text-lg font-semibold text-slate-800 dark:text-white mb-1 flex items-center gap-2">
              {label}
              <ArrowRight
                size={16}
                className="opacity-0 group-hover:opacity-100 transition-opacity text-slate-400"
              />
            </h3>
            <p className="text-sm text-slate-500 dark:text-slate-400">
              {desc}
            </p>
          </Link>
        ))}
      </div>
    </div>
  );
}
