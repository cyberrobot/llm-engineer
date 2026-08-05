export type Administrator = { id: string; email: string; role: 'administrator' };
export type AdminApiErrorKind =
  | 'unauthenticated'
  | 'invalid_credentials'
  | 'throttled'
  | 'invalid_request'
  | 'not_found'
  | 'conflict'
  | 'forbidden'
  | 'network'
  | 'server'
  | 'invalid_response';

export class AdminApiError extends Error {
  readonly kind: AdminApiErrorKind;
  readonly code?: string;

  constructor(kind: AdminApiErrorKind, code?: string) {
    super('The administrator request could not be completed.');
    this.name = 'AdminApiError';
    this.kind = kind;
    this.code = code;
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

async function failure(response: Response, context: 'login' | 'session' | 'logout' | 'assistant'): Promise<never> {
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
  if (response.status === 404) throw new AdminApiError('not_found', typeof code === 'string' ? code : undefined);
  if (response.status === 409) throw new AdminApiError('conflict', typeof code === 'string' ? code : undefined);
  if (response.status === 422) throw new AdminApiError('invalid_request');
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
    async listAssistants(options = {}, signal?: AbortSignal) {
      const params = new URLSearchParams();
      params.set('limit', String(options.limit ?? 50));
      params.set('offset', String(options.offset ?? 0));
      if (options.status) params.set('status', options.status);
      if (options.visibility) params.set('visibility', options.visibility);
      const response = await request(baseUrl, `/admin/assistants?${params}`, { method: 'GET', signal });
      if (!response.ok) return failure(response, 'assistant');
      return assistantListFrom(await successfulJson(response));
    },
    async getAssistant(id, signal) {
      const response = await request(baseUrl, `/admin/assistants/${encodeURIComponent(id)}`, { method: 'GET', signal });
      if (!response.ok) return failure(response, 'assistant');
      return assistantDetailFrom(await successfulJson(response));
    },
    async createAssistant(input, signal) {
      const response = await request(baseUrl, '/admin/assistants', jsonRequest('POST', input, signal));
      if (!response.ok) return failure(response, 'assistant');
      return assistantFrom(await successfulJson(response));
    },
    async updateAssistant(id, input, signal) {
      const response = await request(baseUrl, `/admin/assistants/${encodeURIComponent(id)}`, jsonRequest('PATCH', input, signal));
      if (!response.ok) return failure(response, 'assistant');
      return assistantFrom(await successfulJson(response));
    },
    async deleteAssistant(id, signal) {
      const response = await request(baseUrl, `/admin/assistants/${encodeURIComponent(id)}`, { method: 'DELETE', signal });
      if (!response.ok) return failure(response, 'assistant');
      if (response.status !== 204) throw new AdminApiError('invalid_response');
    },
  };
}

export type AssistantStatus = 'active' | 'inactive';
export type AssistantVisibility = 'public' | 'private';
export type Assistant = { id: string; slug: string; name: string; status: AssistantStatus; visibility: AssistantVisibility; createdAt: string; updatedAt: string; concurrencyToken: string };
export type AssistantDetail = Assistant & { knowledgeSourceCount: number; deletionAllowed: boolean };
export type AssistantList = { items: Assistant[]; total: number; limit: number; offset: number };
export type CreateAssistant = { slug: string; name: string; status: AssistantStatus; visibility: AssistantVisibility };
export type UpdateAssistant = { concurrency_token: string; name?: string; status?: AssistantStatus; visibility?: AssistantVisibility };

const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const slug = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
function timestamp(value: unknown): value is string { return typeof value === 'string' && !Number.isNaN(Date.parse(value)); }
function assistantFrom(value: unknown): Assistant {
  if (!isRecord(value) || !uuid.test(String(value.id)) || typeof value.slug !== 'string' || !slug.test(value.slug) || typeof value.name !== 'string' || !value.name.trim() || !['active','inactive'].includes(String(value.status)) || !['public','private'].includes(String(value.visibility)) || !timestamp(value.created_at) || !timestamp(value.updated_at) || !timestamp(value.concurrency_token)) throw new AdminApiError('invalid_response');
  return { id: String(value.id), slug: value.slug, name: value.name, status: value.status as AssistantStatus, visibility: value.visibility as AssistantVisibility, createdAt: value.created_at, updatedAt: value.updated_at, concurrencyToken: value.concurrency_token };
}
function assistantDetailFrom(value: unknown): AssistantDetail {
  const item = assistantFrom(value);
  if (!isRecord(value) || !Number.isInteger(value.knowledge_source_count) || Number(value.knowledge_source_count) < 0 || typeof value.deletion_allowed !== 'boolean') throw new AdminApiError('invalid_response');
  return { ...item, knowledgeSourceCount: Number(value.knowledge_source_count), deletionAllowed: value.deletion_allowed };
}
function assistantListFrom(value: unknown): AssistantList {
  if (!isRecord(value) || !Array.isArray(value.items) || !Number.isInteger(value.total) || !Number.isInteger(value.limit) || !Number.isInteger(value.offset) || Number(value.total) < 0 || Number(value.limit) < 1 || Number(value.offset) < 0) throw new AdminApiError('invalid_response');
  return { items: value.items.map(assistantFrom), total: Number(value.total), limit: Number(value.limit), offset: Number(value.offset) };
}
function jsonRequest(method: string, body: unknown, signal?: AbortSignal): RequestInit { return { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body), signal }; }

export interface AdminApi {
  login(email: string, password: string, signal?: AbortSignal): Promise<Administrator>;
  currentUser(signal?: AbortSignal): Promise<Administrator>;
  logout(signal?: AbortSignal): Promise<void>;
  listAssistants(options?: { limit?: number; offset?: number; status?: AssistantStatus; visibility?: AssistantVisibility }, signal?: AbortSignal): Promise<AssistantList>;
  getAssistant(id: string, signal?: AbortSignal): Promise<AssistantDetail>;
  createAssistant(input: CreateAssistant, signal?: AbortSignal): Promise<Assistant>;
  updateAssistant(id: string, input: UpdateAssistant, signal?: AbortSignal): Promise<Assistant>;
  deleteAssistant(id: string, signal?: AbortSignal): Promise<void>;
}
