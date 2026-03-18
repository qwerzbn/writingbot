import NotebookWorkspaceScreen from '@/components/notebook/NotebookWorkspaceScreen';

interface NotebookPageProps {
  params: Promise<{ id: string }>;
}

export default async function NotebookPage({ params }: NotebookPageProps) {
  const { id } = await params;
  return <NotebookWorkspaceScreen notebookId={decodeURIComponent(id)} />;
}
