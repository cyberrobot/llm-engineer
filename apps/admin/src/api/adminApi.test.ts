import { afterEach, describe, expect, it, vi } from 'vitest';
import { createAdminApi } from './adminApi';

const base = 'https://api.example.test';

afterEach(() => vi.unstubAllGlobals());

describe('admin API', () => {
  const assistant = {
    id: '11111111-1111-4111-8111-111111111111', slug: 'legal-review', name: 'Legal review',
    status: 'inactive', visibility: 'private', created_at: '2026-08-04T00:00:00Z',
    updated_at: '2026-08-04T00:00:00Z', concurrency_token: '2026-08-04T00:00:00Z',
  };
  it('uses the login contract and credentialed request', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      expect(input).toBe(`${base}/admin/auth/login`);
      expect(init?.credentials).toBe('include');
      expect(init?.method).toBe('POST');
      expect(init?.body).toBe(
        JSON.stringify({ email: 'admin@example.test', password: 'secret' }),
      );
      return Response.json({
        user: { id: '1', email: 'admin@example.test', role: 'administrator' },
      });
    });
    vi.stubGlobal('fetch', fetchMock);

    await expect(createAdminApi(base).login('admin@example.test', 'secret')).resolves.toEqual({
      id: '1',
      email: 'admin@example.test',
      role: 'administrator',
    });
    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it('calls current user and logout at exact paths', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        Response.json({ user: { id: '1', email: 'a@example.test', role: 'administrator' } }),
      )
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    vi.stubGlobal('fetch', fetchMock);
    const api = createAdminApi(base);

    await api.currentUser();
    await api.logout();

    expect(fetchMock.mock.calls[0]?.[0]).toBe(`${base}/admin/auth/me`);
    expect(fetchMock.mock.calls[1]?.[0]).toBe(`${base}/admin/auth/logout`);
    expect(fetchMock.mock.calls[1]?.[1]).toEqual(
      expect.objectContaining({ credentials: 'include', method: 'POST' }),
    );
  });

  it('maps contractual failures without exposing raw content', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        Response.json(
          { detail: { code: 'too_many_login_attempts', message: 'sensitive raw detail' } },
          { status: 429 },
        ),
      ),
    );

    await expect(createAdminApi(base).login('a@b.test', 'x')).rejects.toEqual(
      expect.objectContaining({
        kind: 'throttled',
        message: 'The administrator request could not be completed.',
      }),
    );
  });

  it.each([
    ['array response', []],
    ['missing user field', {}],
    ['array user', { user: [] }],
    ['missing user property', { user: { email: 'a@example.test', role: 'administrator' } }],
    ['wrong primitive type', { user: { id: 1, email: 'a@example.test', role: 'administrator' } }],
    [
      'unexpected top-level field',
      { user: { id: '1', email: 'a@example.test', role: 'administrator' }, extra: true },
    ],
    [
      'unexpected nested field',
      {
        user: { id: '1', email: 'a@example.test', role: 'administrator', enabled: true },
      },
    ],
  ])('rejects malformed successful identity: %s', async (_scenario, body) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json(body)));

    await expect(createAdminApi(base).currentUser()).rejects.toEqual(
      expect.objectContaining({ kind: 'invalid_response' }),
    );
  });

  it('maps invalid successful JSON to invalid_response', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response('not json', { status: 200 })),
    );

    await expect(createAdminApi(base).currentUser()).rejects.toEqual(
      expect.objectContaining({ kind: 'invalid_response' }),
    );
  });

  it('preserves cancellation', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(
        (_input: RequestInfo | URL, init?: RequestInit) =>
          new Promise((_resolve, reject) =>
            init?.signal?.addEventListener('abort', () =>
              reject(new DOMException('Aborted', 'AbortError')),
            ),
          ),
      ),
    );
    const controller = new AbortController();
    const promise = createAdminApi(base).currentUser(controller.signal);
    controller.abort();

    await expect(promise).rejects.toMatchObject({ name: 'AbortError' });
  });

  it('uses exact assistant list and create contracts', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(Response.json({ items: [assistant], total: 1, limit: 25, offset: 0 }))
      .mockResolvedValueOnce(Response.json(assistant, { status: 201 }));
    vi.stubGlobal('fetch', fetchMock);
    const api = createAdminApi(base);
    await api.listAssistants({ limit: 25, status: 'inactive', visibility: 'private' });
    await api.createAssistant({ slug: 'legal-review', name: 'Legal review', status: 'inactive', visibility: 'private' });
    expect(fetchMock.mock.calls[0]?.[0]).toBe(`${base}/admin/assistants?limit=25&offset=0&status=inactive&visibility=private`);
    expect(fetchMock.mock.calls[1]?.[1]).toEqual(expect.objectContaining({ method: 'POST', credentials: 'include', body: JSON.stringify({ slug: 'legal-review', name: 'Legal review', status: 'inactive', visibility: 'private' }) }));
  });

  it.each([
    { ...assistant, status: 'paused' },
    { ...assistant, updated_at: 'not-a-time' },
    { ...assistant, slug: 'Not Safe' },
  ])('rejects malformed successful assistant responses', async (body) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json({ items: [body], total: 1, limit: 50, offset: 0 })));
    await expect(createAdminApi(base).listAssistants()).rejects.toMatchObject({ kind: 'invalid_response' });
  });

  it.each([
    { items: [assistant], total: 0, limit: 50, offset: 0 },
    { items: [assistant], total: 1, limit: 101, offset: 0 },
    { items: [assistant], total: 1, limit: 50, offset: 1 },
    { items: [assistant, assistant], total: 2, limit: 1, offset: 0 },
  ])('rejects contradictory assistant pagination metadata', async (body) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json(body)));
    await expect(createAdminApi(base).listAssistants()).rejects.toMatchObject({ kind: 'invalid_response' });
  });

  it('uses exact assistant detail, update, and delete contracts', async () => {
    const detail = { ...assistant, knowledge_source_count: 2, deletion_allowed: false };
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(Response.json(detail))
      .mockResolvedValueOnce(Response.json({ ...assistant, name: 'Updated' }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    vi.stubGlobal('fetch', fetchMock);
    const api = createAdminApi(base);

    await expect(api.getAssistant(assistant.id)).resolves.toMatchObject({
      id: assistant.id,
      knowledgeSourceCount: 2,
      deletionAllowed: false,
    });
    await api.updateAssistant(assistant.id, {
      concurrency_token: assistant.concurrency_token,
      name: 'Updated',
      visibility: 'public',
    });
    await api.deleteAssistant(assistant.id);

    expect(fetchMock.mock.calls[0]?.[0]).toBe(`${base}/admin/assistants/${assistant.id}`);
    expect(fetchMock.mock.calls[0]?.[1]).toEqual(expect.objectContaining({ method: 'GET', credentials: 'include' }));
    expect(fetchMock.mock.calls[1]?.[1]).toEqual(expect.objectContaining({
      method: 'PATCH',
      credentials: 'include',
      body: JSON.stringify({ concurrency_token: assistant.concurrency_token, name: 'Updated', visibility: 'public' }),
    }));
    expect(fetchMock.mock.calls[2]?.[1]).toEqual(expect.objectContaining({ method: 'DELETE', credentials: 'include' }));
  });

  it.each([
    { knowledge_source_count: -1, deletion_allowed: true },
    { knowledge_source_count: 0.5, deletion_allowed: true },
    { knowledge_source_count: 0, deletion_allowed: 'yes' },
  ])('rejects malformed assistant detail fields', async (fields) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json({ ...assistant, ...fields })));
    await expect(createAdminApi(base).getAssistant(assistant.id)).rejects.toMatchObject({ kind: 'invalid_response' });
  });

  it('maps assistant conflicts without exposing backend messages', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json({ detail: { code: 'assistant_slug_conflict', message: 'raw' } }, { status: 409 })));
    await expect(createAdminApi(base).createAssistant({ slug: 'legal-review', name: 'Legal review', status: 'inactive', visibility: 'private' })).rejects.toMatchObject({ kind: 'conflict', code: 'assistant_slug_conflict', message: 'The administrator request could not be completed.' });
  });

  const source = {
    id: '22222222-2222-4222-8222-222222222222',
    assistant_id: assistant.id,
    source_type: 'direct_text',
    name: 'Policy guide',
    retrieval_state: 'enabled',
    url: null,
    direct_text: null,
    document_id: 'document-1',
    created_at: '2026-08-04T00:00:00Z',
    updated_at: '2026-08-04T00:00:00Z',
    latest_ingestion: {
      id: '33333333-3333-4333-8333-333333333333',
      status: 'queued',
      current_step: null,
      created_at: '2026-08-04T00:00:00Z',
      started_at: null,
      completed_at: null,
      failure_code: null,
      failure_message: null,
    },
    active_job_reused: false,
  };

  it('uses exact assistant-scoped knowledge source contracts', async () => {
    const detail = { ...source, direct_text: 'Fictional policy.' };
    const disabled = { ...detail, retrieval_state: 'disabled' };
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(Response.json({ items: [source], total: 1, limit: 25, offset: 0 }))
      .mockResolvedValueOnce(Response.json(detail))
      .mockResolvedValueOnce(Response.json(detail, { status: 202 }))
      .mockResolvedValueOnce(Response.json(disabled))
      .mockResolvedValueOnce(Response.json({ ...detail, active_job_reused: true }, { status: 202 }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    vi.stubGlobal('fetch', fetchMock);
    const api = createAdminApi(base);

    await api.listKnowledgeSources(assistant.id, { limit: 25 });
    await api.getKnowledgeSource(assistant.id, source.id);
    await api.createKnowledgeSource(assistant.id, {
      source_type: 'direct_text', name: 'Policy guide', direct_text: 'Fictional policy.',
    }, 'create-key');
    await api.updateKnowledgeSourceRetrieval(assistant.id, source.id, 'disabled');
    await api.reingestKnowledgeSource(assistant.id, source.id, 'reingest-key');
    await api.deleteKnowledgeSource(assistant.id, source.id);

    const path = `${base}/admin/assistants/${assistant.id}/knowledge-sources`;
    expect(fetchMock.mock.calls[0]?.[0]).toBe(`${path}?limit=25&offset=0`);
    expect(fetchMock.mock.calls[1]?.[0]).toBe(`${path}/${source.id}`);
    expect(fetchMock.mock.calls[2]?.[1]).toEqual(expect.objectContaining({
      method: 'POST', credentials: 'include',
      headers: expect.objectContaining({ 'Idempotency-Key': 'create-key' }),
      body: JSON.stringify({ source_type: 'direct_text', name: 'Policy guide', direct_text: 'Fictional policy.' }),
    }));
    expect(fetchMock.mock.calls[3]?.[1]).toEqual(expect.objectContaining({
      method: 'PATCH', body: JSON.stringify({ retrieval_state: 'disabled' }),
    }));
    expect(fetchMock.mock.calls[4]?.[0]).toBe(`${path}/${source.id}/reingestions`);
    expect(fetchMock.mock.calls[4]?.[1]).toEqual(expect.objectContaining({
      method: 'POST', headers: expect.objectContaining({ 'Idempotency-Key': 'reingest-key' }),
    }));
    expect(fetchMock.mock.calls[5]?.[1]).toEqual(expect.objectContaining({ method: 'DELETE' }));
  });

  it('preserves caller-owned keys for identical retries and independent operations', async () => {
    const detail = { ...source, direct_text: 'Fictional policy.' };
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(Response.json(detail, { status: 202 })));
    vi.stubGlobal('fetch', fetchMock);
    const api = createAdminApi(base);
    const input = { source_type: 'direct_text' as const, name: 'Policy guide', direct_text: 'Fictional policy.' };

    await api.createKnowledgeSource(assistant.id, input, 'same-key');
    await api.createKnowledgeSource(assistant.id, input, 'same-key');
    await api.createKnowledgeSource(assistant.id, input, 'new-operation-key');

    expect(fetchMock.mock.calls.map((call) => (call[1]?.headers as Record<string, string>)['Idempotency-Key']))
      .toEqual(['same-key', 'same-key', 'new-operation-key']);
  });

  it.each([
    { ...source, assistant_id: '44444444-4444-4444-8444-444444444444' },
    { ...source, source_type: 'file' },
    { ...source, retrieval_state: 'pending' },
    { ...source, direct_text: 'list content must be omitted' },
    { ...source, latest_ingestion: { ...source.latest_ingestion, status: 'unknown' } },
  ])('rejects malformed or cross-assistant knowledge list responses', async (item) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json({ items: [item], total: 1, limit: 50, offset: 0 })));
    await expect(createAdminApi(base).listKnowledgeSources(assistant.id)).rejects.toMatchObject({ kind: 'invalid_response' });
  });

  it('requires direct text in protected direct-text detail responses', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json(source)));
    await expect(createAdminApi(base).getKnowledgeSource(assistant.id, source.id)).rejects.toMatchObject({ kind: 'invalid_response' });
  });

  it('uses the exact URL creation body and validates its returned canonical URL', async () => {
    const urlSource = { ...source, source_type: 'url', url: 'https://example.test/guide', direct_text: null };
    const fetchMock = vi.fn().mockResolvedValue(Response.json(urlSource, { status: 202 }));
    vi.stubGlobal('fetch', fetchMock);

    await expect(createAdminApi(base).createKnowledgeSource(assistant.id, {
      source_type: 'url', name: 'Public guide', url: 'https://example.test/guide',
    }, 'url-operation-key')).resolves.toMatchObject({
      sourceType: 'url', url: 'https://example.test/guide', directText: null,
    });
    expect(fetchMock).toHaveBeenCalledWith(
      `${base}/admin/assistants/${assistant.id}/knowledge-sources`,
      expect.objectContaining({
        credentials: 'include',
        method: 'POST',
        headers: expect.objectContaining({ 'Idempotency-Key': 'url-operation-key' }),
        body: JSON.stringify({ source_type: 'url', name: 'Public guide', url: 'https://example.test/guide' }),
      }),
    );
  });

  it.each([
    'ftp://example.test/guide',
    'https://user:secret@example.test/guide',
    'https://example.test/guide#private',
  ])('rejects unsafe URL source responses: %s', async (url) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json({ ...source, source_type: 'url', url, direct_text: null })));
    await expect(createAdminApi(base).getKnowledgeSource(assistant.id, source.id)).rejects.toMatchObject({ kind: 'invalid_response' });
  });

  it.each(['queued', 'pending', 'running', 'completed', 'failed', 'cancelled'] as const)(
    'accepts supported ingestion status %s', async (status) => {
      const detail = { ...source, direct_text: 'Fictional policy.', latest_ingestion: { ...source.latest_ingestion, status } };
      vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json(detail)));
      await expect(createAdminApi(base).getKnowledgeSource(assistant.id, source.id)).resolves.toMatchObject({ latestIngestion: { status } });
    },
  );

  it.each(['parse', 'chunk', 'embed', 'persist'] as const)(
    'accepts supported ingestion step %s', async (current_step) => {
      const detail = { ...source, direct_text: 'Fictional policy.', latest_ingestion: { ...source.latest_ingestion, current_step } };
      vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json(detail)));
      await expect(createAdminApi(base).getKnowledgeSource(assistant.id, source.id)).resolves.toMatchObject({ latestIngestion: { currentStep: current_step } });
    },
  );

  it.each([
    { ...source, id: 'not-a-uuid', direct_text: 'Fictional policy.' },
    { ...source, created_at: '2026-08-04', direct_text: 'Fictional policy.' },
    { ...source, direct_text: 'Fictional policy.', latest_ingestion: { ...source.latest_ingestion, started_at: 12 } },
    { ...source, direct_text: 'Fictional policy.', latest_ingestion: { ...source.latest_ingestion, completed_at: 'not-a-time' } },
  ])('rejects malformed source identifiers, timestamps, and nullable job fields', async (body) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json(body)));
    await expect(createAdminApi(base).getKnowledgeSource(assistant.id, source.id)).rejects.toMatchObject({ kind: 'invalid_response' });
  });

  it.each([
    { items: [source], total: 0, limit: 50, offset: 0 },
    { items: [source], total: 1, limit: 0, offset: 0 },
    { items: [source], total: 1, limit: 50, offset: 1 },
  ])('rejects contradictory knowledge pagination metadata', async (body) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json(body)));
    await expect(createAdminApi(base).listKnowledgeSources(assistant.id)).rejects.toMatchObject({ kind: 'invalid_response' });
  });

  it('enforces 202 mutation and 204 deletion statuses', async () => {
    const detail = { ...source, direct_text: 'Fictional policy.' };
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(Response.json(detail, { status: 200 }))
      .mockResolvedValueOnce(Response.json(detail, { status: 200 }))
      .mockResolvedValueOnce(Response.json({}, { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);
    const api = createAdminApi(base);

    await expect(api.createKnowledgeSource(assistant.id, { source_type: 'direct_text', name: 'Policy guide', direct_text: 'Fictional policy.' }, 'create-key')).rejects.toMatchObject({ kind: 'invalid_response' });
    await expect(api.reingestKnowledgeSource(assistant.id, source.id, 'reingest-key')).rejects.toMatchObject({ kind: 'invalid_response' });
    await expect(api.deleteKnowledgeSource(assistant.id, source.id)).rejects.toMatchObject({ kind: 'invalid_response' });
  });
});
