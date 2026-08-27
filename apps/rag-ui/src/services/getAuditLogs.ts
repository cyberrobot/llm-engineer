import { API_URL } from '../utils/settings';

export const getAuditLogs = async () => {
  const controller = new AbortController();

  const timeoutId = globalThis.setTimeout(() => {
    controller.abort();
  }, 30000);

  try {
    const res = await fetch(`${API_URL}/admin/operations/audit/rag`, {
      method: 'GET',
      headers: {
        Accept: 'application/json',
      },
      credentials: 'include',
      signal: controller.signal,
    });

    if (!res.ok) {
      throw new Error(`Request failed: ${res.status}`);
    }

    return await res.json();
  } finally {
    clearTimeout(timeoutId);
  }
};
