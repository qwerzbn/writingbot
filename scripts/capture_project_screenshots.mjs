import { mkdir } from "node:fs/promises";
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath } from "node:url";

const APP_ORIGIN = "http://127.0.0.1:3000";
const API_ORIGIN = "http://127.0.0.1:5001";
const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(SCRIPT_DIR, "..");
const OUTPUT_DIR = path.join(REPO_ROOT, "docs", "assets");
const require = createRequire(path.join(REPO_ROOT, "web", "package.json"));
const { chromium } = require("playwright");

async function readJson(url) {
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`Failed to fetch ${url}: ${res.status}`);
  }
  return res.json();
}

async function waitForStable(page, timeout = 1500) {
  await page.waitForLoadState("networkidle").catch(() => {});
  await page.waitForTimeout(timeout);
}

async function capture(page, route, fileName, options = {}) {
  await page.goto(`${APP_ORIGIN}${route}`, { waitUntil: "domcontentloaded" });
  await waitForStable(page, options.waitMs ?? 1800);
  if (options.beforeShot) {
    await options.beforeShot(page);
    await waitForStable(page, options.afterActionWaitMs ?? 1200);
  }
  await page.screenshot({
    path: path.join(OUTPUT_DIR, fileName),
    fullPage: Boolean(options.fullPage),
  });
}

const [{ data: kbRows }, { data: notebookRows }, { data: conversationRows }] = await Promise.all([
  readJson(`${API_ORIGIN}/api/kbs`),
  readJson(`${API_ORIGIN}/api/notebooks`),
  readJson(`${API_ORIGIN}/api/conversations`),
]);

if (!Array.isArray(kbRows) || kbRows.length === 0) {
  throw new Error("No knowledge base found for screenshot capture.");
}
if (!Array.isArray(notebookRows) || notebookRows.length === 0) {
  throw new Error("No notebook found for screenshot capture.");
}
if (!Array.isArray(conversationRows) || conversationRows.length === 0) {
  throw new Error("No conversation found for screenshot capture.");
}

const kbId = kbRows[0].id;
const notebookId = notebookRows[0].id;
const conversationTitle = String(conversationRows[0].title || "").trim();

await mkdir(OUTPUT_DIR, { recursive: true });

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 2048, height: 1024 } });

try {
  await capture(page, "/", "dashboard-overview.png");
  await capture(page, "/knowledge", "knowledge-list.png");
  await capture(page, `/knowledge/${kbId}`, "knowledge-detail.png");
  await capture(page, "/chat", "chat-workspace.png", {
    beforeShot: async (chatPage) => {
      if (conversationTitle) {
        const item = chatPage.getByText(conversationTitle, { exact: true });
        if ((await item.count()) === 1) {
          await item.click();
        }
      }
    },
    afterActionWaitMs: 2200,
  });
  await capture(page, "/notebook", "notebook-list.png");
  await capture(page, `/notebook/${notebookId}`, "notebook-workspace.png", {
    waitMs: 2400,
  });
  await capture(page, "/co-writer", "co-writer-workspace.png", {
    waitMs: 3200,
  });
  await capture(page, "/settings", "settings-page.png");
} finally {
  await browser.close();
}
