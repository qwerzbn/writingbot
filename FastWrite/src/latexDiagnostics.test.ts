import { describe, expect, it } from 'vitest';

import { parseCompileDiagnostics } from './latexDiagnostics';

describe('parseCompileDiagnostics', () => {
  it('parses file-scoped diagnostics and resolves relative paths', () => {
    const log = [
      './sections/intro.tex:12: Undefined control sequence',
      'LaTeX Warning: Citation `foo2024` on page 1 undefined',
    ].join('\n');

    const diagnostics = parseCompileDiagnostics(log, '/tmp/project');

    expect(diagnostics).toHaveLength(2);
    expect(diagnostics[0]).toMatchObject({
      severity: 'error',
      filePath: '/tmp/project/sections/intro.tex',
      line: 12,
      message: 'Undefined control sequence',
      firstFatal: true,
    });
    expect(diagnostics[1]).toMatchObject({
      severity: 'warning',
      message: 'LaTeX Warning: Citation `foo2024` on page 1 undefined',
    });
  });

  it('marks only the first fatal diagnostic as firstFatal', () => {
    const log = [
      '! Undefined control sequence.',
      '! Emergency stop.',
    ].join('\n');

    const diagnostics = parseCompileDiagnostics(log, '/tmp/project');

    expect(diagnostics).toHaveLength(2);
    expect(diagnostics[0]?.firstFatal).toBe(true);
    expect(diagnostics[1]?.firstFatal).toBe(false);
  });

  it('classifies missing package diagnostics', () => {
    const log = "! LaTeX Error: File `xstring.sty' not found.";

    const diagnostics = parseCompileDiagnostics(log, '/tmp/project', 'local');

    expect(diagnostics[0]).toMatchObject({
      severity: 'error',
      category: 'missing-package',
      packageName: 'xstring',
      provider: 'local',
    });
  });
});
