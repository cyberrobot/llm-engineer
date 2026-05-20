import { API_URL } from '../utils/settings';

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
    });

    return await res.json();
  } catch (error) {
    return error instanceof Error
      ? error.message
      : 'Failed to return a chat response';
  }
};
