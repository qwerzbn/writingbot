import { expect, test, type Page } from '@playwright/test';

type NotebookSource = {
  id: string;
  notebook_id: string;
  kind: 'pdf' | 'url' | 'text' | 'kb_ref';
  title: string;
  included: boolean;
  status: string;
  snippet: string;
  word_count: number;
  char_count: number;
  chunk_count: number;
  created_at: string;
  updated_at: string;
  metadata: Record<string, unknown>;
};

type NotebookCitation = {
  index: number;
  source_id: string;
  source_title: string;
  locator: string;
  excerpt: string;
};

type NotebookMessage = {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  background_extension?: string;
  citations?: NotebookCitation[];
  answer_mode?: 'grounded' | 'weakly_grounded' | 'llm_fallback';
  retrieval_mode?: 'grounded' | 'weakly_grounded' | 'llm_fallback';
  source_ids: string[];
  created_at: string;
};

type NotebookSession = {
  id: string;
  notebook_id: string;
  title: string;
  messages: NotebookMessage[];
  created_at: string;
  updated_at: string;
};

type NotebookOutput = {
  id: string;
  notebook_id: string;
  kind: 'summary' | 'study_guide' | 'faq' | 'mind_map';
  title: string;
  content: string;
  blocks: Array<{ title: string; items: string[] }>;
  tree: { id: string; label: string; children?: Array<{ id: string; label: string; children?: Array<{ id: string; label: string }> }> } | null;
  citations: NotebookCitation[];
  source_ids: string[];
  created_at: string;
  updated_at: string;
};

type NotebookNote = {
  id: string;
  notebook_id: string;
  title: string;
  content: string;
  kind: 'manual' | 'saved_chat' | 'saved_research' | 'saved_studio';
  origin: string | null;
  citations: NotebookCitation[];
  source_ids: string[];
  tags: string[];
  created_at: string;
  updated_at: string;
  source: {
    type?: string;
    file_name?: string;
    file_id?: string;
    page?: number;
    citation_count?: number;
    evidence_links?: Array<{ id?: string; source?: string; page?: number | string; content?: string }>;
  };
  ai_meta?: {
    summary?: string;
    suggested_tags?: string[];
  };
};

type MockState = {
  notebook: {
    id: string;
    name: string;
    description: string;
    color: string;
    icon: string;
    source_count: number;
    note_count: number;
    last_chat_at: string | null;
    last_output_at: string | null;
    created_at: string;
    updated_at: string;
    default_kb_id: string | null;
  };
  sources: NotebookSource[];
  sessions: NotebookSession[];
  outputs: NotebookOutput[];
  notes: NotebookNote[];
};

function nowIso() {
  return new Date().toISOString();
}

function createCitation(source: NotebookSource, excerpt: string): NotebookCitation {
  return {
    index: 1,
    source_id: source.id,
    source_title: source.title,
    locator: source.kind === 'pdf' ? 'p.1' : source.kind,
    excerpt,
  };
}

function buildWorkspace(state: MockState) {
  return {
    generated_at: nowIso(),
    notebook: {
      ...state.notebook,
      source_count: state.sources.length,
      note_count: state.notes.length,
      last_chat_at: state.sessions[0]?.updated_at || null,
      last_output_at: state.outputs[0]?.updated_at || null,
      updated_at: nowIso(),
    },
    sources: state.sources,
    recent_sessions: state.sessions.map((session) => ({
      id: session.id,
      title: session.title,
      updated_at: session.updated_at,
      created_at: session.created_at,
      message_count: session.messages.length,
      last_message: session.messages[session.messages.length - 1]?.content || '',
    })),
    studio_outputs: state.outputs,
    notes_summary: state.notes.map((note) => ({
      id: note.id,
      title: note.title,
      kind: note.kind,
      preview: note.content.slice(0, 120),
      tags: note.tags,
      source_ids: note.source_ids,
      updated_at: note.updated_at,
      created_at: note.created_at,
      origin: note.origin,
      citations: note.citations,
    })),
    ui_defaults: {
      selected_source_ids: state.sources.filter((source) => source.included).map((source) => source.id),
      active_session_id: state.sessions[0]?.id || null,
      active_output_id: state.outputs[0]?.id || null,
      note_drawer_open: false,
    },
  };
}

async function installNotebookMocks(page: Page): Promise<MockState> {
  const createdAt = nowIso();
  const notebookId = 'nb-demo';
  const researchNote: NotebookNote = {
    id: 'note-research',
    notebook_id: notebookId,
    title: 'Research saved note',
    content: '这是一条从 Research 页面写入的笔记，用来验证 notebook 工作台会显示外部保存的内容。',
    kind: 'saved_research',
    origin: 'research',
    citations: [],
    source_ids: [],
    tags: ['research'],
    created_at: createdAt,
    updated_at: createdAt,
    source: {
      type: 'research',
      citation_count: 0,
      evidence_links: [],
    },
    ai_meta: {
      summary: 'Research saved note',
      suggested_tags: ['research'],
    },
  };

  const state: MockState = {
    notebook: {
      id: notebookId,
      name: 'NotebookLM Demo',
      description: 'Sources + Chat + Studio + Notes',
      color: '#111827',
      icon: 'book',
      source_count: 0,
      note_count: 1,
      last_chat_at: null,
      last_output_at: null,
      created_at: createdAt,
      updated_at: createdAt,
      default_kb_id: 'kb-1',
    },
    sources: [],
    sessions: [],
    outputs: [],
    notes: [researchNote],
  };

  await page.route('**/api/**', async (route) => {
    const req = route.request();
    const url = new URL(req.url());
    const pathname = url.pathname;
    const method = req.method();

    const json = (payload: unknown, status = 200) =>
      route.fulfill({
        status,
        headers: { 'content-type': 'application/json; charset=utf-8' },
        body: JSON.stringify(payload),
      });

    if (pathname === '/api/kbs' && method === 'GET') {
      return json({
        success: true,
        data: [
          {
            id: 'kb-1',
            name: '演示知识库',
            description: 'mock',
            embedding_model: 'mock',
            embedding_provider: 'mock',
            files: [
              {
                id: 'kb-file-1',
                name: 'demo-paper.pdf',
                size: 1024,
                chunks: 3,
                uploaded_at: createdAt,
              },
            ],
            created_at: createdAt,
          },
        ],
      });
    }

    if (pathname === `/api/notebooks/${notebookId}/workspace` && method === 'GET') {
      return json({ success: true, data: buildWorkspace(state) });
    }

    if (pathname === `/api/notebooks/${notebookId}/sources` && method === 'POST') {
      const sourceId = `source-${state.sources.length + 1}`;
      const source: NotebookSource = {
        id: sourceId,
        notebook_id: notebookId,
        kind: 'text',
        title: '课程摘要',
        included: true,
        status: 'ready',
        snippet: 'NotebookLM 风格智能笔记本支持来源优先回答与 Studio 生成。',
        word_count: 28,
        char_count: 56,
        chunk_count: 1,
        created_at: nowIso(),
        updated_at: nowIso(),
        metadata: { source: 'pasted_text' },
      };
      state.sources = [source, ...state.sources];
      state.notebook.updated_at = nowIso();
      return json({ success: true, data: source });
    }

    const sourceMatch = pathname.match(/^\/api\/notebooks\/nb-demo\/sources\/([^/]+)$/);
    if (sourceMatch && method === 'PUT') {
      const body = req.postDataJSON() as Partial<NotebookSource>;
      state.sources = state.sources.map((source) =>
        source.id === sourceMatch[1]
          ? { ...source, ...body, updated_at: nowIso() }
          : source
      );
      const source = state.sources.find((item) => item.id === sourceMatch[1]);
      return json({ success: true, data: source });
    }

    if (sourceMatch && method === 'DELETE') {
      state.sources = state.sources.filter((source) => source.id !== sourceMatch[1]);
      return json({ success: true, data: true });
    }

    if (pathname === `/api/notebooks/${notebookId}/chat/stream` && method === 'POST') {
      const body = req.postDataJSON() as { message: string; source_ids?: string[] };
      const source = state.sources[0];
      const citation = source
        ? createCitation(source, 'NotebookLM 风格智能笔记本支持来源优先回答与 Studio 生成。')
        : null;
      const sessionId = 'session-1';
      const weaklyGrounded = String(body.message || '').includes('泛问');
      const assistant: NotebookMessage = {
        id: 'assistant-1',
        role: 'assistant',
        content: weaklyGrounded
          ? '我先基于已选来源做一个相关整理，但这次没有形成可直接引用的证据片段。'
          : '来源显示，这个 notebook 会优先基于导入材料回答问题。[1]',
        background_extension: weaklyGrounded ? '' : '补充背景：在来源不足时，模型补充会单独标记出来。',
        citations: weaklyGrounded ? [] : citation ? [citation] : [],
        answer_mode: weaklyGrounded ? 'weakly_grounded' : 'grounded',
        retrieval_mode: weaklyGrounded ? 'weakly_grounded' : 'grounded',
        source_ids: body.source_ids || [],
        created_at: nowIso(),
      };
      state.sessions = [
        {
          id: sessionId,
          notebook_id: notebookId,
          title: '智能笔记本怎么工作',
          messages: [
            {
              id: 'user-1',
              role: 'user',
              content: String(body.message || ''),
              source_ids: body.source_ids || [],
              created_at: nowIso(),
            },
            assistant,
          ],
          created_at: nowIso(),
          updated_at: nowIso(),
        },
      ];

      const sse = [
        { type: 'init', mode: 'notebook-chat' },
        {
          type: 'message_chunk',
          content: weaklyGrounded
            ? '我先基于已选来源做一个相关整理，但这次没有形成可直接引用的证据片段。'
            : '来源显示，这个 notebook 会优先基于导入材料回答问题。[1]',
        },
        { type: 'citations', data: weaklyGrounded ? [] : citation ? [citation] : [] },
        ...(weaklyGrounded ? [] : [{ type: 'background_extension', content: '补充背景：在来源不足时，模型补充会单独标记出来。' }]),
        {
          type: 'done',
          answer_mode: weaklyGrounded ? 'weakly_grounded' : 'grounded',
          retrieval_mode: weaklyGrounded ? 'weakly_grounded' : 'grounded',
          session: state.sessions[0],
          assistant_message: assistant,
        },
      ]
        .map((event) => `data: ${JSON.stringify(event)}\n\n`)
        .join('');

      return route.fulfill({
        status: 200,
        headers: {
          'content-type': 'text/event-stream; charset=utf-8',
          'cache-control': 'no-cache',
        },
        body: sse,
      });
    }

    const sessionMatch = pathname.match(/^\/api\/notebooks\/nb-demo\/chat\/sessions\/([^/]+)$/);
    if (sessionMatch && method === 'GET') {
      const session = state.sessions.find((item) => item.id === sessionMatch[1]);
      return json({ success: true, data: session });
    }

    if (pathname === `/api/notebooks/${notebookId}/studio` && method === 'POST') {
      const body = req.postDataJSON() as { kind: NotebookOutput['kind']; source_ids?: string[] };
      const output: NotebookOutput = {
        id: `output-${body.kind}`,
        notebook_id: notebookId,
        kind: body.kind,
        title: `${body.kind} output`,
        content: `## ${body.kind}\n\n围绕当前来源生成的 ${body.kind} 内容。`,
        blocks: [
          {
            title: '重点',
            items: [`${body.kind} item A`, `${body.kind} item B`],
          },
        ],
        tree:
          body.kind === 'mind_map'
            ? {
                id: 'root',
                label: 'NotebookLM Demo',
                children: [
                  { id: 'node-1', label: 'Sources', children: [{ id: 'leaf-1', label: 'Grounded chat' }] },
                ],
              }
            : null,
        citations: state.sources[0] ? [createCitation(state.sources[0], 'Studio output is grounded in imported sources.')] : [],
        source_ids: body.source_ids || [],
        created_at: nowIso(),
        updated_at: nowIso(),
      };
      state.outputs = [output, ...state.outputs.filter((item) => item.id !== output.id)];
      return json({ success: true, data: output });
    }

    const studioMatch = pathname.match(/^\/api\/notebooks\/nb-demo\/studio\/([^/]+)\/save-note$/);
    if (studioMatch && method === 'POST') {
      const output = state.outputs.find((item) => item.id === studioMatch[1]);
      const note: NotebookNote = {
        id: 'note-studio',
        notebook_id: notebookId,
        title: output?.title || 'Studio note',
        content: output?.content || '',
        kind: 'saved_studio',
        origin: `studio:${output?.kind || 'summary'}`,
        citations: output?.citations || [],
        source_ids: output?.source_ids || [],
        tags: ['studio'],
        created_at: nowIso(),
        updated_at: nowIso(),
        source: {
          type: 'manual',
          citation_count: output?.citations.length || 0,
          evidence_links: (output?.citations || []).map((citation) => ({
            id: `${citation.source_id}:${citation.index}`,
            source: citation.source_title,
            page: citation.locator,
            content: citation.excerpt,
          })),
        },
        ai_meta: {
          summary: output?.content.slice(0, 120),
          suggested_tags: ['studio'],
        },
      };
      state.notes = [note, ...state.notes.filter((item) => item.id !== note.id)];
      return json({ success: true, data: note });
    }

    if (pathname === `/api/notebooks/${notebookId}/notes/from-sources` && method === 'POST') {
      const body = req.postDataJSON() as {
        title: string;
        content: string;
        sources?: NotebookCitation[];
        tags?: string[];
        origin_type?: string;
      };
      const note: NotebookNote = {
        id: `note-chat-${state.notes.length + 1}`,
        notebook_id: notebookId,
        title: body.title,
        content: body.content,
        kind: 'saved_chat',
        origin: body.origin_type || 'chat',
        citations: (body.sources || []).map((source, index) => ({
          index: index + 1,
          source_id: String(source.source_id || state.sources[0]?.id || ''),
          source_title: String(source.source_title || state.sources[0]?.title || 'Untitled source'),
          locator: String(source.locator || 'p.1'),
          excerpt: String(source.excerpt || ''),
        })),
        source_ids: (body.sources || []).map((source) => String(source.source_id || '')),
        tags: body.tags || ['chat'],
        created_at: nowIso(),
        updated_at: nowIso(),
        source: {
          type: 'chat',
          citation_count: (body.sources || []).length,
          evidence_links: (body.sources || []).map((source, index) => ({
            id: `chat:${index}`,
            source: String(source.source_title || state.sources[0]?.title || 'Untitled source'),
            page: String(source.locator || 'p.1'),
            content: String(source.excerpt || ''),
          })),
        },
        ai_meta: {
          summary: body.content.slice(0, 120),
          suggested_tags: body.tags || ['chat'],
        },
      };
      state.notes = [note, ...state.notes.filter((item) => item.id !== note.id)];
      return json({ success: true, data: note });
    }

    const noteMatch = pathname.match(/^\/api\/notebooks\/nb-demo\/notes\/([^/]+)$/);
    if (noteMatch && method === 'GET') {
      const note = state.notes.find((item) => item.id === noteMatch[1]);
      return json({ success: true, data: note });
    }

    if (noteMatch && method === 'PUT') {
      const body = req.postDataJSON() as Partial<NotebookNote>;
      state.notes = state.notes.map((note) =>
        note.id === noteMatch[1]
          ? {
              ...note,
              title: body.title ?? note.title,
              content: body.content ?? note.content,
              tags: body.tags ?? note.tags,
              updated_at: nowIso(),
            }
          : note
      );
      const note = state.notes.find((item) => item.id === noteMatch[1]);
      return json({ success: true, data: note });
    }

    return json({ success: true, data: [] });
  });

  return state;
}

test('notebook workspace keeps a persistent notes rail and routes report generation into notes', async ({ page }) => {
  await installNotebookMocks(page);
  const consoleErrors: string[] = [];
  page.on('console', (msg) => {
    if (msg.type() === 'error') {
      consoleErrors.push(msg.text());
    }
  });

  await page.goto('/notebook/nb-demo');
  await expect(page.getByTestId('notebook-page-root')).toBeVisible();
  await expect(page.locator('h1')).toHaveText('NotebookLM Demo');
  await expect(page.getByTestId('notebook-header-settings')).toHaveCount(0);
  await expect(page.getByTestId('notebook-header-avatar')).toHaveCount(0);
  await expect(page.getByTestId('notebook-notes-panel')).toBeVisible();
  await expect(page.getByTestId('notebook-studio-panel')).toBeHidden();
  await expect(page.getByText('生成的笔记、报告和总结会显示在这里，默认以文档阅读态查看。')).toHaveCount(0);
  await expect(page.getByText('笔记列表保持简洁，选中后会在下方进入完整阅读态，避免右栏内容全部堆在一张卡片里。')).toHaveCount(0);
  await expect(page.getByTestId('note-list-item').first()).toBeVisible();
  await expect(page.getByTestId('notebook-notes-panel').getByText('Research saved note').first()).toBeVisible();
  await expect(page.getByTestId('notebook-chat-empty-state')).toBeVisible();

  await page.getByTestId('notebook-add-source').click();
  await expect(page.getByTestId('source-file-trigger')).toBeVisible();
  await page.getByTestId('source-file-input').setInputFiles({
    name: 'demo.pdf',
    mimeType: 'application/pdf',
    buffer: Buffer.from('%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF'),
  });
  await expect(page.getByText('demo.pdf')).toBeVisible();
  await page.getByRole('button', { name: '粘贴文本' }).click();
  await page.getByPlaceholder('可选，自定义来源标题').fill('课程摘要');
  await page.getByPlaceholder('粘贴文稿、会议纪要、采访内容或章节正文').fill('NotebookLM 风格智能笔记本支持来源优先回答。');
  await page.getByRole('button', { name: '添加来源' }).click();
  await expect(page.getByTestId('notebook-sources-panel').getByText('课程摘要')).toBeVisible();
  await expect(page.getByTestId('sources-select-all')).toBeVisible();

  await page.getByTestId('notebook-chat-input').fill('这个智能笔记本怎么工作？');
  await page.getByTestId('notebook-chat-send').click();
  await expect(page.getByText('来源显示，这个 notebook 会优先基于导入材料回答问题。[1]')).toBeVisible();
  await expect(page.getByTestId('chat-answer-mode')).toContainText('Grounded');
  await expect(page.getByText('背景补充', { exact: true })).toBeVisible();
  await expect(page.getByText('Citations')).toBeVisible();
  await page.getByRole('button', { name: '保存为笔记' }).click();
  await expect(page.getByTestId('notes-back-to-list')).toBeVisible();
  await expect(page.getByTestId('notebook-notes-panel').getByText('聊天笔记：来源显示，这个 notebook 会优先').first()).toBeVisible();
  await expect(page.getByTestId('note-reading-view')).toBeVisible();
  await expect(page.getByTestId('note-reading-breadcrumb')).toContainText('Notes');
  await expect(page.getByTestId('note-reading-view').getByText('背景补充')).toBeVisible();
  await expect(page.getByTestId('note-edit-button')).toBeVisible();
  await expect(page.getByTestId('note-editor-form')).toBeHidden();

  await page.getByTestId('note-edit-button').click();
  await expect(page.getByTestId('note-editor-form')).toBeVisible();
  await page.getByTestId('note-title-input').fill('已编辑聊天笔记');
  await page.getByTestId('note-save-button').click();
  await expect(page.getByTestId('notebook-notes-panel').getByText('已编辑聊天笔记').first()).toBeVisible();
  await expect(page.getByTestId('note-reading-title')).toHaveText('已编辑聊天笔记');

  await page.getByTestId('notebook-generate-report').click();
  await expect(page.getByTestId('notes-back-to-list')).toBeVisible();
  await expect(page.getByTestId('note-reading-title')).toHaveText('summary output');
  await expect(page.getByTestId('note-reading-source-count')).toContainText('Based on');
  await page.getByTestId('notes-back-to-list').click();
  await expect(page.getByTestId('note-list-item').first()).toBeVisible();
  await expect(page.getByTestId('notebook-notes-panel').getByText('summary output').first()).toBeVisible();
  expect(consoleErrors).not.toContainEqual(expect.stringContaining('<button> cannot be a descendant of <button>'));
});

test('mobile tabs switch between sources, chat, and notes', async ({ page }) => {
  await installNotebookMocks(page);
  await page.setViewportSize({ width: 430, height: 932 });
  await page.goto('/notebook/nb-demo');

  await expect(page.getByTestId('mobile-tab-chat')).toBeVisible();
  await page.getByTestId('mobile-tab-sources').click();
  await expect(page.getByTestId('notebook-sources-panel')).toBeVisible();

  await page.getByTestId('mobile-tab-notes').click();
  await expect(page.getByTestId('notebook-notes-panel')).toBeVisible();

  await page.getByTestId('mobile-tab-chat').click();
  await expect(page.getByTestId('notebook-chat-panel')).toBeVisible();
});

test('chat shows weakly grounded state even when citations are empty', async ({ page }) => {
  await installNotebookMocks(page);
  await page.goto('/notebook/nb-demo');

  await page.getByTestId('notebook-chat-input').fill('这是一个泛问，请先给我相关整理');
  await page.getByTestId('notebook-chat-send').click();

  await expect(page.getByText('我先基于已选来源做一个相关整理，但这次没有形成可直接引用的证据片段。')).toBeVisible();
  await expect(page.getByTestId('chat-answer-mode')).toContainText('Related sources');
  await expect(page.getByText('未引用来源')).toBeVisible();
});
