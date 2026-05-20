import { API_URL } from '../utils/settings';

const controller = new AbortController();

const timeoutId = window.setTimeout(() => {
  controller.abort();
}, 8000);

export const getAuditLogs = async () => {
  try {
    const res = await fetch(`${API_URL}/audit-logs`, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      },
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
