import type * as Monaco from 'monaco-editor';

let configured = false;

export const FASTWRITE_LATEX_THEME = 'fastwrite-latex-dark';
export const FASTWRITE_LATEX_LANGUAGE = 'latex-fastwrite';

export function ensureLatexMonaco(monaco: typeof Monaco) {
  if (configured) return;
  configured = true;

  monaco.languages.register({ id: FASTWRITE_LATEX_LANGUAGE });

  monaco.languages.setMonarchTokensProvider(FASTWRITE_LATEX_LANGUAGE, {
    defaultToken: 'text',
    tokenizer: {
      root: [
        [/%.*$/, 'comment'],
        [/(\\(?:begin|end))(\{)([^}]+)(\})/, ['keyword.command', 'delimiter.brace', 'keyword.environment', 'delimiter.brace']],
        [/\\[a-zA-Z@]+/, 'keyword.command'],
        [/[{}[\]()]/, 'delimiter.brace'],
        [/\$[^$]*\$/, 'number.math'],
        [/\^\^?|__?/, 'operator'],
        [/(\\label|\\ref|\\cite|\\eqref)(\{)([^}]+)(\})/, ['keyword.command', 'delimiter.brace', 'identifier.reference', 'delimiter.brace']],
        [/(&|\\\\)/, 'operator'],
        [/\b\d+(\.\d+)?\b/, 'number'],
        [/[^\\%$&{}[\]()]+/, 'text'],
      ],
    },
  });

  monaco.editor.defineTheme(FASTWRITE_LATEX_THEME, {
    base: 'vs-dark',
    inherit: true,
    rules: [
      { token: 'text', foreground: 'E5E7EB' },
      { token: 'comment', foreground: '6B7280', fontStyle: 'italic' },
      { token: 'keyword.command', foreground: '7DD3C7' },
      { token: 'keyword.environment', foreground: '8DE1D2' },
      { token: 'identifier.reference', foreground: 'FACC15' },
      { token: 'number', foreground: 'FDE68A' },
      { token: 'number.math', foreground: 'C4B5FD' },
      { token: 'operator', foreground: 'EAB308' },
      { token: 'delimiter.brace', foreground: 'A1A1AA' },
    ],
    colors: {
      'editor.background': '#050505',
      'editor.foreground': '#E5E7EB',
      'editorLineNumber.foreground': '#707070',
      'editorLineNumber.activeForeground': '#F3F4F6',
      'editorCursor.foreground': '#F5F5F5',
      'editor.selectionBackground': '#1F3A5D',
      'editor.selectionHighlightBackground': '#14324E',
      'editor.lineHighlightBackground': '#0E0E0E',
      'editorIndentGuide.background1': '#252525',
      'editorIndentGuide.activeBackground1': '#3C3C3C',
      'editorBracketMatch.background': '#0F766E33',
      'editorBracketMatch.border': '#5EEAD4',
      'editorGutter.background': '#050505',
      'editorWhitespace.foreground': '#1F2937',
      'editorOverviewRuler.border': '#00000000',
      'scrollbarSlider.background': '#3F3F4633',
      'scrollbarSlider.hoverBackground': '#52525B55',
      'scrollbarSlider.activeBackground': '#71717A66',
    },
  });
}
