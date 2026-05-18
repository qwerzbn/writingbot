import { existsSync, mkdirSync, readFileSync, readdirSync, statSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { basename, dirname, isAbsolute, join, normalize, relative, resolve } from 'node:path';

import type {
  BibTool,
  CompileCommandKind,
  CompileDiagnostic,
  LatexCapabilities,
  LatexEngine,
  LatexProfile,
  LatexToolCapability,
  ProjectConfig,
} from '../web/src/types';

import { parseCompileDiagnostics } from './latexDiagnostics';

const TEXBIN_PATH = '/Library/TeX/texbin';
const COMMON_MAIN_FILES = ['main.tex', 'paper.tex', 'document.tex'];
const BROWSER_ONLY_REASON_PREFIX = 'Skipped browser preview:';

export interface FastwriteBuildConfig {
  engine?: LatexEngine;
  mainFile?: string;
  shellEscape?: 'auto' | boolean;
  bibTool?: BibTool;
}

interface ProjectSignals {
  recommendedEngine: Exclude<LatexEngine, 'auto'>;
  detectedBibTool: BibTool;
  requiresShellEscape: boolean;
  suitableForBrowserPreview: boolean;
  browserPreviewReasons: string[];
  triggers: string[];
  usedLatexmkRc: boolean;
}

interface LocalCompileResult {
  success: boolean;
  provider: 'local';
  engine: Exclude<LatexEngine, 'auto'>;
  commandKind: CompileCommandKind;
  fallbackReason?: string;
  diagnostics: CompileDiagnostic[];
  log: string;
  warnings: number;
  hadNonZeroExit: boolean;
  pdfPath?: string;
  synctexPath?: string | null;
}

function coerceCompileMode(value: unknown): ProjectConfig['compileMode'] | undefined {
  if (value === 'auto' || value === 'local' || value === 'browser-preview') return value;
  if (value === 'browser-wasm') return 'browser-preview';
  return undefined;
}

function coerceEngine(value: unknown): LatexEngine | undefined {
  if (value === 'auto' || value === 'pdflatex' || value === 'xelatex' || value === 'lualatex') return value;
  return undefined;
}

function coerceBibTool(value: unknown): BibTool | undefined {
  if (value === 'auto' || value === 'bibtex' || value === 'biber') return value;
  return undefined;
}

function coerceShellEscape(value: unknown): 'auto' | boolean | undefined {
  if (value === 'auto' || typeof value === 'boolean') return value;
  return undefined;
}

function normalizeRelativePath(input: string): string {
  return normalize(input.replace(/\\/g, '/').replace(/^\.\/+/, '')).replace(/^\/+/, '');
}

function fileExists(pathValue: string | undefined): boolean {
  if (!pathValue) return false;
  return existsSync(pathValue) && statSync(pathValue).isFile();
}

function readTextFile(pathValue: string | undefined): string {
  if (!fileExists(pathValue)) return '';
  try {
    return readFileSync(pathValue!, 'utf-8');
  } catch {
    return '';
  }
}

function safeRelativePath(rootDir: string, targetPath: string): string | null {
  const resolvedRoot = resolve(rootDir);
  const resolvedTarget = resolve(targetPath);
  const rel = relative(resolvedRoot, resolvedTarget);
  if (!rel || rel === '') return basename(resolvedTarget);
  if (rel.startsWith('..') || isAbsolute(rel)) return null;
  return normalizeRelativePath(rel);
}

function resolveProjectPath(rootDir: string, candidate: string | undefined): string | null {
  if (!candidate) return null;
  const normalizedCandidate = normalizeRelativePath(candidate);
  const absolute = isAbsolute(candidate) ? candidate : join(rootDir, normalizedCandidate);
  if (!fileExists(absolute)) return null;
  const rel = safeRelativePath(rootDir, absolute);
  return rel && fileExists(join(rootDir, rel)) ? rel : null;
}

function listFilesRecursive(rootDir: string, extensions?: string[]): string[] {
  const results: string[] = [];

  const walk = (currentDir: string) => {
    const entries = readdirSync(currentDir, { withFileTypes: true });
    for (const entry of entries) {
      if (entry.name === 'output' || entry.name === '.git' || entry.name === 'node_modules') continue;
      const fullPath = join(currentDir, entry.name);
      if (entry.isDirectory()) {
        walk(fullPath);
        continue;
      }
      const rel = safeRelativePath(rootDir, fullPath);
      if (!rel) continue;
      if (!extensions || extensions.some((ext) => entry.name.toLowerCase().endsWith(ext))) {
        results.push(rel);
      }
    }
  };

  walk(rootDir);
  return results.sort((a, b) => a.localeCompare(b, undefined, { numeric: true, sensitivity: 'base' }));
}

function extractTexRootDirective(content: string): string | null {
  const match = content.match(/^\s*%\s*!TeX\s+root\s*=\s*(.+)\s*$/im);
  return match?.[1]?.trim() || null;
}

export function readFastwriteBuildConfig(rootDir: string): FastwriteBuildConfig | null {
  const configPath = join(rootDir, 'fastwrite.json');
  if (!fileExists(configPath)) return null;

  try {
    const data = JSON.parse(readFileSync(configPath, 'utf-8')) as Record<string, unknown>;
    return {
      engine: coerceEngine(data.engine),
      mainFile: typeof data.mainFile === 'string' ? normalizeRelativePath(data.mainFile) : undefined,
      shellEscape: coerceShellEscape(data.shellEscape),
      bibTool: coerceBibTool(data.bibTool),
    };
  } catch {
    return null;
  }
}

function detectMainFile(rootDir: string, texPath: string | undefined, configMainFile: string | undefined, fileConfigMainFile: string | undefined): string | null {
  const hintedRelative = texPath ? resolveProjectPath(rootDir, texPath) : null;
  const hintedContent = hintedRelative ? readTextFile(join(rootDir, hintedRelative)) : '';
  const texRootDirective = extractTexRootDirective(hintedContent);

  if (texRootDirective && hintedRelative) {
    const resolvedFromHint = join(dirname(join(rootDir, hintedRelative)), texRootDirective);
    const relativeFromHint = safeRelativePath(rootDir, resolvedFromHint);
    if (relativeFromHint && fileExists(join(rootDir, relativeFromHint))) return relativeFromHint;
  }

  for (const candidate of [configMainFile, fileConfigMainFile]) {
    const resolvedCandidate = resolveProjectPath(rootDir, candidate);
    if (resolvedCandidate) return resolvedCandidate;
  }

  const texFiles = listFilesRecursive(rootDir, ['.tex']);
  const scoredCandidates = texFiles
    .map((relativePath) => {
      const content = readTextFile(join(rootDir, relativePath));
      const hasDocumentClass = /\\documentclass(?:\[[^\]]*\])?\{[^}]+\}/.test(content);
      const hasBeginDocument = /\\begin\{document\}/.test(content);
      const commonName = COMMON_MAIN_FILES.includes(basename(relativePath));
      const score = (hasDocumentClass ? 4 : 0) + (hasBeginDocument ? 2 : 0) + (commonName ? 1 : 0);
      return { relativePath, score };
    })
    .filter((candidate) => candidate.score > 0)
    .sort((a, b) => b.score - a.score || a.relativePath.localeCompare(b.relativePath));

  if (scoredCandidates[0]?.relativePath) return scoredCandidates[0].relativePath;

  if (hintedRelative && resolveProjectPath(rootDir, hintedRelative)) return hintedRelative;

  const commonCandidate = texFiles.find((candidate) => COMMON_MAIN_FILES.includes(basename(candidate)));
  if (commonCandidate) return commonCandidate;

  return texFiles[0] || null;
}

function hasAny(text: string, patterns: RegExp[]): boolean {
  return patterns.some((pattern) => pattern.test(text));
}

function inferProjectSignals(rootDir: string, mainFile: string | null): ProjectSignals {
  const texFiles = listFilesRecursive(rootDir, ['.tex']);
  const bibliographyFiles = listFilesRecursive(rootDir, ['.bib', '.bst', '.bbx', '.cbx']);
  const joinedText = texFiles
    .map((relativePath) => readTextFile(join(rootDir, relativePath)))
    .join('\n');
  const mainText = mainFile ? readTextFile(join(rootDir, mainFile)) : '';
  const combinedText = `${mainText}\n${joinedText}`;
  const browserPreviewReasons: string[] = [];
  const triggers: string[] = [];
  let recommendedEngine: Exclude<LatexEngine, 'auto'> = 'pdflatex';
  let detectedBibTool: BibTool = 'auto';
  let requiresShellEscape = false;
  const usedLatexmkRc = fileExists(join(rootDir, '.latexmkrc'));

  const addBrowserReason = (reason: string, trigger?: string) => {
    if (!browserPreviewReasons.includes(reason)) browserPreviewReasons.push(reason);
    if (trigger && !triggers.includes(trigger)) triggers.push(trigger);
  };

  if (/\\documentclass(?:\[[^\]]*\])?\{acmart\}/.test(combinedText)) {
    addBrowserReason(`${BROWSER_ONLY_REASON_PREFIX} uses acmart`, 'acmart');
  }
  if (hasAny(combinedText, [/\\usepackage(?:\[[^\]]*\])?\{ctex\}/, /\\documentclass(?:\[[^\]]*\])?\{ctex[a-z]*\}/])) {
    recommendedEngine = 'xelatex';
    addBrowserReason(`${BROWSER_ONLY_REASON_PREFIX} uses ctex`, 'ctex');
  }
  if (hasAny(combinedText, [/\\usepackage(?:\[[^\]]*\])?\{fontspec\}/, /\\setmainfont\{/, /\\setsansfont\{/])) {
    recommendedEngine = 'xelatex';
    addBrowserReason(`${BROWSER_ONLY_REASON_PREFIX} uses fontspec/system fonts`, 'fontspec');
  }
  if (hasAny(combinedText, [/\\usepackage(?:\[[^\]]*\])?\{xeCJK\}/, /\\setCJKmainfont\{/])) {
    recommendedEngine = 'xelatex';
    addBrowserReason(`${BROWSER_ONLY_REASON_PREFIX} uses xeCJK`, 'xeCJK');
  }
  if (/\\usepackage(?:\[[^\]]*\])?\{unicode-math\}/.test(combinedText)) {
    recommendedEngine = recommendedEngine === 'pdflatex' ? 'xelatex' : recommendedEngine;
    addBrowserReason(`${BROWSER_ONLY_REASON_PREFIX} uses unicode-math`, 'unicode-math');
  }
  if (hasAny(combinedText, [/\\usepackage(?:\[[^\]]*\])?\{minted\}/, /\\begin\{minted\}/, /\\immediate\\write18/])) {
    requiresShellEscape = true;
    addBrowserReason(`${BROWSER_ONLY_REASON_PREFIX} requires shell-escape`, 'minted');
  }
  if (hasAny(combinedText, [/\\usepackage(?:\[[^\]]*\])?\{biblatex\}/, /\\addbibresource\{/])) {
    detectedBibTool = 'biber';
    addBrowserReason(`${BROWSER_ONLY_REASON_PREFIX} uses biblatex`, 'biblatex');
  } else if (bibliographyFiles.length > 0 || hasAny(combinedText, [/\\bibliographystyle\{/, /\\bibliography\{/])) {
    detectedBibTool = 'bibtex';
    addBrowserReason(`${BROWSER_ONLY_REASON_PREFIX} uses bibliography tooling`, 'bibliography');
  }
  if (hasAny(combinedText, [/\\usepackage(?:\[[^\]]*\])?\{tikz\}/, /\\usetikzlibrary\{/, /\\usepackage(?:\[[^\]]*\])?\{pgfplots\}/])) {
    addBrowserReason(`${BROWSER_ONLY_REASON_PREFIX} uses TikZ/PGF`, 'tikz');
  }
  if (hasAny(combinedText, [/\\usepackage(?:\[[^\]]*\])?\{glossaries\}/, /\\makeglossaries/, /\\printglossaries/])) {
    addBrowserReason(`${BROWSER_ONLY_REASON_PREFIX} uses glossaries`, 'glossaries');
  }
  if (hasAny(combinedText, [/\\makeindex/, /\\printindex/])) {
    addBrowserReason(`${BROWSER_ONLY_REASON_PREFIX} uses makeindex`, 'makeindex');
  }
  if (usedLatexmkRc) {
    addBrowserReason(`${BROWSER_ONLY_REASON_PREFIX} project provides .latexmkrc`, '.latexmkrc');
  }

  return {
    recommendedEngine,
    detectedBibTool,
    requiresShellEscape,
    suitableForBrowserPreview: browserPreviewReasons.length === 0,
    browserPreviewReasons,
    triggers,
    usedLatexmkRc,
  };
}

function firstAvailableEngine(capabilities: LatexCapabilities): Exclude<LatexEngine, 'auto'> | null {
  if (capabilities.local.pdflatex.available) return 'pdflatex';
  if (capabilities.local.xelatex.available) return 'xelatex';
  if (capabilities.local.lualatex.available) return 'lualatex';
  return null;
}

export function findExecutable(command: string): LatexToolCapability {
  const texLivePath = join(TEXBIN_PATH, command);
  if (existsSync(texLivePath)) return { available: true, path: texLivePath };

  const result = spawnSync('which', [command], { encoding: 'utf-8' });
  const resolvedPath = result.status === 0 ? result.stdout.trim() : '';
  if (resolvedPath) return { available: true, path: resolvedPath };

  return { available: false };
}

export function getLatexCapabilities(): LatexCapabilities {
  return {
    local: {
      latexmk: findExecutable('latexmk'),
      pdflatex: findExecutable('pdflatex'),
      xelatex: findExecutable('xelatex'),
      lualatex: findExecutable('lualatex'),
      bibtex: findExecutable('bibtex'),
      biber: findExecutable('biber'),
      makeindex: findExecutable('makeindex'),
      makeglossaries: findExecutable('makeglossaries'),
    },
    remote: {
      available: false,
    },
  };
}

export function buildLatexProfile(config: ProjectConfig, texPath?: string): LatexProfile {
  const fileConfig = readFastwriteBuildConfig(config.sectionsDir);
  const mainFile = detectMainFile(
    config.sectionsDir,
    texPath,
    config.mainFile,
    fileConfig?.mainFile
  );
  const mainFilePath = mainFile ? join(config.sectionsDir, mainFile) : null;
  const signals = inferProjectSignals(config.sectionsDir, mainFile);
  const preferredEngine = config.preferredEngine && config.preferredEngine !== 'auto'
    ? config.preferredEngine
    : fileConfig?.engine && fileConfig.engine !== 'auto'
      ? fileConfig.engine
      : signals.recommendedEngine;
  const shellEscape = typeof config.shellEscape === 'boolean'
    ? config.shellEscape
    : typeof fileConfig?.shellEscape === 'boolean'
      ? fileConfig.shellEscape
      : signals.requiresShellEscape;
  const bibTool = config.bibTool && config.bibTool !== 'auto'
    ? config.bibTool
    : fileConfig?.bibTool && fileConfig.bibTool !== 'auto'
      ? fileConfig.bibTool
      : signals.detectedBibTool;
  const effectiveEngine: Exclude<LatexEngine, 'auto'> = preferredEngine;

  return {
    mainFile,
    mainFilePath,
    recommendedEngine: signals.recommendedEngine,
    effectiveEngine,
    shellEscape,
    bibTool,
    suitableForBrowserPreview: signals.suitableForBrowserPreview,
    browserPreviewReasons: signals.browserPreviewReasons,
    triggers: signals.triggers,
    usedLatexmkRc: signals.usedLatexmkRc,
  };
}

function joinCommandOutput(result: ReturnType<typeof spawnSync>): string {
  return [result.stdout || '', result.stderr || '']
    .filter(Boolean)
    .join('\n')
    .trim();
}

function runCommand(command: string, args: string[], cwd: string): ReturnType<typeof spawnSync> {
  const normalizedEnv = { ...process.env };
  const preferredLocale = process.platform === 'darwin' ? 'en_US.UTF-8' : 'C';
  for (const key of ['LANG', 'LC_ALL', 'LC_CTYPE'] as const) {
    if (!normalizedEnv[key] || normalizedEnv[key] === 'C.UTF-8') {
      normalizedEnv[key] = preferredLocale;
    }
  }

  return spawnSync(command, args, {
    cwd,
    encoding: 'utf-8',
    timeout: 60000,
    maxBuffer: 1024 * 1024 * 10,
    env: normalizedEnv,
  });
}

function annotateDiagnostics(diagnostics: CompileDiagnostic[], provider: 'local'): CompileDiagnostic[] {
  return diagnostics.map((diagnostic) => ({
    ...diagnostic,
    provider,
  }));
}

function buildMissingToolDiagnostic(toolName: string, message: string, suggestion: string): CompileDiagnostic {
  return {
    id: `diag-tool-${toolName}`,
    severity: 'error',
    category: 'missing-tool',
    provider: 'local',
    toolName,
    message,
    raw: message,
    suggestion,
    firstFatal: true,
  };
}

export function compileLocally(config: ProjectConfig, texPath?: string): LocalCompileResult {
  const capabilities = getLatexCapabilities();
  const profile = buildLatexProfile(config, texPath);
  const mainFilePath = profile.mainFilePath;
  if (!mainFilePath || !fileExists(mainFilePath)) {
    const diagnostic: CompileDiagnostic = {
      id: 'diag-project-mainfile',
      severity: 'error',
      category: 'tex-error',
      provider: 'local',
      message: 'Main TeX file could not be resolved.',
      raw: 'Main TeX file could not be resolved.',
      suggestion: 'Choose a valid main file in Compilation Settings.',
      firstFatal: true,
    };
    return {
      success: false,
      provider: 'local',
      engine: profile.effectiveEngine,
      commandKind: 'direct-engine',
      diagnostics: [diagnostic],
      log: diagnostic.raw,
      warnings: 0,
      hadNonZeroExit: true,
    };
  }

  const texDir = dirname(mainFilePath);
  const texFilename = basename(mainFilePath);
  const outputName = texFilename.replace(/\.tex$/, '');
  const outputDir = join(texDir, 'output');
  const pdfPath = join(outputDir, `${outputName}.pdf`);
  const synctexPath = join(outputDir, `${outputName}.synctex.gz`);
  if (!existsSync(outputDir)) {
    mkdirSync(outputDir, { recursive: true });
  }
  let commandKind: CompileCommandKind = 'direct-engine';
  let fallbackReason: string | undefined;
  let result: ReturnType<typeof spawnSync>;
  const logSections: string[] = [];
  const appendLog = (label: string, commandResult: ReturnType<typeof spawnSync>) => {
    const output = joinCommandOutput(commandResult);
    if (output) {
      logSections.push(`=== ${label} ===\n${output}`);
    }
  };

  if (capabilities.local.latexmk.available && capabilities.local.latexmk.path) {
    commandKind = 'latexmk';
    const args = [
      profile.effectiveEngine === 'xelatex' ? '-xelatex' : profile.effectiveEngine === 'lualatex' ? '-lualatex' : '-pdf',
      '-synctex=1',
      '-interaction=nonstopmode',
      '-outdir=output',
    ];
    if (profile.shellEscape) args.push('-shell-escape');
    if (profile.bibTool === 'biber') args.push('-use-biber');
    if (profile.bibTool === 'bibtex') args.push('-bibtex');
    args.push(texFilename);
    result = runCommand(capabilities.local.latexmk.path, args, texDir);
    appendLog('latexmk', result);
  } else {
    const engineCapability = capabilities.local[profile.effectiveEngine];
    if (!engineCapability.available || !engineCapability.path) {
      const diagnostic = buildMissingToolDiagnostic(
        profile.effectiveEngine,
        `Local LaTeX engine ${profile.effectiveEngine} is not installed.`,
        'Install a full TeX Live / MacTeX / MiKTeX environment or switch to Fast Preview (WASM).',
      );
      return {
        success: false,
        provider: 'local',
        engine: profile.effectiveEngine,
        commandKind,
        diagnostics: [diagnostic],
        log: diagnostic.raw,
        warnings: 0,
        hadNonZeroExit: true,
      };
    }

    fallbackReason = 'latexmk is unavailable; used direct engine compile';
    const engineArgs = ['-output-directory=output', '-synctex=1', '-interaction=nonstopmode', '-file-line-error'];
    if (profile.shellEscape) engineArgs.push('-shell-escape');
    engineArgs.push(texFilename);

    const firstPass = runCommand(engineCapability.path, engineArgs, texDir);
    appendLog(`${profile.effectiveEngine} pass 1`, firstPass);
    result = firstPass;

    const auxPath = join(outputDir, `${outputName}.aux`);
    const bcfPath = join(outputDir, `${outputName}.bcf`);
    const hasAuxArtifacts = fileExists(auxPath) || fileExists(bcfPath);

    if (hasAuxArtifacts) {
      if (profile.bibTool === 'biber') {
        const biberCapability = capabilities.local.biber;
        if (!biberCapability.available || !biberCapability.path) {
          const diagnostic = buildMissingToolDiagnostic(
            'biber',
            'Biber is required for this project, but it is not installed locally.',
            'Install biber locally or switch to a machine with a full TeX distribution.',
          );
          return {
            success: false,
            provider: 'local',
            engine: profile.effectiveEngine,
            commandKind,
            fallbackReason,
            diagnostics: [diagnostic],
            log: [...logSections, diagnostic.raw].join('\n\n').trim(),
            warnings: 0,
            hadNonZeroExit: true,
          };
        }

        const biberResult = runCommand(biberCapability.path, [outputName], outputDir);
        appendLog('biber', biberResult);
        result = biberResult;
      } else if (profile.bibTool === 'bibtex') {
        const bibtexCapability = capabilities.local.bibtex;
        if (!bibtexCapability.available || !bibtexCapability.path) {
          const diagnostic = buildMissingToolDiagnostic(
            'bibtex',
            'BibTeX is required for this project, but it is not installed locally.',
            'Install bibtex locally or use a TeX distribution that includes bibliography tooling.',
          );
          return {
            success: false,
            provider: 'local',
            engine: profile.effectiveEngine,
            commandKind,
            fallbackReason,
            diagnostics: [diagnostic],
            log: [...logSections, diagnostic.raw].join('\n\n').trim(),
            warnings: 0,
            hadNonZeroExit: true,
          };
        }

        const bibtexResult = runCommand(bibtexCapability.path, [outputName], outputDir);
        appendLog('bibtex', bibtexResult);
        result = bibtexResult;
      }

      if (result.status === 0 || fileExists(pdfPath) || fileExists(auxPath) || fileExists(bcfPath)) {
        const secondPass = runCommand(engineCapability.path, engineArgs, texDir);
        appendLog(`${profile.effectiveEngine} pass 2`, secondPass);
        result = secondPass;

        const shouldRunThirdPass =
          profile.bibTool !== 'auto' ||
          /Rerun to get cross-references right|Label\(s\) may have changed/i.test(joinCommandOutput(secondPass));
        if (shouldRunThirdPass) {
          const thirdPass = runCommand(engineCapability.path, engineArgs, texDir);
          appendLog(`${profile.effectiveEngine} pass 3`, thirdPass);
          result = thirdPass;
        }
      }
    }
  }

  const compileLog = logSections.length > 0 ? logSections.join('\n\n') : joinCommandOutput(result);
  const diagnostics = annotateDiagnostics(parseCompileDiagnostics(compileLog, texDir, 'local'), 'local');
  const warningCount = diagnostics.filter((diagnostic) => diagnostic.severity === 'warning').length;

  return {
    success: result.status === 0 && fileExists(pdfPath),
    provider: 'local',
    engine: profile.effectiveEngine,
    commandKind,
    fallbackReason,
    diagnostics,
    log: compileLog,
    warnings: warningCount,
    hadNonZeroExit: result.status !== 0,
    pdfPath: fileExists(pdfPath) ? pdfPath : undefined,
    synctexPath: fileExists(synctexPath) ? synctexPath : null,
  };
}
