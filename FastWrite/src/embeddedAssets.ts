// Embedded web assets for single binary distribution
// These imports embed the files directly into the Bun binary

// @ts-ignore - Bun file embed
import indexHtml from "../web/dist/index.html" with { type: "file" };
// @ts-ignore - Bun file embed
import indexCss from "../web/dist/assets/index-B1KbLfCc.css" with { type: "file" };
// @ts-ignore - Bun file embed
import indexJs from "../web/dist/assets/index-Boh8_tkr.js" with { type: "file" };
// @ts-ignore - Bun file embed
import workerJs from "../web/dist/assets/worker-BH7JnVKG.js" with { type: "file" };
// @ts-ignore - Bun file embed
import editorWorkerJs from "../web/dist/assets/editor.worker-BctYAlYZ.js" with { type: "file" };
// @ts-ignore - Bun file embed
import opfsJs from "../web/dist/assets/OPFSBackend-gSESiBnj.js" with { type: "file" };
// @ts-ignore - Bun file embed
import blakeWasm from "../web/dist/assets/blake3_js_bg-BuxyNMCA.wasm" with { type: "file" };

// Bun embeds return file paths that work with Bun.file()
export const EMBEDDED_ASSETS: Record<string, any> = {
	"/": indexHtml,
	"/index.html": indexHtml,
	"/assets/index-B1KbLfCc.css": indexCss,
	"/assets/index-Boh8_tkr.js": indexJs,
	"/assets/worker-BH7JnVKG.js": workerJs,
	"/assets/editor.worker-BctYAlYZ.js": editorWorkerJs,
	"/assets/OPFSBackend-gSESiBnj.js": opfsJs,
	"/assets/blake3_js_bg-BuxyNMCA.wasm": blakeWasm,
};

export function isEmbeddedAsset(path: string): boolean {
	return path in EMBEDDED_ASSETS;
}

export function getEmbeddedAsset(path: string): any {
	return EMBEDDED_ASSETS[path];
}
