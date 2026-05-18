import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  fetchMaskedGlobalLLMConfig,
  getWritingBotBaseUrl,
  maskSecret,
  proxyLLMTest,
} from './writingbotSettings';

describe('writingbotSettings', () => {
  const originalBaseUrl = process.env.WRITINGBOT_SETTINGS_BASE_URL;
  const originalFetch = globalThis.fetch;

  afterEach(() => {
    globalThis.fetch = originalFetch;
    if (originalBaseUrl === undefined) {
      delete process.env.WRITINGBOT_SETTINGS_BASE_URL;
    } else {
      process.env.WRITINGBOT_SETTINGS_BASE_URL = originalBaseUrl;
    }
  });

  it('reads and masks the global LLM config from WritingBot', async () => {
    process.env.WRITINGBOT_SETTINGS_BASE_URL = 'http://writer.test/';
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({
        success: true,
        data: {
          provider: 'openai',
          base_url: 'https://api.openai.com/v1',
          model: 'gpt-5.4',
          api_key: 'sk-test-1234567890',
        },
      }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    );
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    const config = await fetchMaskedGlobalLLMConfig();

    expect(getWritingBotBaseUrl()).toBe('http://writer.test');
    expect(fetchMock).toHaveBeenCalledWith('http://writer.test/api/settings/llm');
    expect(config.api_key).toBe(maskSecret('sk-test-1234567890'));
  });

  it('uses fetched global settings when proxying a test request', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({
          success: true,
          data: {
            provider: 'openai',
            base_url: 'https://api.openai.com/v1',
            model: 'gpt-5.4',
            api_key: 'secret-key',
          },
        }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        })
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({
          success: true,
          data: { response: 'OK' },
        }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
      })
      );
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    const payload = await proxyLLMTest(undefined, 'http://writer.test');

    expect(fetchMock).toHaveBeenNthCalledWith(1, 'http://writer.test/api/settings/llm');
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      'http://writer.test/api/settings/llm/test',
      expect.objectContaining({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          provider: 'openai',
          base_url: 'https://api.openai.com/v1',
          model: 'gpt-5.4',
          api_key: 'secret-key',
        }),
      })
    );
    expect(payload).toMatchObject({ success: true });
  });

  it('throws when WritingBot reports a failed connection test', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({
        success: false,
        error: 'invalid api key',
      }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    );
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    await expect(proxyLLMTest({
      provider: 'openai',
      base_url: 'https://api.openai.com/v1',
      model: 'gpt-5.4',
      api_key: 'bad-key',
    }, 'http://writer.test')).rejects.toThrow('invalid api key');
  });
});
