import { afterEach, describe, expect, it, vi } from 'vitest';

describe('getRagChat', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
    vi.resetModules();
  });

  it('uses the credentialed administrator RAG endpoint and preserves its response', async () => {
    vi.stubEnv('VITE_API_URL', 'https://backend.test');
    const payload = {
      reply: { answer: 'Use the checklist.', source_ids: ['chunk-1'] },
      sources: [{ id: 'chunk-1', text: 'Checklist' }],
      evaluation: { metrics: { groundedness_score: 1 } },
    };
    const fetchImplementation = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(payload), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    vi.stubGlobal('fetch', fetchImplementation);
    const { getRagChat } = await import('./getRagChat');

    await expect(
      getRagChat({ query: 'What is required?', userRole: 'manager' }),
    ).resolves.toEqual(payload);
    expect(fetchImplementation).toHaveBeenCalledWith(
      'https://backend.test/admin/assistants/rag-chat',
      expect.objectContaining({
        method: 'POST',
        credentials: 'include',
        body: JSON.stringify({
          message: 'What is required?',
          user_role: 'manager',
        }),
      }),
    );
  });

  it('surfaces administrator authentication failures', async () => {
    vi.stubEnv('VITE_API_URL', 'https://backend.test');
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 401 })));
    const { getRagChat } = await import('./getRagChat');

    await expect(getRagChat({ query: 'Question', userRole: 'doctor' })).rejects.toThrow(
      'Request failed: 401',
    );
  });
});
