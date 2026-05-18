import type { GlobalLLMConfig } from "../web/src/types";

const DEFAULT_WRITINGBOT_BASE_URL = "http://localhost:5001";

function trimTrailingSlash(value: string): string {
  return value.replace(/\/+$/, "");
}

export function getWritingBotBaseUrl(): string {
  return trimTrailingSlash(
    process.env.WRITINGBOT_SETTINGS_BASE_URL ||
      process.env.WRITINGBOT_BASE_URL ||
      DEFAULT_WRITINGBOT_BASE_URL
  );
}

export function maskSecret(value: string): string {
  if (!value) return "";
  if (value.length <= 8) return "*".repeat(value.length);
  if (value.length <= 12) return `${value.slice(0, 2)}***${value.slice(-2)}`;
  return `${value.slice(0, 4)}...${value.slice(-4)}`;
}

async function parseJsonResponse<T>(response: Response): Promise<T> {
  const data = await response.json();
  return data as T;
}

export async function fetchGlobalLLMConfig(baseUrl = getWritingBotBaseUrl()): Promise<GlobalLLMConfig> {
  const response = await fetch(`${baseUrl}/api/settings/llm`);
  if (!response.ok) {
    throw new Error(`WritingBot settings unavailable (${response.status})`);
  }

  const payload = await parseJsonResponse<{ success?: boolean; data?: GlobalLLMConfig; detail?: string }>(response);
  if (!payload.success || !payload.data) {
    throw new Error(payload.detail || "WritingBot settings returned an invalid payload");
  }
  return payload.data;
}

export async function fetchMaskedGlobalLLMConfig(baseUrl = getWritingBotBaseUrl()): Promise<GlobalLLMConfig> {
  const config = await fetchGlobalLLMConfig(baseUrl);
  return {
    ...config,
    api_key: maskSecret(config.api_key),
  };
}

export async function proxyLLMTest(
  settings?: Partial<GlobalLLMConfig>,
  baseUrl = getWritingBotBaseUrl()
): Promise<unknown> {
  const effectiveSettings = settings?.provider
    ? settings
    : await fetchGlobalLLMConfig(baseUrl);

  const response = await fetch(`${baseUrl}/api/settings/llm/test`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(effectiveSettings),
  });

  const payload = await parseJsonResponse<{ success?: boolean; error?: string } & Record<string, unknown>>(response);
  if (!response.ok) {
    throw new Error(`WritingBot settings test failed (${response.status})`);
  }
  if (payload.success === false) {
    throw new Error(payload.error || "WritingBot settings test failed");
  }
  return payload;
}
