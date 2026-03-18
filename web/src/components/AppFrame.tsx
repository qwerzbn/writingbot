'use client';

import { usePathname } from 'next/navigation';

import Sidebar from '@/components/Sidebar';
import AppToaster from '@/components/ui/sonner';

interface AppFrameProps {
  children: React.ReactNode;
}

function isNotebookWorkspacePath(pathname: string): boolean {
  return pathname.startsWith('/notebook/');
}

export default function AppFrame({ children }: AppFrameProps) {
  const pathname = usePathname();
  const notebookWorkspace = isNotebookWorkspacePath(pathname);

  if (notebookWorkspace) {
    return (
      <div className="h-screen overflow-hidden bg-stone-950 text-stone-50">
        <main className="h-full min-h-0 overflow-hidden">{children}</main>
        <AppToaster />
      </div>
    );
  }

  return (
    <div className="flex h-screen overflow-hidden bg-slate-100 transition-colors dark:bg-slate-900">
      <Sidebar />
      <main className="min-h-0 flex-1 overflow-hidden">{children}</main>
      <AppToaster />
    </div>
  );
}
