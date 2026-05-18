import { afterEach, describe, expect, it } from 'vitest';
import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';

import type { ProjectConfig } from '../web/src/types';
import { buildLatexProfile } from './latexBuild';

const tempDirs: string[] = [];

function createProject(structure: Record<string, string>): { rootDir: string; config: ProjectConfig } {
  const rootDir = mkdtempSync(join(tmpdir(), 'fastwrite-latex-'));
  tempDirs.push(rootDir);

  for (const [relativePath, content] of Object.entries(structure)) {
    const absolutePath = join(rootDir, relativePath);
    mkdirSync(join(absolutePath, '..'), { recursive: true });
    writeFileSync(absolutePath, content, 'utf-8');
  }

  return {
    rootDir,
    config: {
      projectId: 'proj_test',
      sectionsDir: rootDir,
      backupsDir: join(rootDir, 'backups'),
      bibFiles: [],
      compileMode: 'auto',
      preferredEngine: 'auto',
      shellEscape: 'auto',
      bibTool: 'auto',
    },
  };
}

afterEach(() => {
  for (const dir of tempDirs.splice(0)) {
    rmSync(dir, { recursive: true, force: true });
  }
});

describe('buildLatexProfile', () => {
  it('keeps lightweight article projects eligible for browser preview', () => {
    const { config } = createProject({
      'main.tex': [
        '\\documentclass{article}',
        '\\usepackage{amsmath}',
        '\\usepackage{hyperref}',
        '\\begin{document}',
        'Hello FastWrite',
        '\\end{document}',
      ].join('\n'),
    });

    const profile = buildLatexProfile(config);

    expect(profile.mainFile).toBe('main.tex');
    expect(profile.suitableForBrowserPreview).toBe(true);
    expect(profile.effectiveEngine).toBe('pdflatex');
    expect(profile.bibTool).toBe('auto');
  });

  it('resolves TeX root directives and detects complex local-only projects', () => {
    const { config } = createProject({
      'main.tex': [
        '\\documentclass{acmart}',
        '\\usepackage{biblatex}',
        '\\addbibresource{references.bib}',
        '\\usepackage{minted}',
        '\\begin{document}',
        '\\input{sections/intro}',
        '\\end{document}',
      ].join('\n'),
      'sections/intro.tex': [
        '% !TeX root = ../main.tex',
        '\\section{Intro}',
        'Hello',
      ].join('\n'),
      'references.bib': '@article{demo,title={Demo}}',
    });

    const profile = buildLatexProfile(config, 'sections/intro.tex');

    expect(profile.mainFile).toBe('main.tex');
    expect(profile.suitableForBrowserPreview).toBe(false);
    expect(profile.browserPreviewReasons.join(' ')).toContain('acmart');
    expect(profile.bibTool).toBe('biber');
    expect(profile.shellEscape).toBe(true);
  });

  it('respects fastwrite.json overrides for main file and engine', () => {
    const { config } = createProject({
      'fastwrite.json': JSON.stringify({
        mainFile: 'paper/main.tex',
        engine: 'xelatex',
        shellEscape: false,
        bibTool: 'bibtex',
      }),
      'paper/main.tex': [
        '\\documentclass{article}',
        '\\begin{document}',
        'Configured main file',
        '\\end{document}',
      ].join('\n'),
      'scratch.tex': [
        '\\documentclass{article}',
        '\\begin{document}',
        'Scratch',
        '\\end{document}',
      ].join('\n'),
    });

    const profile = buildLatexProfile(config);

    expect(profile.mainFile).toBe('paper/main.tex');
    expect(profile.effectiveEngine).toBe('xelatex');
    expect(profile.shellEscape).toBe(false);
    expect(profile.bibTool).toBe('bibtex');
  });
});
