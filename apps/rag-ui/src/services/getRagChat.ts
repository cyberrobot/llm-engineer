import { API_URL } from '../utils/settings';

export const getRagChat = async ({
  query,
  userRole,
}: {
  query: string;
  userRole: string;
}) => {
  const controller = new AbortController();

  const timeoutId = globalThis.setTimeout(() => {
    controller.abort();
  }, 30000);

  try {
    const res = await fetch(`${API_URL}/admin/assistants/rag-chat`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
      },
      body: JSON.stringify({
        message: query,
        user_role: userRole,
      }),
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
