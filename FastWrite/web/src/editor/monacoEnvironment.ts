import editorWorker from 'monaco-editor/esm/vs/editor/editor.worker?worker';

const monacoWindow = window as Window & {
  MonacoEnvironment?: {
    getWorker: (_workerId: string, _label: string) => Worker;
  };
};

monacoWindow.MonacoEnvironment = {
  getWorker() {
    return new editorWorker();
  },
};
