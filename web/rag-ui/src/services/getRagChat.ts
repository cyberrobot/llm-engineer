import { API_URL } from '../utils/settings';

const controller = new AbortController();

const timeoutId = window.setTimeout(() => {
  controller.abort();
}, 8000);

export const getRagChat = async ({
  query,
  userRole,
}: {
  query: string;
  userRole: string;
}) => {
  try {
    const res = await fetch(`${API_URL}/rag-chat`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
      },
      body: JSON.stringify({
        message: query,
        user_role: userRole,
      }),
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
