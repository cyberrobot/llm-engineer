import { afterEach, describe, expect, it, vi } from 'vitest';

describe('getAuditLogs', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
    vi.resetModules();
  });

  it('loads RAG history through the credentialed Operations audit extension', async () => {
    vi.stubEnv('VITE_API_URL', 'https://backend.test');
    const records = [{ id: 7, question: 'What is required?' }];
    const fetchImplementation = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(records), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    vi.stubGlobal('fetch', fetchImplementation);
    const { getAuditLogs } = await import('./getAuditLogs');

    await expect(getAuditLogs()).resolves.toEqual(records);
    expect(fetchImplementation).toHaveBeenCalledWith(
      'https://backend.test/admin/operations/audit/rag',
      expect.objectContaining({ method: 'GET', credentials: 'include' }),
    );
  });

  it('surfaces administrator authentication failures', async () => {
    vi.stubEnv('VITE_API_URL', 'https://backend.test');
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 401 })));
    const { getAuditLogs } = await import('./getAuditLogs');

    await expect(getAuditLogs()).rejects.toThrow('Request failed: 401');
  });
});
