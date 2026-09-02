import { API_URL } from '../utils/settings';

export const getCurrentAdministrator = async () => {
  const res = await fetch(`${API_URL}/admin/auth/me`, {
    method: 'GET',
    credentials: 'include',
    headers: {
      Accept: 'application/json',
    },
  });

  if (!res.ok) {
    throw new Error(`Request failed: ${res.status}`);
  }

  return await res.json();
};
