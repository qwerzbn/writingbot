import { basename, normalize } from "node:path";

import type { CompileDiagnostic, CompileProvider } from "../web/src/types";

function normalizePath(value: string | undefined): string | undefined {
  if (!value) return undefined;
  return normalize(value.replace(/^\.\/+/, ""));
}

function resolveFilePath(pathValue: string | undefined, texDir: string): string | undefined {
  if (!pathValue) return undefined;
  const normalized = normalizePath(pathValue);
  if (!normalized) return undefined;
  if (normalized.startsWith("/")) return normalized;
  return normalize(`${texDir}/${normalized}`);
}

function buildId(index: number, filePath?: string, line?: number): string {
  const filePart = filePath ? basename(filePath) : "project";
  return `diag-${filePart}-${line || index}-${index}`;
}

function classifyDiagnostic(message: string): Pick<CompileDiagnostic, 'category' | 'packageName' | 'toolName' | 'suggestion'> {
  const missingPackageMatch = message.match(/File [`']([^`']+\.(?:sty|cls|bst|bbx|cbx))[`'] not found/i);
  if (missingPackageMatch) {
    const packageName = missingPackageMatch[1]?.replace(/\.(sty|cls|bst|bbx|cbx)$/i, '');
    return {
      category: 'missing-package',
      packageName,
      suggestion: 'Use Local compile for full TeX Live compatibility, or vendor the missing package into the project.',
    };
  }

  const missingToolMatch = message.match(/\b(biber|bibtex|makeindex|makeglossaries|pygmentize|latexmk)\b.*not found/i);
  if (missingToolMatch) {
    return {
      category: 'missing-tool',
      toolName: missingToolMatch[1]?.toLowerCase(),
      suggestion: 'Install the missing local tool or switch to a compile mode that provides it.',
    };
  }

  if (/fontspec|requires either XeTeX or LuaTeX|XeTeX|LuaTeX/i.test(message)) {
    return {
      category: 'engine-mismatch',
      suggestion: 'Switch to XeLaTeX or LuaLaTeX for this project.',
    };
  }

  if (/shell-escape|write18/i.test(message)) {
    return {
      category: 'shell-escape-required',
      suggestion: 'Enable shell-escape in Compilation Settings for packages like minted.',
    };
  }

  if (/font .* not loadable|font .* not found|metric .* not found/i.test(message)) {
    return {
      category: 'missing-font',
      suggestion: 'Install the required font locally or switch to a compatible engine.',
    };
  }

  if (/warning/i.test(message)) {
    return {
      category: 'warning',
    };
  }

  return {
    category: 'tex-error',
  };
}

export function parseCompileDiagnostics(log: string, texDir: string, provider?: CompileProvider): CompileDiagnostic[] {
  const diagnostics: CompileDiagnostic[] = [];
  const lines = log.split(/\r?\n/);
  let pendingFatal = false;

  for (let index = 0; index < lines.length; index++) {
    const raw = lines[index]?.trim();
    if (!raw) continue;

    if (raw.startsWith("!")) {
      const message = raw.replace(/^!\s*/, "").trim();
      const classification = classifyDiagnostic(message);
      diagnostics.push({
        id: buildId(index, undefined, undefined),
        severity: "error",
        message,
        raw,
        firstFatal: !pendingFatal,
        provider,
        ...classification,
      });
      pendingFatal = true;
      continue;
    }

    const fileMatch = raw.match(/^(.+?):(\d+):\s*(.+)$/);
    if (fileMatch) {
      const [, filePath, lineNumber, message] = fileMatch;
      if (!filePath || !lineNumber || !message) continue;
      const severity = /warning/i.test(message) ? "warning" : "error";
      const classification = classifyDiagnostic(message.trim());
      diagnostics.push({
        id: buildId(index, filePath, Number(lineNumber)),
        severity,
        filePath: resolveFilePath(filePath, texDir),
        line: Number(lineNumber),
        message: message.trim(),
        raw,
        firstFatal: severity === "error" && !pendingFatal,
        provider,
        ...classification,
      });
      if (severity === "error") pendingFatal = true;
      continue;
    }

    if (/warning/i.test(raw)) {
      const classification = classifyDiagnostic(raw);
      diagnostics.push({
        id: buildId(index, undefined, undefined),
        severity: "warning",
        message: raw,
        raw,
        provider,
        ...classification,
      });
    }
  }

  return diagnostics;
}
