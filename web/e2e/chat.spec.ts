import { expect, test, type Page } from '@playwright/test';

type StreamEvent = Record<string, unknown>;

type MockState = {
  conversations: Array<Record<string, unknown>>;
  lastChatPayload: Record<string, unknown> | null;
};

function sse(events: StreamEvent[]): string {
  return events.map((event, i) => `id: ${i + 1}\ndata: ${JSON.stringify(event)}\n\n`).join('');
}

function baseSkills() {
  return [
    {
      id: '/paper-summary',
      name: '论文总结',
      label_cn: '论文总结',
      description: '提炼研究问题、方法、实验设置与核心结论。',
      description_cn: '提炼研究问题、方法、实验设置与核心结论。',
      domain: 'research',
      enabled: true,
      requires_kb: false,
      critical: false,
      timeout_ms: 2000,
    },
    {
      id: '/experiment-compare',
      name: '实验对比',
      label_cn: '实验对比',
      description: '对比不同论文或方法在数据集、指标和结果上的差异。',
      description_cn: '对比不同论文或方法在数据集、指标和结果上的差异。',
      domain: 'research',
      enabled: true,
      requires_kb: false,
      critical: false,
      timeout_ms: 2000,
    },
    {
      id: '/innovation-summary',
      name: '创新总结',
      label_cn: '创新总结',
      description: '总结论文创新点以及与已有工作的关键区别。',
      description_cn: '总结论文创新点以及与已有工作的关键区别。',
      domain: 'research',
      enabled: true,
      requires_kb: false,
      critical: false,
      timeout_ms: 2000,
    },
    {
      id: '/research-gaps',
      name: '研究不足',
      label_cn: '研究不足',
      description: '指出局限、潜在偏差、外推风险与后续改进方向。',
      description_cn: '指出局限、潜在偏差、外推风险与后续改进方向。',
      domain: 'research',
      enabled: true,
      requires_kb: false,
      critical: false,
      timeout_ms: 2000,
    },
  ];
}

async function installApiMocks(
  page: Page,
  options: {
    streamDelayMs?: number;
    streamEvents?: StreamEvent[];
    onStreamRequest?: (payload: Record<string, unknown>, state: MockState) => Promise<void> | void;
  } = {}
): Promise<MockState> {
  const state: MockState = {
    conversations: [],
    lastChatPayload: null,
  };

  await page.route('**/api/**', async (route) => {
    const req = route.request();
    const url = new URL(req.url());
    const pathname = url.pathname;
    const method = req.method();

    const jsonResponse = (payload: unknown, status = 200) =>
      route.fulfill({
        status,
        headers: { 'content-type': 'application/json; charset=utf-8' },
        body: JSON.stringify(payload),
      });

    if (pathname === '/api/kbs' && method === 'GET') {
      return jsonResponse({
        success: true,
        data: [
          {
            id: 'kb-1',
            name: 'agent 论文集',
            description: 'mock kb',
            embedding_model: 'mock',
            embedding_provider: 'mock',
            files: [],
            created_at: new Date().toISOString(),
          },
        ],
      });
    }

    if (pathname === '/api/conversations' && method === 'GET') {
      return jsonResponse({ success: true, data: state.conversations });
    }

    if (pathname.startsWith('/api/conversations/') && method === 'GET') {
      return jsonResponse({ detail: 'Conversation not found' }, 404);
    }

    if (pathname === '/api/skills' && method === 'GET') {
      return jsonResponse({ success: true, data: baseSkills() });
    }

    if (pathname === '/api/chat/stream' && method === 'POST') {
      const payload = req.postDataJSON() as Record<string, unknown>;
      state.lastChatPayload = payload;
      await options.onStreamRequest?.(payload, state);

      const events =
        options.streamEvents ||
        [
          {
            type: 'chunk',
            content: '',
            meta: { kind: 'progress', step: 'plan', status: 'working', ts: new Date().toISOString() },
          },
          { type: 'chunk', content: '默认回答', meta: { kind: 'content', ts: new Date().toISOString() } },
          { type: 'sources', data: [] },
          { type: 'done', conversation_id: 'conv-1', meta: { progress_event_count: 1 } },
        ];

      const done = events.find((event) => event.type === 'done');
      const convId = String(done?.conversation_id || 'conv-1');
      state.conversations = [
        {
          id: convId,
          title: String(payload.message || '新聊天').slice(0, 30),
          kb_id: payload.kb_id || null,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          message_count: 2,
          last_message: String(payload.message || ''),
        },
      ];

      if ((options.streamDelayMs || 0) > 0) {
        await new Promise((resolve) => setTimeout(resolve, options.streamDelayMs));
      }

      return route.fulfill({
        status: 200,
        headers: {
          'content-type': 'text/event-stream; charset=utf-8',
          'cache-control': 'no-cache, no-transform',
          connection: 'keep-alive',
        },
        body: sse(events),
      });
    }

    return jsonResponse({ success: true, data: [] });
  });

  return state;
}

test('发送后 1 秒内进度可见且会变化', async ({ page }) => {
  await installApiMocks(page, {
    streamDelayMs: 2200,
    streamEvents: [{ type: 'done', conversation_id: 'conv-1', meta: {} }],
  });

  await page.goto('/chat');
  await page.getByTestId('chat-input').fill('请总结这篇论文');
  await page.getByTestId('chat-send').click();

  await expect(page.getByText('智能体思考过程')).toBeVisible();
  await page.waitForTimeout(1200);
  const text = (await page.getByTestId('thinking-progress-value').textContent()) || '';
  const value = Number((text.match(/(\d+)/) || [])[1] || 0);
  expect(value).toBeGreaterThan(0);
});

test('聊天页全屏布局：无外围留白', async ({ page }) => {
  await installApiMocks(page);
  await page.goto('/chat');

  const root = page.getByTestId('chat-page-root');
  const grid = page.getByTestId('chat-grid');
  await expect(root).toBeVisible();
  await expect(grid).toBeVisible();

  const rootStyle = await root.evaluate((el) => {
    const s = window.getComputedStyle(el);
    return {
      paddingTop: s.paddingTop,
      paddingRight: s.paddingRight,
      paddingBottom: s.paddingBottom,
      paddingLeft: s.paddingLeft,
      marginTop: s.marginTop,
      marginRight: s.marginRight,
      marginBottom: s.marginBottom,
      marginLeft: s.marginLeft,
      maxWidth: s.maxWidth,
    };
  });
  expect(rootStyle.paddingTop).toBe('0px');
  expect(rootStyle.paddingRight).toBe('0px');
  expect(rootStyle.paddingBottom).toBe('0px');
  expect(rootStyle.paddingLeft).toBe('0px');
  expect(rootStyle.marginTop).toBe('0px');
  expect(rootStyle.marginRight).toBe('0px');
  expect(rootStyle.marginBottom).toBe('0px');
  expect(rootStyle.marginLeft).toBe('0px');
  expect(rootStyle.maxWidth).toBe('none');

  const mainBox = await page.locator('main').boundingBox();
  const rootBox = await root.boundingBox();
  expect(mainBox).not.toBeNull();
  expect(rootBox).not.toBeNull();
  if (mainBox && rootBox) {
    expect(Math.abs(rootBox.x - mainBox.x)).toBeLessThan(1);
    expect(Math.abs(rootBox.y - mainBox.y)).toBeLessThan(1);
    expect(Math.abs(rootBox.width - mainBox.width)).toBeLessThan(1);
    expect(Math.abs(rootBox.height - mainBox.height)).toBeLessThan(1);
  }
});

test('长等待期间不会静默卡死（30 秒）', async ({ page }) => {
  test.setTimeout(120000);
  await installApiMocks(page, {
    streamDelayMs: 30000,
    streamEvents: [
      { type: 'chunk', content: '默认回答', meta: { kind: 'content', ts: new Date().toISOString() } },
      { type: 'sources', data: [] },
      { type: 'done', conversation_id: 'conv-1', meta: {} },
    ],
  });

  await page.goto('/chat');
  await page.getByTestId('chat-input').fill('请做相关工作综述');
  await page.getByTestId('chat-send').click();

  await expect(page.getByText('智能体思考过程')).toBeVisible();
  await page.waitForTimeout(5000);

  const text = (await page.getByTestId('thinking-progress-value').textContent()) || '';
  const value = Number((text.match(/(\d+)/) || [])[1] || 0);
  expect(value).toBeGreaterThan(0);
  await expect(page.getByText(/已耗时 \d+s/)).toBeVisible();
  await page.waitForTimeout(26000);
  await expect(page.locator('[data-testid^="message-assistant-"]').last()).toContainText('默认回答');
});

test('回答渲染清洁：不显示裸 <br> 且表格可读', async ({ page }) => {
  await installApiMocks(page, {
    streamEvents: [
      {
        type: 'chunk',
        content: '第一行<br>第二行<br/>第三行\n\n| 指标 | 数值 |\n| --- | --- |\n| F1 | 90% |',
        meta: { kind: 'content', ts: new Date().toISOString() },
      },
      { type: 'sources', data: [] },
      { type: 'done', conversation_id: 'conv-1', meta: {} },
    ],
  });

  await page.goto('/chat');
  await page.getByTestId('chat-input').fill('输出格式测试');
  await page.getByTestId('chat-send').click();

  const assistantBubble = page.locator('[data-testid^="message-assistant-"]').last();
  await expect(assistantBubble).toContainText('第一行');
  await expect(assistantBubble).toContainText('第二行');
  await expect(assistantBubble).not.toContainText('<br>');
  await expect(page.locator('table').first()).toBeVisible();
});

test('选中 skill 后空输入可直接发送', async ({ page }) => {
  const state = await installApiMocks(page);
  await page.goto('/chat');

  await page.getByTestId('chat-input').fill('/');
  await expect(page.getByTestId('skill-option-paper-summary')).toBeVisible();
  await expect(page.getByTestId('skill-option-experiment-compare')).toBeVisible();
  await expect(page.getByTestId('skill-option-innovation-summary')).toBeVisible();
  await expect(page.getByTestId('skill-option-research-gaps')).toBeVisible();
  await page.getByTestId('skill-option-paper-summary').click();
  await expect(page.getByTestId('selected-skill-card')).toBeVisible();
  await expect(page.getByTestId('chat-input')).toHaveValue('');
  await expect(page.getByTestId('chat-send')).toBeEnabled();
  await page.getByTestId('chat-send').click();

  await expect.poll(() => state.lastChatPayload).not.toBeNull();
  expect(state.lastChatPayload?.skill_ids).toEqual(['/paper-summary']);
  expect(String(state.lastChatPayload?.message || '')).toContain('技能模板开始分析');
});
