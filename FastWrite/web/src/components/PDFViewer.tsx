import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Document, Page, pdfjs } from 'react-pdf';
import { ZoomIn, ZoomOut, RefreshCw, AlertCircle, FileWarning, Loader2, FolderOpen, ChevronUp, ChevronDown, ChevronDown as DropdownIcon, Settings } from 'lucide-react';
import 'react-pdf/dist/Page/AnnotationLayer.css';
import 'react-pdf/dist/Page/TextLayer.css';
import CompileSettingsModal from './CompileSettingsModal';
import { api } from '../api';
import * as latexCompiler from '../services/latexCompiler';
import type { CompileDiagnostic, CompileMode, CompileProvider, LatexCapabilities, LatexProfile } from '../types';

// Configure PDF.js worker
pdfjs.GlobalWorkerOptions.workerSrc = `//unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`;

interface PDFViewerProps {
	projectId: string;
	mainTexPath: string | null;
	onSyncToSource?: (filePath: string, line: number) => void;
	scrollTo?: { page: number; x: number; y: number } | null;
	compileMode?: CompileMode;
	onCompilerChange?: () => void;
	onCompilationDiagnostics?: (diagnostics: CompileDiagnostic[]) => void;
}

interface CompilationResult {
	success: boolean;
	pdfPath?: string;
	error?: string;
	synctexPath?: string;
	diagnostics?: CompileDiagnostic[];
	log?: string;
	warnings?: number;
	hadNonZeroExit?: boolean;
	provider?: CompileProvider;
	engine?: string;
	commandKind?: 'latexmk' | 'direct-engine';
	fallbackReason?: string;
}

interface LatexStatus {
	installed: boolean;
	version?: string;
	engine?: string;
}

import { forwardRef, useImperativeHandle } from 'react';

export interface PDFViewerRef {
	syncFromSelection: () => Promise<{ success: boolean; message?: string }>;
	compile: () => Promise<void>;
}

function hasLocalCompiler(capabilities: LatexCapabilities | null): boolean {
	if (!capabilities) return false;
	return Boolean(
		capabilities.local.latexmk.available ||
		capabilities.local.pdflatex.available ||
		capabilities.local.xelatex.available ||
		capabilities.local.lualatex.available
	);
}

function summarizeLocalTool(capabilities: LatexCapabilities | null): string {
	if (!capabilities) return 'No local compiler';
	if (capabilities.local.latexmk.available) return 'latexmk';
	if (capabilities.local.xelatex.available) return 'xelatex';
	if (capabilities.local.lualatex.available) return 'lualatex';
	if (capabilities.local.pdflatex.available) return 'pdflatex';
	return 'No local compiler';
}

function inferBrowserDiagnostics(log: string | null, provider: CompileProvider = 'browser-preview'): CompileDiagnostic[] {
	if (!log) return [];
	const diagnostics: CompileDiagnostic[] = [];
	const lines = log.split(/\r?\n/);

	for (let index = 0; index < lines.length; index++) {
		const raw = lines[index]?.trim();
		if (!raw) continue;

		const missingPackageMatch = raw.match(/File [`']([^`']+\.(?:sty|cls|bst|bbx|cbx))[`'] not found/i);
		if (missingPackageMatch) {
			diagnostics.push({
				id: `browser-diag-${index}`,
				severity: 'error',
				category: 'missing-package',
				provider,
				message: raw.replace(/^!\s*/, ''),
				raw,
				packageName: missingPackageMatch[1]?.replace(/\.(sty|cls|bst|bbx|cbx)$/i, ''),
				suggestion: 'Switch to Local compile for a full TeX Live environment.',
				firstFatal: diagnostics.filter((diagnostic) => diagnostic.severity === 'error').length === 0,
			});
			continue;
		}

		if (/shell-escape|write18/i.test(raw)) {
			diagnostics.push({
				id: `browser-diag-${index}`,
				severity: 'error',
				category: 'shell-escape-required',
				provider,
				message: raw.replace(/^!\s*/, ''),
				raw,
				suggestion: 'Enable shell-escape in Local mode for minted-like workflows.',
				firstFatal: diagnostics.filter((diagnostic) => diagnostic.severity === 'error').length === 0,
			});
			continue;
		}

		if (/fontspec|XeTeX|LuaTeX|unicode-math/i.test(raw)) {
			diagnostics.push({
				id: `browser-diag-${index}`,
				severity: 'error',
				category: 'engine-mismatch',
				provider,
				message: raw.replace(/^!\s*/, ''),
				raw,
				suggestion: 'Switch to Local compile with XeLaTeX or LuaLaTeX.',
				firstFatal: diagnostics.filter((diagnostic) => diagnostic.severity === 'error').length === 0,
			});
			continue;
		}

		if (/warning/i.test(raw)) {
			diagnostics.push({
				id: `browser-diag-${index}`,
				severity: 'warning',
				category: 'warning',
				provider,
				message: raw,
				raw,
			});
		}
	}

	return diagnostics;
}

const PDFViewer = forwardRef<PDFViewerRef, PDFViewerProps>(({ projectId, mainTexPath, onSyncToSource, scrollTo, compileMode, onCompilerChange, onCompilationDiagnostics }, ref) => {
	const [numPages, setNumPages] = useState<number>(0);
	// ...

	const [currentPage, setCurrentPage] = useState<number>(1);
	const [pageInputValue, setPageInputValue] = useState<string>('1');
	const [scale, setScale] = useState<number>(0.8);
	const [pdfUrl, setPdfUrl] = useState<string | null>(null);
	const [isCompiling, setIsCompiling] = useState(false);
	const [compilationError, setCompilationError] = useState<string | null>(null);
	const [compilationLog, setCompilationLog] = useState<string | null>(null);
	const [currentDiagnostics, setCurrentDiagnostics] = useState<CompileDiagnostic[]>([]);
	const [errorCount, setErrorCount] = useState<number>(0);
	const [showErrorLog, setShowErrorLog] = useState(false);
	const [latexStatus, setLatexStatus] = useState<LatexStatus | null>(null);
	const [isCheckingLatex, setIsCheckingLatex] = useState(true);
	const [isSettingsOpen, setIsSettingsOpen] = useState(false);
	const [clickedLocation, setClickedLocation] = useState<{ page: number; x: number; y: number } | null>(null);
	const [highlightBox, setHighlightBox] = useState<{ page: number; x: number; y: number; width: number; height: number; lineCount: number } | null>(null);
	const [wasmReady, setWasmReady] = useState(false);
	const [wasmInitError, setWasmInitError] = useState<string | null>(null);
	const [capabilities, setCapabilities] = useState<LatexCapabilities | null>(null);
	const [compileProfile, setCompileProfile] = useState<LatexProfile | null>(null);
	const [compileStageMessage, setCompileStageMessage] = useState<string | null>(null);
	const containerRef = useRef<HTMLDivElement>(null);
	const pageRefs = useRef<Map<number, HTMLDivElement>>(new Map());
	const pageHeightsRef = useRef<Map<number, number>>(new Map());
	const pdfBlobUrlRef = useRef<string | null>(null); // Track blob URLs for cleanup

	const currentCompileMode = compileMode || 'auto';

	const initWasmCompiler = useCallback(async () => {
		if (wasmReady) return true;
		try {
			await latexCompiler.init();
			setWasmReady(true);
			setWasmInitError(null);
			return true;
		} catch (err) {
			console.error('[LaTeX WASM] Init failed:', err);
			setWasmInitError(err instanceof Error ? err.message : 'WASM init failed');
			return false;
		}
	}, [wasmReady]);

	// Check local LaTeX capabilities and optionally prewarm the preview compiler.
	useEffect(() => {
		let cancelled = false;

		const loadEnvironment = async () => {
			setIsCheckingLatex(true);
			try {
				const capabilityData = await api.getLatexCapabilities();
				if (cancelled) return;

				setCapabilities(capabilityData || null);
				setLatexStatus({
					installed: hasLocalCompiler(capabilityData || null),
					engine: summarizeLocalTool(capabilityData || null),
				});

				if (currentCompileMode !== 'local') {
					await initWasmCompiler();
				}
			} catch (error) {
				console.error('Failed to check LaTeX capabilities:', error);
				if (!cancelled) {
					setCapabilities(null);
					setLatexStatus({ installed: false });
				}
			} finally {
				if (!cancelled) setIsCheckingLatex(false);
			}
		};

		loadEnvironment();

		return () => {
			cancelled = true;
			if (pdfBlobUrlRef.current) {
				URL.revokeObjectURL(pdfBlobUrlRef.current);
			}
		};
	}, [currentCompileMode, initWasmCompiler]);

	// Compile LaTeX — branches on isBrowserMode
	const compile = useCallback(async () => {
		if (!mainTexPath) return;

		setIsCompiling(true);
		setCompilationError(null);
		setCompilationLog(null);
		setCurrentDiagnostics([]);
		setErrorCount(0);
		setCompileStageMessage(null);
		onCompilationDiagnostics?.([]);

		try {
			const profile = await api.getLatexProfile(projectId, mainTexPath);
			setCompileProfile(profile || null);
			const resolvedMainTexPath = profile?.mainFilePath || mainTexPath;
			const localAvailable = hasLocalCompiler(capabilities);

			const compileInBrowser = async () => {
				const ready = await initWasmCompiler();
				if (!ready) {
					throw new Error(wasmInitError || 'WASM compiler is unavailable');
				}

				setCompileStageMessage('Fast Preview (WASM) running');

				const srcRes = await fetch(`/api/files/${encodeURIComponent(resolvedMainTexPath)}?projectId=${encodeURIComponent(projectId)}`);
				if (!srcRes.ok) throw new Error('Failed to fetch .tex source');
				const srcData = await srcRes.json() as { content: string };

				const filesRes = await fetch(`/api/projects/${projectId}/files`);
				const additionalFiles: Record<string, string | Uint8Array> = {};
				if (filesRes.ok) {
					const filesData = await filesRes.json() as { files?: Array<{ id?: string; name: string; type: string; path: string; children?: any[] }> };
					const flatFiles = flattenFileTree(filesData.files || []);

					const supportExts = ['.tex', '.bib', '.sty', '.cls', '.bbl', '.bst', '.bbx', '.cbx'];
					await Promise.allSettled(
						flatFiles
							.filter((file) => file.path !== resolvedMainTexPath && supportExts.some((ext) => file.name.endsWith(ext)))
							.map(async (file) => {
								const res = await fetch(`/api/files/${encodeURIComponent(file.path)}?projectId=${encodeURIComponent(projectId)}`);
								if (!res.ok) return;
								const data = await res.json() as { content: string };
								additionalFiles[file.id] = data.content;
							})
					);

					const binaryExts = ['.png', '.jpg', '.jpeg', '.gif', '.pdf', '.eps', '.bmp', '.svg'];
					await Promise.allSettled(
						flatFiles
							.filter((file) => binaryExts.some((ext) => file.name.toLowerCase().endsWith(ext)))
							.map(async (file) => {
								const res = await fetch(`/api/files/${encodeURIComponent(file.path)}?projectId=${encodeURIComponent(projectId)}&raw=true`);
								if (!res.ok) return;
								additionalFiles[file.id] = new Uint8Array(await res.arrayBuffer());
							})
					);
				}

				const hasAdditionalFiles = Object.keys(additionalFiles).length > 0;
				const result = await latexCompiler.compile(srcData.content, {
					additionalFiles,
					useCache: !hasAdditionalFiles,
				});

				const diagnostics = inferBrowserDiagnostics(result.log || result.error || null);
				setCurrentDiagnostics(diagnostics);
				onCompilationDiagnostics?.(diagnostics);

				if (result.success && result.pdf) {
					if (pdfBlobUrlRef.current) {
						URL.revokeObjectURL(pdfBlobUrlRef.current);
					}

					const pdfBytes = new Uint8Array(result.pdf as any);
					const blob = new Blob([pdfBytes], { type: 'application/pdf' });
					const url = URL.createObjectURL(blob);
					pdfBlobUrlRef.current = url;
					setPdfUrl(url);
					setCompilationError(null);
					setCompilationLog(result.log || null);
					setErrorCount(diagnostics.filter((diagnostic) => diagnostic.severity !== 'info').length);
					setCompileStageMessage('Fast Preview (WASM) completed');

					fetch(`/api/latex/save-pdf/${encodeURIComponent(projectId)}`, {
						method: 'POST',
						headers: { 'Content-Type': 'application/pdf' },
						body: pdfBytes,
					}).catch((err) => console.warn('[PDFViewer] Failed to save PDF to disk:', err));

					return { success: true as const };
				}

				const errorLog = result.error || result.log || 'Fast Preview (WASM) failed';
				setCompilationError(errorLog);
				setCompilationLog(result.log || errorLog);
				setErrorCount(Math.max(1, diagnostics.filter((diagnostic) => diagnostic.severity === 'error').length));
				return {
					success: false as const,
					errorLog,
					diagnostics,
				};
			};

			const compileLocallyOnServer = async (reason?: string) => {
				const reasonLabel = reason ? `Local compile running: ${reason}` : 'Local compile running';
				const profileLabel = profile ? `${profile.effectiveEngine}` : 'auto engine';
				setCompileStageMessage(`${reasonLabel} (${profile?.usedLatexmkRc ? '.latexmkrc aware' : 'auto profile'} · ${profileLabel})`);

				const response = await fetch('/api/latex/compile', {
					method: 'POST',
					headers: { 'Content-Type': 'application/json' },
					body: JSON.stringify({ projectId, texPath: resolvedMainTexPath })
				});

				const result = await response.json() as CompilationResult & { warnings?: number };
				const diagnostics = result.diagnostics || [];
				setCurrentDiagnostics(diagnostics);
				onCompilationDiagnostics?.(diagnostics);

				if (result.success && result.pdfPath) {
					setCompilationError(null);
					setCompilationLog(result.log || null);
					setPdfUrl(`/api/latex/pdf/${encodeURIComponent(projectId)}?t=${Date.now()}`);
					setErrorCount(diagnostics.filter((diagnostic) => diagnostic.severity !== 'info').length || result.warnings || 0);
					setCompileStageMessage(
						result.commandKind === 'latexmk'
							? `Local compile running with latexmk + ${result.engine}`
							: `Local compile running with ${result.engine}`
					);
					return;
				}

				const errorLog = result.log || result.error || 'Compilation failed';
				setCompilationError(errorLog);
				setCompilationLog(errorLog);
				setErrorCount(Math.max(1, diagnostics.filter((diagnostic) => diagnostic.severity === 'error').length));
				setCompileStageMessage(result.fallbackReason || reasonLabel);
			};

			if (currentCompileMode === 'browser-preview') {
				await compileInBrowser();
			} else if (currentCompileMode === 'local') {
				if (!localAvailable) {
					setCompilationError('No local LaTeX toolchain detected. Install TeX Live / MacTeX / MiKTeX or switch to Fast Preview (WASM).');
					setCompilationLog('No local LaTeX toolchain detected. Install TeX Live / MacTeX / MiKTeX or switch to Fast Preview (WASM).');
					setErrorCount(1);
					setCompileStageMessage('Local compile unavailable on this machine');
					return;
				}
				await compileLocallyOnServer();
			} else {
				const shouldUseBrowserPreview = profile?.suitableForBrowserPreview ?? true;
				if (shouldUseBrowserPreview) {
					try {
						const browserResult = await compileInBrowser();
						if (!browserResult.success && localAvailable) {
							const fallbackDiagnostic = browserResult.diagnostics.find((diagnostic) => diagnostic.severity === 'error');
							const fallbackReason = fallbackDiagnostic?.packageName
								? `Fell back to local compile: missing package ${fallbackDiagnostic.packageName}`
								: fallbackDiagnostic?.message
									? `Fell back to local compile: ${fallbackDiagnostic.message}`
									: 'Fell back to local compile after Fast Preview failed';
							await compileLocallyOnServer(fallbackReason);
						} else if (!browserResult.success && !localAvailable) {
							const limitedReason = profile?.browserPreviewReasons[0] || 'Local full engine unavailable. Current session is limited to Fast Preview (WASM).';
							setCompileStageMessage(limitedReason);
						}
					} catch (browserError) {
						if (localAvailable) {
							const reason = browserError instanceof Error
								? `Fell back to local compile: ${browserError.message}`
								: 'Fell back to local compile after Fast Preview initialization failed';
							await compileLocallyOnServer(reason);
						} else {
							throw browserError;
						}
					}
				} else if (localAvailable) {
					await compileLocallyOnServer(profile?.browserPreviewReasons[0] || 'Skipped browser preview for this project profile');
				} else {
					setCompileStageMessage(`Local full engine unavailable. Current session is limited to Fast Preview (WASM). ${profile?.browserPreviewReasons[0] || ''}`.trim());
					await compileInBrowser();
				}
			}
		} catch (error) {
			setCurrentDiagnostics([]);
			onCompilationDiagnostics?.([]);
			setCompilationError(error instanceof Error ? error.message : 'Compilation failed');
			setCompilationLog(error instanceof Error ? error.message : 'Compilation failed');
			setErrorCount(1);
		} finally {
			setIsCompiling(false);
		}
	}, [projectId, mainTexPath, capabilities, initWasmCompiler, wasmInitError, currentCompileMode, onCompilationDiagnostics]);

	// Auto-compile when tex path changes
	useEffect(() => {
		if (mainTexPath && !isCheckingLatex) {
			compile();
		}
	}, [mainTexPath, isCheckingLatex, compile]);

	// Determine if we should hide extra controls based on container width
	const [hideExtras, setHideExtras] = useState(false);

	useEffect(() => {
		if (!containerRef.current) return;
		const resizeObserver = new ResizeObserver(entries => {
			for (const entry of entries) {
				setHideExtras(entry.contentRect.width < 350);
			}
		});
		resizeObserver.observe(containerRef.current);
		return () => resizeObserver.disconnect();
	}, []);

	// Handle scroll to sync location with highlight box
	useEffect(() => {
		if (scrollTo) {
			// Check if y coordinate is near page bottom (synctex returns ~842 for A4 page height)
			// If y > 750, content likely wrapped to next page
			let targetPage = scrollTo.page;
			let targetY = scrollTo.y;

			if (pageRefs.current.has(targetPage)) {
				const pageEl = pageRefs.current.get(targetPage);
				if (pageEl) {
					pageEl.scrollIntoView({ behavior: 'smooth', block: 'center' });

					// Set highlight box at the adjusted location
					const w = (scrollTo as any).width || 300;
					const h = (scrollTo as any).height || 15;
					const lineCount = (scrollTo as any).lineCount || 1;
					setHighlightBox({ page: targetPage, x: scrollTo.x, y: targetY, width: w, height: h, lineCount });

					// Clear highlight after 2 seconds
					setTimeout(() => {
						setHighlightBox(null);
					}, 2000);
				}
			}
		}
	}, [scrollTo, numPages]);

	// Handle PDF load success
	const onDocumentLoadSuccess = ({ numPages }: { numPages: number }) => {
		setNumPages(numPages);
	};

	// Handle click on PDF - store location for later sync (don't sync immediately)
	const handlePageClick = (event: React.MouseEvent<HTMLDivElement>, pageNumber: number) => {
		if (!pdfUrl) return;

		const pageElement = pageRefs.current.get(pageNumber);
		if (!pageElement) return;

		const rect = pageElement.getBoundingClientRect();
		const x = event.clientX - rect.left;
		const y = event.clientY - rect.top;

		// Normalize coordinates to PDF units and store
		const pdfX = x / scale;
		const pdfY = y / scale;

		setClickedLocation({ page: pageNumber, x: pdfX, y: pdfY });
	};

	// Expose sync functionality and compile to parent
	useImperativeHandle(ref, () => ({
		compile: async () => {
			await compile(); // Reuse existing compile function
		},
		syncFromSelection: async () => {
			console.log('[PDFViewer] syncFromSelection called');
			if (!onSyncToSource || !pdfUrl) {
				console.warn('[PDFViewer] Missing onSyncToSource or pdfUrl');
				return { success: false, message: 'PDF not loaded' };
			}

			// 1. First priority: use stored clicked location
			if (clickedLocation) {
				await performSync(clickedLocation.page, clickedLocation.x, clickedLocation.y);
				return { success: true, message: 'Synced from clicked location' };
			}

			// 2. Try to find the selected text in the PDF
			const selection = window.getSelection();
			if (selection && selection.rangeCount > 0) {
				const range = selection.getRangeAt(0);
				const rect = range.getBoundingClientRect();

				// Find which page this selection belongs to
				let pageElement = range.startContainer.parentElement;
				while (pageElement && !pageElement.classList.contains('react-pdf__Page')) {
					pageElement = pageElement.parentElement;
				}

				if (pageElement) {
					// Extract page number from data attribute or aria-label if possible,
					// but react-pdf usually puts it in a clear attribute structure.
					// We'll trust our pageRefs map to find the page number by comparing elements.
					let pageNumber = -1;
					for (const [p, el] of Array.from(pageRefs.current.entries())) {
						if (el.contains(pageElement)) {
							pageNumber = p;
							break;
						}
					}

					if (pageNumber !== -1) {
						// Found the page. Calculate relative coordinates.
						// The 'pageElement' we found covers the page content.
						// However, 'pageRefs' stores the wrapper div.
						// We need the bounding rect of the actual page content to measure offset.
						const pageRect = pageElement.getBoundingClientRect();

						// Coordinates relative to page
						const x = rect.left - pageRect.left;
						const y = rect.top - pageRect.top;

						// Normalize to PDF units
						const pdfX = x / scale;
						const pdfY = y / scale;

						await performSync(pageNumber, pdfX, pdfY);
						return { success: true };
					}
				}
			}

			// 3. Fallback: Sync from the center of the currently visible viewport
			// We can use the container's center point
			if (containerRef.current) {
				const containerRect = containerRef.current.getBoundingClientRect();
				const centerX = containerRect.left + containerRect.width / 2;
				const centerY = containerRect.top + containerRect.height / 2;

				// Find element at center
				const elements = document.elementsFromPoint(centerX, centerY);
				const pageWrapper = elements.find(el => el.classList.contains('react-pdf__Page'));

				if (pageWrapper) {
					// Find which page number this corresponds to
					let pageNumber = -1;
					let pageElement = pageWrapper as HTMLElement;

					// Often elementsFromPoint hits a child, so traverse up
					while (pageElement && !pageElement.classList.contains('react-pdf__Page')) {
						pageElement = pageElement.parentElement as HTMLElement;
					}

					if (pageElement) {
						for (const [p, el] of Array.from(pageRefs.current.entries())) {
							if (el.contains(pageElement)) {
								pageNumber = p;
								break;
							}
						}
					}

					if (pageNumber !== -1) {
						const pageRect = pageElement.getBoundingClientRect();
						const x = centerX - pageRect.left;
						const y = centerY - pageRect.top;
						const pdfX = x / scale;
						const pdfY = y / scale;
						await performSync(pageNumber, pdfX, pdfY);
						return { success: true, message: 'Synced from visible page' };
					}
				}
			}
			return { success: false, message: 'Could not determine sync location' };
		}
	}));

	const performSync = async (pageNumber: number, pdfX: number, pdfY: number) => {
		try {
			const response = await fetch('/api/latex/synctex', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({
					projectId,
					page: pageNumber,
					x: pdfX,
					y: pdfY
				})
			});

			if (response.ok) {
				const result = await response.json() as { filePath: string; line: number };
				if (result.filePath && result.line) {
					onSyncToSource?.(result.filePath, result.line);
				}
			}
		} catch (error) {
			console.error('SyncTeX lookup failed:', error);
		}
	};

	// Zoom controls
	const zoomIn = () => setScale(prev => Math.min(2.5, prev + 0.2));
	const zoomOut = () => setScale(prev => Math.max(0.4, prev - 0.2));

	// Render all pages for continuous scrolling
	const renderPages = () => {
		const pages = [];
		for (let i = 1; i <= numPages; i++) {
			const showHighlight = highlightBox && highlightBox.page === i;
			pages.push(
				<div
					key={i}
					ref={(el) => { if (el) pageRefs.current.set(i, el); }}
					className="mb-4 shadow-lg cursor-pointer hover:shadow-xl transition-shadow relative"
					onClick={(e) => handlePageClick(e, i)}
				>
					<Page
						pageNumber={i}
						scale={scale}
						renderTextLayer={true}
						renderAnnotationLayer={true}
						className="bg-white"
						onLoadSuccess={(page) => {
							pageHeightsRef.current.set(i, page.originalHeight);
						}}
					/>
					{/* Highlight box for text-to-PDF sync */}
					{showHighlight && (() => {
						// Synctex coordinates are bottom-up (0,0 is bottom-left)
						// Web coordinates are top-down (0,0 is top-left)
						// We need to invert the Y coordinate using the page height
						const pageHeight = pageHeightsRef.current.get(i) || 842; // Default to A4 (842pt) if unknown

						// Invert Y: newY = pageHeight - synctexY
						// And apply scale
						const visualY = (pageHeight - highlightBox.y);
						const topPos = Math.max(0, visualY * scale - 15);

						const count = highlightBox.lineCount || 1;
						// Width logic can be improved but keeping simple for now
						const boxHeight = Math.max(20, count * 15 * scale);

						return (
							<div
								className="absolute pointer-events-none"
								style={{
									left: '10%',
									top: topPos,
									width: '80%',
									height: boxHeight,
									background: 'rgba(59, 130, 246, 0.2)',
									border: '3px solid #3b82f6',
									borderRadius: 6,
									boxShadow: '0 0 15px rgba(59, 130, 246, 0.5)'
								}}
							/>
						);
					})()}
				</div>
			);
		}
		return pages;
	};

	// Helper: flatten file tree for WASM compilation
	function flattenFileTree(nodes: Array<{ id?: string; name: string; type: string; path: string; children?: any[] }>): Array<{ id: string; name: string; path: string }> {
		let results: Array<{ id: string; name: string; path: string }> = [];
		for (const node of nodes) {
			if (node.type === 'file') {
				results.push({ id: node.id || node.name, name: node.name, path: node.path || node.name });
			} else if (node.children) {
				results = [...results, ...flattenFileTree(node.children)];
			}
		}
		return results;
	}

		// Show loading while checking LaTeX
		if (isCheckingLatex) {
			return (
				<div className="flex flex-col items-center justify-center h-full bg-slate-200 text-slate-500">
					<Loader2 size={32} className="animate-spin mb-3" />
					<p className="text-sm">Checking compilation environment...</p>
				</div>
			);
		}

		// Show WASM init error when preview mode is required.
		if (currentCompileMode === 'browser-preview' && wasmInitError) {
			return (
				<div className="flex flex-col items-center justify-center h-full bg-slate-200 p-6">
					<AlertCircle size={48} className="text-red-500 mb-4" />
					<h3 className="text-lg font-semibold text-slate-700 mb-2">Fast Preview Unavailable</h3>
					<p className="text-sm text-slate-500 text-center mb-4 max-w-xs">
						The browser preview compiler could not be initialized on this machine.
					</p>
					<pre className="text-xs text-red-600 bg-white p-3 rounded shadow max-w-md overflow-auto whitespace-pre-wrap mb-4">
						{wasmInitError}
					</pre>
					<div className="bg-white rounded-lg p-4 shadow-sm border border-slate-200 max-w-md">
					<p className="text-xs font-medium text-slate-500 mb-2">Install LaTeX locally as an alternative:</p>
					<ul className="text-xs text-slate-500 space-y-1">
						<li><strong>macOS:</strong> <code className="bg-slate-100 px-1 rounded">brew install --cask mactex</code></li>
						<li><strong>Windows:</strong> Install MiKTeX or TeX Live</li>
						<li><strong>Linux:</strong> <code className="bg-slate-100 px-1 rounded">sudo apt install texlive-full</code></li>
					</ul>
				</div>
			</div>
			);
		}

		// Show installation guide if Local mode was requested without a local toolchain.
		if (currentCompileMode === 'local' && !latexStatus?.installed) {
			const switchToPreview = async () => {
				try {
					await fetch(`/api/projects/${encodeURIComponent(projectId)}/config`, {
						method: 'POST',
						headers: { 'Content-Type': 'application/json' },
						body: JSON.stringify({ compileMode: 'browser-preview' })
					});
					onCompilerChange?.();
				} catch (error) {
					console.error('Failed to switch compiler:', error);
				}
		};

		return (
				<div className="flex flex-col items-center justify-center h-full bg-slate-200 p-6">
					<FileWarning size={48} className="text-amber-500 mb-4" />
					<h3 className="text-lg font-semibold text-slate-700 mb-2">Local Full Compile Unavailable</h3>
					<p className="text-sm text-slate-500 text-center mb-4 max-w-xs">
						Local mode needs a TeX Live / MacTeX / MiKTeX toolchain. You can switch to Fast Preview (WASM), but it only supports lightweight projects.
					</p>
					<button
						onClick={switchToPreview}
						className="mb-4 px-5 py-2.5 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-colors font-medium text-sm shadow-sm"
					>
						Switch to Fast Preview (WASM)
					</button>
					<div className="bg-white rounded-lg p-4 shadow-sm border border-slate-200 max-w-md">
						<p className="text-xs font-medium text-slate-500 mb-2">Or install locally:</p>
					<ul className="text-xs text-slate-500 space-y-1">
						<li><strong>macOS:</strong> <code className="bg-slate-100 px-1 rounded">brew install --cask mactex</code></li>
						<li><strong>Windows:</strong> Install MiKTeX or TeX Live</li>
						<li><strong>Linux:</strong> <code className="bg-slate-100 px-1 rounded">sudo apt install texlive-full</code></li>
					</ul>
				</div>
				</div>
			);
		}

	// Show empty state if no tex file selected
	if (!mainTexPath) {
		return (
			<div className="flex flex-col items-center justify-center h-full bg-slate-200 text-slate-400">
				<FileWarning size={48} className="mb-3 text-slate-300" />
				<p className="text-sm">Select a .tex file to preview PDF</p>
			</div>
		);
	}

	// Open PDF folder in Finder
	const revealInFinder = async () => {
		try {
			await fetch(`/api/latex/reveal/${encodeURIComponent(projectId)}`, { method: 'POST' });
		} catch (error) {
			console.error('Failed to reveal PDF:', error);
		}
	};



	// Page navigation
	const goToPrevPage = () => {
		if (currentPage > 1) {
			const newPage = currentPage - 1;
			setCurrentPage(newPage);
			setPageInputValue(String(newPage));
			scrollToPage(newPage);
		}
	};

	const goToNextPage = () => {
		if (currentPage < numPages) {
			const newPage = currentPage + 1;
			setCurrentPage(newPage);
			setPageInputValue(String(newPage));
			scrollToPage(newPage);
		}
	};

	const scrollToPage = (page: number) => {
		const pageEl = pageRefs.current.get(page);
		if (pageEl) {
			pageEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
		}
	};

	const handlePageInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
		setPageInputValue(e.target.value);
	};

	const handlePageInputSubmit = (e: React.KeyboardEvent<HTMLInputElement>) => {
		if (e.key === 'Enter') {
			const page = parseInt(pageInputValue, 10);
			if (page >= 1 && page <= numPages) {
				setCurrentPage(page);
				scrollToPage(page);
			} else {
				setPageInputValue(String(currentPage));
			}
		}
	};

	return (
		<div className="flex flex-col h-full bg-slate-200" ref={containerRef}>
			{/* Toolbar - Overleaf style - Compact */}
			<div className="flex items-center justify-between px-2 bg-white border-b border-slate-200 shadow-sm shrink-0 h-10">
				{/* Left: Recompile button with error badge */}
					<div className="flex items-center">
						<button
							onClick={compile}
							disabled={isCompiling}
							className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-white bg-green-600 hover:bg-green-700 disabled:bg-green-400 rounded transition-colors shadow-sm"
						>
							<RefreshCw size={12} className={isCompiling ? 'animate-spin' : ''} />
							{isCompiling ? 'Compiling...' : 'Recompile'}
						</button>

						<span className="ml-2 rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-[11px] font-medium text-slate-600">
							{currentCompileMode === 'browser-preview' ? 'Fast Preview' : currentCompileMode === 'local' ? 'Local' : 'Auto'}
						</span>

						<button
							onClick={() => setIsSettingsOpen(true)}
							className="p-1.5 ml-2 text-slate-500 hover:text-slate-700 hover:bg-slate-100 rounded transition-colors"
							title="Compilation Settings"
					>
						<Settings size={16} />
					</button>

					{/* Error badge */}
					{errorCount > 0 && (
						<button
							onClick={() => setShowErrorLog(!showErrorLog)}
							className="flex items-center gap-1 px-2 py-0.5 text-xs font-medium text-white bg-red-500 hover:bg-red-600 rounded ml-2"
							title="View compilation errors"
						>
							{errorCount}
						</button>
					)}

					{pdfUrl && !hideExtras && (
						<button
							onClick={revealInFinder}
							className="p-1.5 text-gray-500 hover:text-gray-700 hover:bg-gray-200 rounded ml-1"
							title="Open in Finder"
						>
							<FolderOpen size={16} />
						</button>
					)}
				</div>

				{/* Center: Page navigation */}
				{pdfUrl && numPages > 0 && !hideExtras && (
					<div className="flex items-center gap-1">
						<button
							onClick={goToPrevPage}
							disabled={currentPage <= 1}
							className="p-1 text-gray-500 hover:text-gray-700 hover:bg-gray-200 disabled:text-gray-300 disabled:hover:bg-transparent rounded"
							title="Previous page"
						>
							<ChevronUp size={16} />
						</button>
						<button
							onClick={goToNextPage}
							disabled={currentPage >= numPages}
							className="p-1 text-gray-500 hover:text-gray-700 hover:bg-gray-200 disabled:text-gray-300 disabled:hover:bg-transparent rounded"
							title="Next page"
						>
							<ChevronDown size={16} />
						</button>
						<input
							type="text"
							value={pageInputValue}
							onChange={handlePageInputChange}
							onKeyDown={handlePageInputSubmit}
							className="w-8 px-1 py-0.5 text-xs text-center border border-gray-300 rounded focus:outline-none focus:border-blue-500"
						/>
						<span className="text-xs text-gray-500">/ {numPages}</span>
					</div>
				)}

				{/* Right: Zoom controls */}
				{pdfUrl && !hideExtras && (
					<div className="flex items-center gap-0.5">
						<button
							onClick={zoomOut}
							className="p-1.5 text-gray-500 hover:text-gray-700 hover:bg-gray-200 rounded"
							title="Zoom out"
						>
							<ZoomOut size={16} />
						</button>
						<span className="text-xs text-gray-600 w-10 text-center">{Math.round(scale * 100)}%</span>
						<button
							onClick={zoomIn}
							className="p-1.5 text-gray-500 hover:text-gray-700 hover:bg-gray-200 rounded"
							title="Zoom in"
						>
							<ZoomIn size={16} />
						</button>
					</div>
					)}
				</div>

				{(compileStageMessage || (currentCompileMode === 'auto' && compileProfile && !compileProfile.suitableForBrowserPreview)) && (
					<div className="border-b border-slate-200 bg-slate-50 px-3 py-2 text-[11px] text-slate-600">
						<div className="flex flex-wrap items-center gap-x-3 gap-y-1">
							{compileStageMessage && <span className="font-medium text-slate-700">{compileStageMessage}</span>}
							{compileProfile?.mainFile && <span className="text-slate-500">Main file: {compileProfile.mainFile}</span>}
							{currentCompileMode === 'auto' && compileProfile && !compileProfile.suitableForBrowserPreview && compileProfile.browserPreviewReasons[0] && (
								<span className="text-amber-600">{compileProfile.browserPreviewReasons[0]}</span>
							)}
						</div>
					</div>
				)}

				{/* Error log panel */}
				{showErrorLog && (compilationLog || compilationError) && (
					<div className="bg-red-50 border-b border-red-200 p-3 max-h-40 overflow-auto">
					<div className="flex justify-between items-start mb-2">
						<span className="text-sm font-medium text-red-700">Compilation Log</span>
						<button
							onClick={() => setShowErrorLog(false)}
							className="text-red-500 hover:text-red-700 text-xs"
						>
								Close
							</button>
						</div>
						{currentDiagnostics.length > 0 && (
							<div className="mb-3 space-y-2">
								{currentDiagnostics.slice(0, 4).map((diagnostic) => (
									<div key={diagnostic.id} className="rounded-md border border-red-100 bg-white/80 px-2 py-1.5 text-xs text-red-700">
										<div className="font-medium">{diagnostic.message}</div>
										<div className="mt-0.5 text-red-500">
											{diagnostic.category || diagnostic.severity}
											{diagnostic.suggestion ? ` · ${diagnostic.suggestion}` : ''}
										</div>
									</div>
								))}
							</div>
						)}
						<pre className="text-xs text-red-600 whitespace-pre-wrap font-mono">{compilationLog || compilationError}</pre>
					</div>
				)}

			{/* PDF Content - Continuous Scrolling */}
			<div
				ref={containerRef}
				className="flex-1 overflow-auto flex flex-col items-center bg-slate-300 p-4"
			>
					{compilationError ? (
						<div className="flex flex-col items-center justify-center text-center p-6 h-full overflow-auto">
							<AlertCircle size={48} className="text-red-500 mb-3 flex-shrink-0" />
							<p className="text-sm text-red-600 mb-2 flex-shrink-0">Compilation Error</p>

							{currentDiagnostics.some((diagnostic) => diagnostic.category === 'missing-package') && (
								<div className="mb-4 p-3 bg-yellow-50 border border-yellow-200 rounded-lg max-w-md text-left flex-shrink-0">
									<p className="text-xs font-semibold text-yellow-800 mb-1">Missing Package Detected</p>
									<p className="text-xs text-yellow-700">
										{currentDiagnostics.find((diagnostic) => diagnostic.category === 'missing-package')?.suggestion || 'Switch to Local compile for a full TeX Live environment.'}
									</p>
								</div>
							)}

							{currentDiagnostics.length > 0 && (
								<div className="mb-4 flex w-full max-w-md flex-col gap-2 text-left">
									{currentDiagnostics.slice(0, 3).map((diagnostic) => (
										<div key={diagnostic.id} className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs text-slate-700 shadow-sm">
											<div className="font-medium text-slate-800">{diagnostic.message}</div>
											<div className="mt-1 text-slate-500">
												{diagnostic.category || diagnostic.severity}
												{diagnostic.suggestion ? ` · ${diagnostic.suggestion}` : ''}
											</div>
										</div>
									))}
								</div>
							)}

							<pre className="text-xs text-slate-600 bg-white p-3 rounded shadow max-w-md overflow-auto whitespace-pre-wrap text-left w-full">
								{compilationError}
							</pre>
						</div>
				) : isCompiling ? (
					<div className="flex flex-col items-center justify-center h-full">
						<Loader2 size={48} className="animate-spin text-blue-500 mb-3" />
						<p className="text-sm text-slate-600">Compiling LaTeX...</p>
					</div>
				) : pdfUrl ? (
					<Document
						file={pdfUrl}
						onLoadSuccess={onDocumentLoadSuccess}
						loading={
							<div className="flex items-center gap-2 text-slate-500">
								<Loader2 size={20} className="animate-spin" />
								<span className="text-sm">Loading PDF...</span>
							</div>
						}
						error={
							<div className="text-center text-red-500">
								<AlertCircle size={32} className="mx-auto mb-2" />
								<p className="text-sm">Failed to load PDF</p>
							</div>
						}
					>
						{renderPages()}
					</Document>
				) : (
					<div className="flex flex-col items-center justify-center h-full text-slate-500">
						<FileWarning size={48} className="mb-3 text-slate-400" />
						<p className="text-sm">Click "Compile" to generate PDF</p>
					</div>
				)}
			</div>
			<CompileSettingsModal
				isOpen={isSettingsOpen}
				onClose={() => setIsSettingsOpen(false)}
				projectId={projectId}
			/>
		</div>
	);
}); // Close forwardRef

export default PDFViewer;
