export type Administrator = { id: string; email: string; role: 'administrator' };
export type AdminApiErrorKind =
  | 'unauthenticated'
  | 'invalid_credentials'
  | 'throttled'
  | 'invalid_request'
  | 'forbidden'
  | 'network'
  | 'server'
  | 'invalid_response';

export class AdminApiError extends Error {
  readonly kind: AdminApiErrorKind;

  constructor(kind: AdminApiErrorKind) {
    super('The administrator request could not be completed.');
    this.name = 'AdminApiError';
    this.kind = kind;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function hasExactKeys(value: Record<string, unknown>, expected: string[]): boolean {
  const keys = Object.keys(value);
  return keys.length === expected.length && expected.every((key) => keys.includes(key));
}

function userFrom(value: unknown): Administrator {
  if (!isRecord(value) || !hasExactKeys(value, ['user'])) {
    throw new AdminApiError('invalid_response');
  }

  const user = value.user;
  if (
    !isRecord(user) ||
    !hasExactKeys(user, ['id', 'email', 'role']) ||
    typeof user.id !== 'string' ||
    typeof user.email !== 'string' ||
    user.role !== 'administrator'
  ) {
    throw new AdminApiError('invalid_response');
  }

  return { id: user.id, email: user.email, role: user.role };
}

async function successfulJson(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    throw new AdminApiError('invalid_response');
  }
}

async function request(baseUrl: string, path: string, init: RequestInit): Promise<Response> {
  try {
    return await fetch(`${baseUrl}${path}`, {
      ...init,
      credentials: 'include',
      headers: { Accept: 'application/json', ...init.headers },
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error;
    throw new AdminApiError('network');
  }
}

async function failure(response: Response, context: 'login' | 'session' | 'logout'): Promise<never> {
  let code: unknown;
  try {
    const body: unknown = await response.json();
    code =
      isRecord(body) && isRecord(body.detail) && typeof body.detail.code === 'string'
        ? body.detail.code
        : undefined;
  } catch {
    // Deliberately discard raw bodies.
  }

  if (response.status === 401) {
    throw new AdminApiError(
      context === 'login' && code === 'invalid_credentials'
        ? 'invalid_credentials'
        : 'unauthenticated',
    );
  }
  if (response.status === 429 && code === 'too_many_login_attempts') throw new AdminApiError('throttled');
  if (response.status === 400) throw new AdminApiError('invalid_request');
  if (response.status === 403) throw new AdminApiError('forbidden');
  throw new AdminApiError(response.status >= 500 ? 'server' : 'invalid_response');
}

export function createAdminApi(baseUrl: string): AdminApi {
  return {
    async login(email: string, password: string, signal?: AbortSignal) {
      const response = await request(baseUrl, '/admin/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
        signal,
      });
      if (!response.ok) return failure(response, 'login');
      return userFrom(await successfulJson(response));
    },
    async currentUser(signal?: AbortSignal) {
      const response = await request(baseUrl, '/admin/auth/me', { method: 'GET', signal });
      if (!response.ok) return failure(response, 'session');
      return userFrom(await successfulJson(response));
    },
    async logout(signal?: AbortSignal) {
      const response = await request(baseUrl, '/admin/auth/logout', { method: 'POST', signal });
      if (!response.ok) return failure(response, 'logout');
      if (response.status !== 204) throw new AdminApiError('invalid_response');
    },
  };
}

export interface AdminApi {
  login(email: string, password: string, signal?: AbortSignal): Promise<Administrator>;
  currentUser(signal?: AbortSignal): Promise<Administrator>;
  logout(signal?: AbortSignal): Promise<void>;
}
