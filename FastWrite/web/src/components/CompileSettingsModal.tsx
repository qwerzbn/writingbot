import React, { useEffect, useMemo, useState } from 'react';
import { AlertCircle, FileText, Loader2, Save, Settings, X } from 'lucide-react';

import { api } from '../api';
import type { BibTool, CompileMode, FileNode, LatexCapabilities, LatexEngine, ProjectConfig } from '../types';

interface CompileSettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  projectId: string;
}

const DEFAULT_CONFIG: Partial<ProjectConfig> = {
  compileMode: 'auto',
  preferredEngine: 'auto',
  shellEscape: 'auto',
  bibTool: 'auto',
};

function flattenTexFiles(nodes: FileNode[]): string[] {
  let results: string[] = [];
  for (const node of nodes) {
    if (node.type === 'file' && node.name.endsWith('.tex')) {
      results.push(node.id);
    } else if (node.children) {
      results = [...results, ...flattenTexFiles(node.children)];
    }
  }
  return results.sort((a, b) => a.localeCompare(b, undefined, { numeric: true, sensitivity: 'base' }));
}

function capabilityLabel(capabilities: LatexCapabilities | null): string {
  if (!capabilities) return 'Checking local TeX tools...';

  const availableTools = Object.entries(capabilities.local)
    .filter(([, value]) => value.available)
    .map(([key]) => key);

  if (availableTools.length === 0) {
    return 'No local TeX toolchain detected. Auto mode will be limited to Fast Preview (WASM).';
  }

  return `Local toolchain detected: ${availableTools.join(', ')}`;
}

const CompileSettingsModal: React.FC<CompileSettingsModalProps> = ({ isOpen, onClose, projectId }) => {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [config, setConfig] = useState<Partial<ProjectConfig>>(DEFAULT_CONFIG);
  const [texFiles, setTexFiles] = useState<string[]>([]);
  const [capabilities, setCapabilities] = useState<LatexCapabilities | null>(null);

  useEffect(() => {
    if (!isOpen || !projectId) return;

    const loadData = async () => {
      setLoading(true);
      try {
        const [currentConfig, capabilityData, filesResponse] = await Promise.all([
          api.getProjectConfig(projectId),
          api.getLatexCapabilities(),
          fetch(`/api/projects/${projectId}/files`),
        ]);

        if (currentConfig) {
          setConfig({
            ...DEFAULT_CONFIG,
            ...currentConfig,
          });
        } else {
          setConfig(DEFAULT_CONFIG);
        }

        setCapabilities(capabilityData || null);

        if (filesResponse.ok) {
          const data = await filesResponse.json() as { files?: FileNode[] };
          setTexFiles(flattenTexFiles(data.files || []));
        } else {
          setTexFiles([]);
        }
      } catch (error) {
        console.error('Failed to load compilation settings:', error);
      } finally {
        setLoading(false);
      }
    };

    loadData();
  }, [isOpen, projectId]);

  const modeDescription = useMemo(() => {
    const mode = config.compileMode || 'auto';
    if (mode === 'browser-preview') {
      return 'Fast Preview (WASM) stays in the browser and is best for lightweight projects and demos.';
    }
    if (mode === 'local') {
      return 'Local mode always uses your machine’s TeX toolchain and prioritizes full project compatibility.';
    }
    return 'Auto mode profiles the project first: lightweight projects use Fast Preview, complex projects go straight to local compilation.';
  }, [config.compileMode]);

  const handleSave = async () => {
    setSaving(true);
    try {
      await api.saveProjectConfig(projectId, {
        compileMode: (config.compileMode || 'auto') as CompileMode,
        preferredEngine: (config.preferredEngine || 'auto') as LatexEngine,
        shellEscape: config.shellEscape ?? 'auto',
        bibTool: (config.bibTool || 'auto') as BibTool,
        mainFile: config.mainFile || undefined,
        kbId: config.kbId?.trim() || undefined,
      });
      onClose();
    } catch (error) {
      console.error('Failed to save compilation settings:', error);
    } finally {
      setSaving(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
      <div className="w-full max-w-xl overflow-hidden rounded-xl border border-slate-200 bg-white shadow-2xl">
        <div className="flex items-center justify-between border-b border-slate-100 bg-slate-50/60 px-4 py-3">
          <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-800">
            <Settings size={16} className="text-slate-500" />
            Compilation Settings
          </h3>
          <button
            onClick={onClose}
            className="rounded-lg p-1 text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-600"
          >
            <X size={16} />
          </button>
        </div>

        <div className="space-y-4 p-6">
          {loading ? (
            <div className="flex justify-center py-8">
              <Loader2 className="animate-spin text-blue-500" size={24} />
            </div>
          ) : (
            <>
              <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
                <div className="flex items-start gap-2 text-xs text-slate-600">
                  <AlertCircle size={14} className="mt-0.5 text-slate-400" />
                  <div>
                    <div className="font-medium text-slate-700">Local toolchain status</div>
                    <div className="mt-1">{capabilityLabel(capabilities)}</div>
                  </div>
                </div>
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                  Compile Mode
                </label>
                <select
                  value={config.compileMode || 'auto'}
                  onChange={(e) => setConfig((current) => ({ ...current, compileMode: e.target.value as CompileMode }))}
                  className="w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
                >
                  <option value="auto">Auto</option>
                  <option value="local">Local</option>
                  <option value="browser-preview">Fast Preview (WASM)</option>
                </select>
                <p className="text-[11px] text-slate-400">{modeDescription}</p>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <label className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                    Preferred Engine
                  </label>
                  <select
                    value={config.preferredEngine || 'auto'}
                    onChange={(e) => setConfig((current) => ({ ...current, preferredEngine: e.target.value as LatexEngine }))}
                    className="w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
                  >
                    <option value="auto">Auto</option>
                    <option value="pdflatex">pdfLaTeX</option>
                    <option value="xelatex">XeLaTeX</option>
                    <option value="lualatex">LuaLaTeX</option>
                  </select>
                </div>

                <div className="space-y-1.5">
                  <label className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                    Bibliography Tool
                  </label>
                  <select
                    value={config.bibTool || 'auto'}
                    onChange={(e) => setConfig((current) => ({ ...current, bibTool: e.target.value as BibTool }))}
                    className="w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
                  >
                    <option value="auto">Auto</option>
                    <option value="bibtex">BibTeX</option>
                    <option value="biber">Biber</option>
                  </select>
                </div>
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                  Shell Escape
                </label>
                <select
                  value={typeof config.shellEscape === 'boolean' ? String(config.shellEscape) : 'auto'}
                  onChange={(e) => {
                    const value = e.target.value;
                    setConfig((current) => ({
                      ...current,
                      shellEscape: value === 'auto' ? 'auto' : value === 'true',
                    }));
                  }}
                  className="w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
                >
                  <option value="auto">Auto</option>
                  <option value="true">Enabled</option>
                  <option value="false">Disabled</option>
                </select>
                <p className="text-[11px] text-slate-400">
                  Auto enables shell-escape only when the project profile detects packages like minted.
                </p>
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                  Main File
                </label>
                <div className="relative">
                  <FileText size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                  <select
                    value={config.mainFile || ''}
                    onChange={(e) => setConfig((current) => ({ ...current, mainFile: e.target.value || undefined }))}
                    className="w-full rounded-lg border border-slate-200 bg-slate-50 py-2 pl-9 pr-3 text-sm text-slate-700 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
                  >
                    {!config.mainFile && <option value="">Auto-detect main file</option>}
                    {texFiles.map((file) => (
                      <option key={file} value={file}>
                        {file}
                      </option>
                    ))}
                  </select>
                </div>
                <p className="text-[11px] text-slate-400">
                  Stored as a project-relative path so nested main documents compile correctly.
                </p>
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                  Knowledge Base ID
                </label>
                <input
                  type="text"
                  value={config.kbId || ''}
                  onChange={(e) => setConfig((current) => ({ ...current, kbId: e.target.value }))}
                  placeholder="Optional: enable Related Work evidence lookup"
                  className="w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
                />
              </div>
            </>
          )}
        </div>

        <div className="flex justify-end gap-2 border-t border-slate-100 bg-slate-50 px-4 py-3">
          <button
            onClick={onClose}
            className="rounded-lg px-3 py-1.5 text-xs font-medium text-slate-600 transition-colors hover:bg-slate-200 hover:text-slate-800"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={saving || loading}
            className="flex items-center gap-1.5 rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-medium text-white shadow-sm transition-colors hover:bg-blue-700 disabled:bg-blue-400"
          >
            {saving ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />}
            Save Settings
          </button>
        </div>
      </div>
    </div>
  );
};

export default CompileSettingsModal;
