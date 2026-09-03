import { API_URL, type UserRole } from '../utils/settings';

export const getRagChat = async ({
  query,
  userRole,
}: {
  query: string;
  userRole: UserRole;
}) => {
  const controller = new AbortController();

  const timeoutId = window.setTimeout(() => {
    controller.abort();
  }, 30000);

  try {
    const res = await fetch(`${API_URL}/rag-chat`, {
      method: 'POST',
      credentials: 'include',
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
