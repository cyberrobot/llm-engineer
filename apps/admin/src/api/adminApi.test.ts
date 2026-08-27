import { afterEach, describe, expect, it, vi } from 'vitest';
import { AdminApiError, createAdminApi } from './adminApi';

const base = 'https://api.example.test';

afterEach(() => vi.unstubAllGlobals());

describe('admin API', () => {
  const assistant = {
    id: '11111111-1111-4111-8111-111111111111', slug: 'legal-review', name: 'Legal review',
    status: 'inactive', visibility: 'private', created_at: '2026-08-04T00:00:00Z',
    updated_at: '2026-08-04T00:00:00Z', concurrency_token: '2026-08-04T00:00:00Z',
  };
  const operationsSummary = {
    generated_at: '2026-08-25T10:00:00Z', health: 'healthy', maintenance: false,
    cache: { regions: 3 }, jobs: { running: 1, failed: 0 }, audit: { today: 4 },
    assistants: { total: 2, published: 1 },
    knowledge_sources: { total: 5, enabled: 4, failed: null },
    ingestion: { queued: 2, running: 1, recoverable: 0, failed: 0, oldest_queued_age_seconds: 4320.5, workers_observed: 2 },
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

  it('loads and maps the exact credentialed Operations Summary contract', async () => {
    const controller = new AbortController();
    const fetchMock = vi.fn().mockResolvedValue(Response.json(operationsSummary));
    vi.stubGlobal('fetch', fetchMock);

    await expect(createAdminApi(base).getOperationsSummary(controller.signal)).resolves.toEqual({
      generatedAt: '2026-08-25T10:00:00Z', health: 'healthy', maintenance: false,
      cache: { regions: 3 }, jobs: { running: 1, failed: 0 }, audit: { today: 4 },
      assistants: { total: 2, published: 1 },
      knowledgeSources: { total: 5, enabled: 4, failed: null },
      ingestion: { queued: 2, running: 1, recoverable: 0, failed: 0, oldestQueuedAgeSeconds: 4320.5, workersObserved: 2 },
    });
    expect(fetchMock).toHaveBeenCalledWith(`${base}/admin/operations/summary`, expect.objectContaining({
      method: 'GET', credentials: 'include', signal: controller.signal,
    }));
  });

  it.each([
    ['invalid generated timestamp', { ...operationsSummary, generated_at: 'today' }],
    ['unknown health state', { ...operationsSummary, health: 'ok' }],
    ['negative count', { ...operationsSummary, jobs: { running: -1, failed: 0 } }],
    ['fractional count', { ...operationsSummary, cache: { regions: 1.5 } }],
    ['invalid queue age', { ...operationsSummary, ingestion: { ...operationsSummary.ingestion, oldest_queued_age_seconds: -1 } }],
    ['missing nested field', { ...operationsSummary, ingestion: { queued: 0 } }],
    ['unexpected top-level field', { ...operationsSummary, request_id: 'request-1' }],
    ['invalid nullable count', { ...operationsSummary, knowledge_sources: { total: 5, enabled: 4, failed: 'unknown' } }],
  ])('rejects a malformed Operations Summary: %s', async (_scenario, body) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json(body)));
    await expect(createAdminApi(base).getOperationsSummary()).rejects.toEqual(
      expect.objectContaining({ kind: 'invalid_response' }),
    );
  });

  it.each([[401, 'unauthenticated'], [403, 'forbidden'], [500, 'server']] as const)(
    'maps Operations Summary HTTP %i safely', async (status, kind) => {
      vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status })));
      await expect(createAdminApi(base).getOperationsSummary()).rejects.toEqual(expect.objectContaining({ kind }));
    },
  );

  it('accepts authoritative zero counts and a reported zero Knowledge Source failure count', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json({
      ...operationsSummary,
      cache: { regions: 0 }, jobs: { running: 0, failed: 0 }, audit: { today: 0 },
      assistants: { total: 0, published: 0 }, knowledge_sources: { total: 0, enabled: 0, failed: 0 },
      ingestion: { queued: 0, running: 0, recoverable: 0, failed: 0, oldest_queued_age_seconds: 0, workers_observed: 0 },
    })));
    const result = await createAdminApi(base).getOperationsSummary();
    expect(result.knowledgeSources.failed).toBe(0);
    expect(result.ingestion.oldestQueuedAgeSeconds).toBe(0);
  });

  it('maps malformed JSON, network failure, and cancellation for Operations Summary', async () => {
    const api = createAdminApi(base);
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('not json', { status: 200 })));
    await expect(api.getOperationsSummary()).rejects.toEqual(expect.objectContaining({ kind: 'invalid_response' }));

    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('offline')));
    await expect(api.getOperationsSummary()).rejects.toEqual(expect.objectContaining({ kind: 'network' }));

    vi.stubGlobal('fetch', vi.fn((_input: RequestInfo | URL, init?: RequestInit) => new Promise((_resolve, reject) => {
      init?.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')));
    })));
    const controller = new AbortController();
    const pending = api.getOperationsSummary(controller.signal);
    controller.abort();
    await expect(pending).rejects.toEqual(expect.objectContaining({ name: 'AbortError' }));
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

  it.each(['list', 'detail'] as const)('forwards cancellation for knowledge %s reads', async (operation) => {
    const controller = new AbortController();
    const fetchMock = vi.fn((_input: RequestInfo | URL, init?: RequestInit) =>
      new Promise<Response>((_resolve, reject) => {
        init?.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')));
      }));
    vi.stubGlobal('fetch', fetchMock);
    const api = createAdminApi(base);
    const request = operation === 'list'
      ? api.listKnowledgeSources(assistant.id, { limit: 25, offset: 0 }, controller.signal)
      : api.getKnowledgeSource(assistant.id, source.id, controller.signal);

    expect(fetchMock.mock.calls[0]?.[1]?.signal).toBe(controller.signal);
    controller.abort();
    await expect(request).rejects.toMatchObject({ name: 'AbortError' });
  });

  it.each([
    [401, undefined, 'unauthenticated'],
    [403, undefined, 'forbidden'],
    [404, 'knowledge_source_not_found', 'not_found'],
    [422, 'validation_failed', 'invalid_request'],
    [409, 'idempotency_key_conflict', 'conflict'],
    [409, 'active_ingestion', 'conflict'],
    [503, 'provider_secret', 'server'],
  ] as const)('maps knowledge failure %s/%s safely', async (status, code, kind) => {
    const raw = '<html>provider token and database trace</html>';
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json({ detail: { code, message: raw }, provider_payload: raw }, { status })));

    const error = await createAdminApi(base).getKnowledgeSource(assistant.id, source.id)
      .then(() => undefined, (caught: unknown) => caught);
    expect(error).toBeInstanceOf(AdminApiError);
    expect(error).toMatchObject({
      kind,
      code: status === 404 || status === 409 ? code : undefined,
      message: 'The administrator request could not be completed.',
    });
    expect(JSON.stringify(error)).not.toContain('provider token');
    expect(String(error)).not.toContain('database trace');
  });

  it.each([
    ['invalid JSON', new Response('provider stack', { status: 200 })],
    ['malformed success', Response.json({ ...source, direct_text: 'Fictional policy.', assistant_id: '44444444-4444-4444-8444-444444444444' })],
  ])('maps knowledge %s to a safe invalid response', async (_scenario, response) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response));
    await expect(createAdminApi(base).getKnowledgeSource(assistant.id, source.id)).rejects.toMatchObject({
      kind: 'invalid_response',
      message: 'The administrator request could not be completed.',
    });
  });

  it.each([
    ['direct_text', 'enabled'],
    ['direct_text', 'disabled'],
    ['url', 'enabled'],
    ['url', 'disabled'],
  ] as const)('accepts %s sources in the %s retrieval state', async (source_type, retrieval_state) => {
    const body = source_type === 'url'
      ? { ...source, source_type, retrieval_state, url: 'https://example.test/guide', direct_text: null }
      : { ...source, source_type, retrieval_state, url: null, direct_text: 'Fictional policy.' };
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json(body)));
    await expect(createAdminApi(base).getKnowledgeSource(assistant.id, source.id)).resolves.toMatchObject({
      sourceType: source_type,
      retrievalState: retrieval_state,
    });
  });

  it('preserves supplied re-ingestion keys across retry and independent operations', async () => {
    const detail = { ...source, direct_text: 'Fictional policy.' };
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(Response.json(detail, { status: 202 })));
    vi.stubGlobal('fetch', fetchMock);
    const api = createAdminApi(base);

    await api.reingestKnowledgeSource(assistant.id, source.id, 'same-reingestion-key');
    await api.reingestKnowledgeSource(assistant.id, source.id, 'same-reingestion-key');
    await api.reingestKnowledgeSource(assistant.id, source.id, 'independent-reingestion-key');

    expect(fetchMock.mock.calls.map((call) => (call[1]?.headers as Record<string, string>)['Idempotency-Key']))
      .toEqual(['same-reingestion-key', 'same-reingestion-key', 'independent-reingestion-key']);
  });

  const behaviour = {
    assistant_id: assistant.id,
    draft: {
      revision: 2,
      instructions: '  Preserve leading space\n\nAnd trailing space  ',
      welcome_message: 'Welcome to the fictional assistant.',
      input_placeholder: 'Ask about policy',
      suggested_questions: ['What is covered?', 'How do I appeal?'],
      created_at: '2026-08-10T09:00:00Z',
    },
    published: { revision: 1, published_at: '2026-08-09T09:00:00Z' },
    has_unpublished_changes: true,
    concurrency_token: '2',
  };

  it('uses exact behaviour read, save, and publish contracts without normalising prompt content', async () => {
    const saved = { ...behaviour, concurrency_token: '3', draft: { ...behaviour.draft, revision: 3 } };
    const published = {
      ...saved,
      published: { revision: 3, published_at: '2026-08-10T10:00:00Z' },
      has_unpublished_changes: false,
      concurrency_token: '4',
    };
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(Response.json(behaviour))
      .mockResolvedValueOnce(Response.json(saved))
      .mockResolvedValueOnce(Response.json(published));
    vi.stubGlobal('fetch', fetchMock);
    const api = createAdminApi(base);

    await api.getAssistantBehaviour(assistant.id);
    await api.updateAssistantBehaviour(assistant.id, {
      concurrency_token: '2',
      instructions: behaviour.draft.instructions,
      welcome_message: behaviour.draft.welcome_message,
      input_placeholder: behaviour.draft.input_placeholder,
      suggested_questions: behaviour.draft.suggested_questions,
    });
    await api.publishAssistantBehaviour(assistant.id, {
      concurrency_token: '3',
      draft_revision: 3,
    });

    const path = `${base}/admin/assistants/${assistant.id}/behaviour`;
    expect(fetchMock.mock.calls[0]).toEqual([path, expect.objectContaining({ method: 'GET', credentials: 'include' })]);
    expect(fetchMock.mock.calls[1]?.[1]).toEqual(expect.objectContaining({
      method: 'PUT',
      credentials: 'include',
      body: JSON.stringify({
        concurrency_token: '2',
        instructions: behaviour.draft.instructions,
        welcome_message: behaviour.draft.welcome_message,
        input_placeholder: behaviour.draft.input_placeholder,
        suggested_questions: behaviour.draft.suggested_questions,
      }),
    }));
    expect(fetchMock.mock.calls[2]?.[0]).toBe(`${path}/publish`);
    expect(fetchMock.mock.calls[2]?.[1]).toEqual(expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ concurrency_token: '3', draft_revision: 3 }),
    }));
  });

  it.each([
    { ...behaviour, assistant_id: source.id },
    { ...behaviour, draft: { ...behaviour.draft, revision: 0 } },
    { ...behaviour, draft: { ...behaviour.draft, suggested_questions: ['', 'Valid?'] } },
    { ...behaviour, published: { revision: 1, published_at: 'yesterday' } },
    { ...behaviour, has_unpublished_changes: false },
    { ...behaviour, extra: 'unsupported' },
  ])('rejects malformed behaviour state responses', async (body) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json(body)));
    await expect(createAdminApi(base).getAssistantBehaviour(assistant.id)).rejects.toMatchObject({ kind: 'invalid_response' });
  });

  it('rejects malformed successful publication state', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json({
      ...behaviour,
      published: { revision: 2, published_at: 'not-a-timestamp' },
      has_unpublished_changes: false,
    })));

    await expect(createAdminApi(base).publishAssistantBehaviour(assistant.id, {
      concurrency_token: '2',
      draft_revision: 2,
    })).rejects.toMatchObject({ kind: 'invalid_response' });
  });

  it('uses the authenticated saved-draft preview SSE contract and validates completion', async () => {
    const stream = [
      'event: start\ndata: {"assistant":"legal-review"}',
      'event: delta\ndata: {"text":"A fictional "}',
      'event: delta\ndata: {"text":"answer."}',
      'event: complete\ndata: {"finishReason":"stop"}',
      '',
    ].join('\n\n');
    const fetchMock = vi.fn().mockResolvedValue(new Response(stream, {
      headers: { 'Content-Type': 'text/event-stream; charset=utf-8' },
    }));
    vi.stubGlobal('fetch', fetchMock);

    await expect(createAdminApi(base).previewAssistantMessage(assistant.id, {
      message: 'Follow up?',
      history: [
        { role: 'user', content: 'First question' },
        { role: 'assistant', content: 'First answer' },
      ],
    })).resolves.toEqual({ answer: 'A fictional answer.' });
    expect(fetchMock).toHaveBeenCalledWith(
      `${base}/admin/assistants/${assistant.id}/preview/chat`,
      expect.objectContaining({
        method: 'POST',
        credentials: 'include',
        headers: expect.objectContaining({ Accept: 'text/event-stream' }),
        body: JSON.stringify({
          message: 'Follow up?',
          history: [
            { role: 'user', content: 'First question' },
            { role: 'assistant', content: 'First answer' },
          ],
        }),
      }),
    );
  });

  it('surfaces preview deltas before the response completes', async () => {
    let streamController!: ReadableStreamDefaultController<Uint8Array>;
    const body = new ReadableStream<Uint8Array>({
      start(controller) { streamController = controller; },
    });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(body, {
      headers: { 'Content-Type': 'text/event-stream' },
    })));
    const onDelta = vi.fn();
    const pending = createAdminApi(base).previewAssistantMessage(
      assistant.id,
      { message: 'Question', history: [] },
      { signal: new AbortController().signal, onDelta },
    );

    streamController.enqueue(new TextEncoder().encode(
      'event: start\ndata: {"assistant":"legal-review"}\n\n' +
      'event: delta\ndata: {"text":"First "}\n\n',
    ));
    await vi.waitFor(() => expect(onDelta).toHaveBeenCalledWith('First '));

    streamController.enqueue(new TextEncoder().encode(
      'event: delta\ndata: {"text":"answer."}\n\n' +
      'event: complete\ndata: {"finishReason":"stop"}\n\n',
    ));
    await expect(pending).resolves.toEqual({ answer: 'First answer.' });
  });

  it('maps an interrupted preview stream safely after partial output', async () => {
    let streamController!: ReadableStreamDefaultController<Uint8Array>;
    const body = new ReadableStream<Uint8Array>({
      start(controller) { streamController = controller; },
    });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(body, {
      headers: { 'Content-Type': 'text/event-stream' },
    })));
    const onDelta = vi.fn();
    const pending = createAdminApi(base).previewAssistantMessage(
      assistant.id,
      { message: 'Question', history: [] },
      { signal: new AbortController().signal, onDelta },
    );
    streamController.enqueue(new TextEncoder().encode(
      'event: start\ndata: {"assistant":"legal-review"}\n\n' +
      'event: delta\ndata: {"text":"partial"}\n\n',
    ));
    await vi.waitFor(() => expect(onDelta).toHaveBeenCalledWith('partial'));

    streamController.error(new TypeError('private network detail'));

    await expect(pending).rejects.toMatchObject({
      kind: 'network',
      message: 'The administrator request could not be completed.',
    });
  });

  it('aborts an active preview stream without processing more deltas', async () => {
    let streamController!: ReadableStreamDefaultController<Uint8Array>;
    const body = new ReadableStream<Uint8Array>({
      start(controller) { streamController = controller; },
    });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(body, {
      headers: { 'Content-Type': 'text/event-stream' },
    })));
    const controller = new AbortController();
    const onDelta = vi.fn();
    const pending = createAdminApi(base).previewAssistantMessage(
      assistant.id,
      { message: 'Question', history: [] },
      { signal: controller.signal, onDelta },
    );
    streamController.enqueue(new TextEncoder().encode(
      'event: start\ndata: {"assistant":"legal-review"}\n\n' +
      'event: delta\ndata: {"text":"partial"}\n\n',
    ));
    await vi.waitFor(() => expect(onDelta).toHaveBeenCalledOnce());

    controller.abort();

    await expect(pending).rejects.toMatchObject({ name: 'AbortError' });
    expect(onDelta).toHaveBeenCalledOnce();
  });

  it.each([
    ['wrong media type', new Response('{}', { headers: { 'Content-Type': 'application/json' } })],
    ['missing completion', new Response('event: delta\ndata: {"text":"partial"}\n\n', { headers: { 'Content-Type': 'text/event-stream' } })],
    ['unsupported event payload', new Response('event: delta\ndata: {"content":"raw"}\n\nevent: complete\ndata: {"finishReason":"stop"}\n\n', { headers: { 'Content-Type': 'text/event-stream' } })],
  ])('rejects malformed preview success: %s', async (_scenario, response) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response));
    await expect(createAdminApi(base).previewAssistantMessage(assistant.id, { message: 'Question', history: [] }))
      .rejects.toMatchObject({ kind: 'invalid_response' });
  });

  it('forwards cancellation for behaviour reads and safely maps preview failures', async () => {
    const controller = new AbortController();
    const fetchMock = vi.fn((_input: RequestInfo | URL, init?: RequestInit) =>
      new Promise<Response>((_resolve, reject) => {
        init?.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')));
      }));
    vi.stubGlobal('fetch', fetchMock);
    const pending = createAdminApi(base).getAssistantBehaviour(assistant.id, controller.signal);
    controller.abort();
    await expect(pending).rejects.toMatchObject({ name: 'AbortError' });

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json({
      detail: { code: 'assistant_preview_unavailable', message: 'provider prompt and stack trace' },
    }, { status: 409 })));
    await expect(createAdminApi(base).previewAssistantMessage(assistant.id, { message: 'Question', history: [] }))
      .rejects.toMatchObject({
        kind: 'conflict',
        code: 'assistant_preview_unavailable',
        message: 'The administrator request could not be completed.',
      });
  });
});

describe('Operations API', () => {
  const id = '11111111-1111-4111-8111-111111111111';
  const timestamp = '2026-08-25T10:00:00Z';
  const action = { success: true, request_id: 'request-1', correlation_id: 'correlation-1' };
  const job = { id, status:'failed', created_at:timestamp, started_at:timestamp, completed_at:timestamp, duration_ms:12, retry_count:1, last_error:'Safe failure', execution_node:'worker-1', job_type:'ingestion' };
  const audit = { id, timestamp, user:'admin@example.test', action:'cache.clear', resource:'cache', result:'SUCCESS' };

  it('requests and strictly maps root, health, cache, and maintenance reads', async () => {
    const fetchMock=vi.fn()
      .mockResolvedValueOnce(Response.json({generated_at:timestamp,service:'operations',status:'available',capabilities:['health','cache']}))
      .mockResolvedValueOnce(Response.json({generated_at:timestamp,status:'degraded',checks:[{name:'postgres',status:'unhealthy',required:true,latency_ms:25,code:'dependency_unavailable',checked_at:timestamp}]}))
      .mockResolvedValueOnce(Response.json({items:[{name:'assistant',entries:null,estimated_memory_bytes:null,hit_count:5,miss_count:1,hit_ratio:0.833}]}))
      .mockResolvedValueOnce(Response.json({enabled:true,message:'Planned work',updated_at:timestamp,updated_by:'admin',request_id:null,correlation_id:null}));
    vi.stubGlobal('fetch',fetchMock); const api=createAdminApi(base); const signal=new AbortController().signal;
    await expect(api.getOperations(signal)).resolves.toEqual({generatedAt:timestamp,service:'operations',status:'available',capabilities:['health','cache']});
    await expect(api.getOperationsHealth(signal)).resolves.toMatchObject({status:'degraded',checks:[{name:'postgres',status:'unhealthy',latencyMs:25}]});
    await expect(api.listCacheRegions(signal)).resolves.toEqual([{name:'assistant',entries:null,estimatedMemoryBytes:null,hitCount:5,missCount:1,hitRatio:0.833}]);
    await expect(api.getMaintenance(signal)).resolves.toMatchObject({enabled:true,message:'Planned work',requestId:null});
    expect(fetchMock.mock.calls.map((call)=>call[0])).toEqual([`${base}/admin/operations`,`${base}/admin/operations/health`,`${base}/admin/operations/cache`,`${base}/admin/operations/maintenance`]);
    expect(fetchMock.mock.calls.every((call)=>call[1]?.credentials==='include'&&call[1]?.signal===signal)).toBe(true);
  });

  it('accepts the backend health serialization when a null diagnostic code is omitted', async () => {
    vi.stubGlobal('fetch',vi.fn().mockResolvedValue(Response.json({
      generated_at:timestamp,status:'healthy',checks:[{
        name:'postgres',status:'healthy',required:true,latency_ms:5,checked_at:timestamp,
      }],
    })));

    await expect(createAdminApi(base).getOperationsHealth()).resolves.toEqual({
      generatedAt:timestamp,status:'healthy',checks:[{
        name:'postgres',status:'healthy',required:true,latencyMs:5,code:null,checkedAt:timestamp,
      }],
    });
  });

  it.each([
    ['explicit null code',{name:'postgres',status:'healthy',required:true,latency_ms:5,code:null,checked_at:timestamp},null],
    ['supported diagnostic code',{name:'postgres',status:'degraded',required:true,latency_ms:5,code:'dependency_timeout',checked_at:timestamp},'dependency_timeout'],
  ])('accepts a health check with %s',async(_scenario,check,expectedCode)=>{
    vi.stubGlobal('fetch',vi.fn().mockResolvedValue(Response.json({generated_at:timestamp,status:check.status,checks:[check]})));
    await expect(createAdminApi(base).getOperationsHealth()).resolves.toMatchObject({checks:[{code:expectedCode}]});
  });

  it.each([
    ['unknown code',{name:'postgres',status:'unhealthy',required:true,latency_ms:5,code:'unknown_failure',checked_at:timestamp}],
    ['unexpected property',{name:'postgres',status:'healthy',required:true,latency_ms:5,checked_at:timestamp,detail:'private'}],
    ['missing required field',{name:'postgres',status:'healthy',latency_ms:5,checked_at:timestamp}],
  ])('rejects a health check with %s',async(_scenario,check)=>{
    vi.stubGlobal('fetch',vi.fn().mockResolvedValue(Response.json({generated_at:timestamp,status:'healthy',checks:[check]})));
    await expect(createAdminApi(base).getOperationsHealth()).rejects.toMatchObject({kind:'invalid_response'});
  });

  it('uses exact cache mutation contracts, URL encoding, and validates success', async () => {
    const fetchMock=vi.fn().mockImplementation(async()=>Response.json(action));vi.stubGlobal('fetch',fetchMock);const api=createAdminApi(base);
    await api.clearCache(); await api.clearCacheRegion('assistant region'); await api.invalidateCacheKey({region:'assistant',key:'private key'});
    expect(fetchMock.mock.calls.map((call)=>[call[0],call[1]?.method])).toEqual([[`${base}/admin/operations/cache/clear`,'POST'],[`${base}/admin/operations/cache/regions/assistant%20region/clear`,'POST'],[`${base}/admin/operations/cache/key`,'POST']]);
    expect(fetchMock.mock.calls[2]?.[1]?.body).toBe(JSON.stringify({region:'assistant',key:'private key'}));
    vi.stubGlobal('fetch',vi.fn().mockResolvedValue(Response.json({...action,success:false})));
    await expect(createAdminApi(base).clearCache()).rejects.toMatchObject({kind:'invalid_response'});
  });

  it('serializes maintenance, job pagination/status, and audit filters exactly', async () => {
    const maintenance={enabled:false,message:null,updated_at:timestamp,updated_by:'admin',request_id:'r',correlation_id:'c'};
    const fetchMock=vi.fn().mockResolvedValueOnce(Response.json(maintenance)).mockResolvedValueOnce(Response.json({items:[job],total:1,limit:25,offset:0})).mockResolvedValueOnce(Response.json({items:[audit],total:21,limit:10,offset:20}));
    vi.stubGlobal('fetch',fetchMock);const api=createAdminApi(base);
    await api.updateMaintenance({enabled:false,message:null});
    await api.listOperationalJobs({limit:25,offset:0,status:'failed'});
    await api.listAuditEntries({limit:10,offset:20,user:'admin',action:'cache.clear',resource:'cache',result:'SUCCESS',dateFrom:'2026-08-01T00:00:00Z',dateTo:'2026-08-25T00:00:00Z'});
    expect(fetchMock.mock.calls[0]?.[1]?.body).toBe(JSON.stringify({enabled:false,message:null}));
    expect(fetchMock.mock.calls[1]?.[0]).toBe(`${base}/admin/operations/jobs?limit=25&offset=0&status=failed`);
    const auditUrl=String(fetchMock.mock.calls[2]?.[0]);expect(auditUrl).toContain('limit=10&offset=20');expect(auditUrl).toContain('result=SUCCESS');expect(auditUrl).toContain('date_from=2026-08-01T00%3A00%3A00Z');expect(auditUrl).toContain('date_to=2026-08-25T00%3A00%3A00Z');
  });

  it('maps job and audit details and rejects malformed successful structures', async () => {
    const detail={...audit,actor:'admin@example.test',request_id:'request',correlation_id:'correlation',duration_ms:3,metadata:{enabled:true}};
    const fetchMock=vi.fn().mockResolvedValueOnce(Response.json(job)).mockResolvedValueOnce(Response.json(detail));vi.stubGlobal('fetch',fetchMock);const api=createAdminApi(base);
    await expect(api.getOperationalJob(id)).resolves.toMatchObject({id,status:'failed',durationMs:12,lastError:'Safe failure'});
    await expect(api.getAuditEntry(id)).resolves.toMatchObject({id,result:'SUCCESS',metadata:{enabled:true}});
    for(const malformed of [
      {generated_at:timestamp,service:'operations',status:'available',capabilities:['health','invented']},
      {generated_at:timestamp,status:'healthy',checks:[{name:'db',status:'invented',required:true,latency_ms:0,code:null,checked_at:timestamp}]},
      {items:[{name:'assistant',entries:-1,estimated_memory_bytes:null,hit_count:null,miss_count:null,hit_ratio:null}]},
      {...job,status:'retrying'},
      {...detail,result:'OK'},
    ]){vi.stubGlobal('fetch',vi.fn().mockResolvedValue(Response.json(malformed)));const request='capabilities' in malformed?api.getOperations():Array.isArray((malformed as {items?:unknown[]}).items)?api.listCacheRegions():('checks' in malformed?api.getOperationsHealth():('job_type' in malformed?api.getOperationalJob(id):api.getAuditEntry(id)));await expect(request).rejects.toMatchObject({kind:'invalid_response'});}
  });

  it('preserves safe failure mapping, network errors, and AbortSignal cancellation', async () => {
    for(const [status,kind] of [[400,'invalid_request'],[401,'unauthenticated'],[403,'forbidden'],[404,'not_found'],[409,'conflict'],[422,'invalid_request'],[503,'server']] as const){vi.stubGlobal('fetch',vi.fn().mockResolvedValue(Response.json({detail:{code:'safe_code'}},{status})));await expect(createAdminApi(base).getOperations()).rejects.toMatchObject({kind});}
    vi.stubGlobal('fetch',vi.fn().mockRejectedValue(new TypeError('offline')));await expect(createAdminApi(base).getOperations()).rejects.toMatchObject({kind:'network'});
    const aborted=new DOMException('aborted','AbortError');vi.stubGlobal('fetch',vi.fn().mockRejectedValue(aborted));await expect(createAdminApi(base).getOperations(new AbortController().signal)).rejects.toBe(aborted);
  });
});
