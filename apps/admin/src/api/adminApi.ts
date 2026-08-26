import {
  AssistantChatError,
  consumeAssistantEventStream,
} from '@redmoor/assistant-widget';

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

async function failure(response: Response, context: 'login' | 'session' | 'logout' | 'assistant' | 'operations'): Promise<never> {
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
    async getOperationsSummary(signal?: AbortSignal) {
      const response = await request(baseUrl, '/admin/operations/summary', { method: 'GET', signal });
      if (!response.ok) return failure(response, 'operations');
      return operationsSummaryFrom(await successfulJson(response));
    },
    async getOperations(signal?: AbortSignal) {
      const response = await request(baseUrl, '/admin/operations', { method: 'GET', signal });
      if (!response.ok) return failure(response, 'operations');
      return operationsRootFrom(await successfulJson(response));
    },
    async getOperationsHealth(signal?: AbortSignal) {
      const response = await request(baseUrl, '/admin/operations/health', { method: 'GET', signal });
      if (!response.ok) return failure(response, 'operations');
      return operationsHealthFrom(await successfulJson(response));
    },
    async listCacheRegions(signal?: AbortSignal) {
      const response = await request(baseUrl, '/admin/operations/cache', { method: 'GET', signal });
      if (!response.ok) return failure(response, 'operations');
      return cacheRegionsFrom(await successfulJson(response));
    },
    async clearCache(signal?: AbortSignal) {
      return actionRequest(baseUrl, '/admin/operations/cache/clear', { method: 'POST', signal });
    },
    async clearCacheRegion(region: string, signal?: AbortSignal) {
      return actionRequest(baseUrl, `/admin/operations/cache/regions/${encodeURIComponent(region)}/clear`, { method: 'POST', signal });
    },
    async invalidateCacheKey(input: CacheKeyInvalidation, signal?: AbortSignal) {
      return actionRequest(baseUrl, '/admin/operations/cache/key', jsonRequest('POST', input, signal));
    },
    async getMaintenance(signal?: AbortSignal) {
      const response = await request(baseUrl, '/admin/operations/maintenance', { method: 'GET', signal });
      if (!response.ok) return failure(response, 'operations');
      return maintenanceFrom(await successfulJson(response));
    },
    async updateMaintenance(input: MaintenanceUpdate, signal?: AbortSignal) {
      const response = await request(baseUrl, '/admin/operations/maintenance', jsonRequest('PUT', input, signal));
      if (!response.ok) return failure(response, 'operations');
      return maintenanceFrom(await successfulJson(response));
    },
    async listOperationalJobs(options = {}, signal?: AbortSignal) {
      const params = pageParams(options);
      if (options.status) params.set('status', options.status);
      const response = await request(baseUrl, `/admin/operations/jobs?${params}`, { method: 'GET', signal });
      if (!response.ok) return failure(response, 'operations');
      return operationalJobsFrom(await successfulJson(response));
    },
    async getOperationalJob(id: string, signal?: AbortSignal) {
      const response = await request(baseUrl, `/admin/operations/jobs/${encodeURIComponent(id)}`, { method: 'GET', signal });
      if (!response.ok) return failure(response, 'operations');
      return operationalJobFrom(await successfulJson(response));
    },
    async listAuditEntries(options = {}, signal?: AbortSignal) {
      const params = pageParams(options);
      for (const [key, value] of Object.entries({ user: options.user, action: options.action, resource: options.resource, result: options.result, date_from: options.dateFrom, date_to: options.dateTo })) {
        if (value) params.set(key, value);
      }
      const response = await request(baseUrl, `/admin/operations/audit?${params}`, { method: 'GET', signal });
      if (!response.ok) return failure(response, 'operations');
      return auditPageFrom(await successfulJson(response));
    },
    async getAuditEntry(id: string, signal?: AbortSignal) {
      const response = await request(baseUrl, `/admin/operations/audit/${encodeURIComponent(id)}`, { method: 'GET', signal });
      if (!response.ok) return failure(response, 'operations');
      return auditDetailFrom(await successfulJson(response));
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
    async getAssistantBehaviour(id, signal) {
      const response = await request(baseUrl, behaviourPath(id), { method: 'GET', signal });
      if (!response.ok) return failure(response, 'assistant');
      return assistantBehaviourFrom(await successfulJson(response), id);
    },
    async updateAssistantBehaviour(id, input, signal) {
      const response = await request(baseUrl, behaviourPath(id), jsonRequest('PUT', input, signal));
      if (!response.ok) return failure(response, 'assistant');
      return assistantBehaviourFrom(await successfulJson(response), id);
    },
    async publishAssistantBehaviour(id, input, signal) {
      const response = await request(baseUrl, `${behaviourPath(id)}/publish`, jsonRequest('POST', input, signal));
      if (!response.ok) return failure(response, 'assistant');
      return assistantBehaviourFrom(await successfulJson(response), id);
    },
    async previewAssistantMessage(id, input, options = {}) {
      const response = await request(baseUrl, `/admin/assistants/${encodeURIComponent(id)}/preview/chat`, {
        ...jsonRequest('POST', input, options.signal),
        headers: { Accept: 'text/event-stream', 'Content-Type': 'application/json' },
      });
      if (!response.ok) return failure(response, 'assistant');
      if (!response.headers.get('content-type')?.toLowerCase().includes('text/event-stream')) {
        throw new AdminApiError('invalid_response');
      }
      try {
        return await consumeAssistantEventStream(response.body, {
          signal: options.signal ?? new AbortController().signal,
          onStart: options.onStart,
          onDelta: options.onDelta,
        });
      } catch (error: unknown) {
        if (error instanceof DOMException && error.name === 'AbortError') throw error;
        if (error instanceof AssistantChatError) {
          if (error.code === 'invalid_response') throw new AdminApiError('invalid_response');
          if (error.code === 'network_error') throw new AdminApiError('network');
          throw new AdminApiError('server');
        }
        throw error;
      }
    },
    async listKnowledgeSources(assistantId, options = {}, signal) {
      const params = new URLSearchParams({
        limit: String(options.limit ?? 50),
        offset: String(options.offset ?? 0),
      });
      const response = await request(baseUrl, `${knowledgePath(assistantId)}?${params}`, { method: 'GET', signal });
      if (!response.ok) return failure(response, 'assistant');
      return knowledgeSourceListFrom(await successfulJson(response), assistantId);
    },
    async getKnowledgeSource(assistantId, sourceId, signal) {
      const response = await request(baseUrl, `${knowledgePath(assistantId)}/${encodeURIComponent(sourceId)}`, { method: 'GET', signal });
      if (!response.ok) return failure(response, 'assistant');
      return knowledgeSourceFrom(await successfulJson(response), assistantId, true);
    },
    async createKnowledgeSource(assistantId, input, idempotencyKey, signal) {
      const response = await request(baseUrl, knowledgePath(assistantId), jsonRequest('POST', input, signal, { 'Idempotency-Key': idempotencyKey }));
      if (!response.ok) return failure(response, 'assistant');
      if (response.status !== 202) throw new AdminApiError('invalid_response');
      return knowledgeSourceFrom(await successfulJson(response), assistantId, true);
    },
    async updateKnowledgeSourceRetrieval(assistantId, sourceId, retrievalState, signal) {
      const response = await request(baseUrl, `${knowledgePath(assistantId)}/${encodeURIComponent(sourceId)}`, jsonRequest('PATCH', { retrieval_state: retrievalState }, signal));
      if (!response.ok) return failure(response, 'assistant');
      return knowledgeSourceFrom(await successfulJson(response), assistantId, true);
    },
    async reingestKnowledgeSource(assistantId, sourceId, idempotencyKey, signal) {
      const response = await request(baseUrl, `${knowledgePath(assistantId)}/${encodeURIComponent(sourceId)}/reingestions`, {
        method: 'POST', signal, headers: { 'Idempotency-Key': idempotencyKey },
      });
      if (!response.ok) return failure(response, 'assistant');
      if (response.status !== 202) throw new AdminApiError('invalid_response');
      return knowledgeSourceFrom(await successfulJson(response), assistantId, true);
    },
    async deleteKnowledgeSource(assistantId, sourceId, signal) {
      const response = await request(baseUrl, `${knowledgePath(assistantId)}/${encodeURIComponent(sourceId)}`, { method: 'DELETE', signal });
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
export type AssistantBehaviourDraft = {
  revision: number;
  instructions: string;
  welcomeMessage: string;
  inputPlaceholder: string;
  suggestedQuestions: string[];
  createdAt: string;
};
export type AssistantBehaviourPublished = { revision: number; publishedAt: string };
export type AssistantBehaviour = {
  assistantId: string;
  draft: AssistantBehaviourDraft;
  published: AssistantBehaviourPublished | null;
  hasUnpublishedChanges: boolean;
  concurrencyToken: string;
};
export type UpdateAssistantBehaviour = {
  concurrency_token: string;
  instructions: string;
  welcome_message: string;
  input_placeholder: string;
  suggested_questions: string[];
};
export type PublishAssistantBehaviour = { concurrency_token: string; draft_revision: number };
export type AssistantChatHistoryMessage = { role: 'user' | 'assistant'; content: string };
export type AssistantPreviewMessage = { message: string; history: AssistantChatHistoryMessage[] };
export type AssistantPreviewStreamOptions = {
  signal?: AbortSignal;
  onStart?: () => void;
  onDelta?: (delta: string) => void;
};
export type KnowledgeSourceType = 'direct_text' | 'url';
export type RetrievalState = 'enabled' | 'disabled';
export type IngestionStatus = 'queued' | 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
export type IngestionStep = 'parse' | 'chunk' | 'embed' | 'persist';
export type KnowledgeSourceJob = { id: string; status: IngestionStatus; currentStep: IngestionStep | null; createdAt: string; startedAt: string | null; completedAt: string | null; failureCode: string | null; failureMessage: string | null };
export type KnowledgeSource = { id: string; assistantId: string; sourceType: KnowledgeSourceType; name: string; retrievalState: RetrievalState; url: string | null; directText: string | null; documentId: string; createdAt: string; updatedAt: string; latestIngestion: KnowledgeSourceJob | null; activeJobReused: boolean };
export type KnowledgeSourceList = { items: KnowledgeSource[]; total: number; limit: number; offset: number };
export type CreateKnowledgeSource =
  | { source_type: 'direct_text'; name: string; direct_text: string }
  | { source_type: 'url'; name: string; url: string };
export type OperationsHealth = 'healthy' | 'degraded' | 'unhealthy' | 'unknown';
export type OperationsSummary = {
  generatedAt: string;
  health: OperationsHealth;
  maintenance: boolean;
  cache: { regions: number };
  jobs: { running: number; failed: number };
  audit: { today: number };
  assistants: { total: number; published: number };
  knowledgeSources: { total: number; enabled: number; failed: number | null };
  ingestion: {
    queued: number;
    running: number;
    recoverable: number;
    failed: number;
    oldestQueuedAgeSeconds: number;
    workersObserved: number;
  };
};
export type OperationsCapability = 'health' | 'cache' | 'audit' | 'maintenance' | 'jobs' | 'summary';
export type OperationsRoot = { generatedAt: string; service: 'operations'; status: 'available'; capabilities: OperationsCapability[] };
export type DependencyHealthCode = 'dependency_timeout' | 'dependency_unavailable' | 'dependency_authentication_failed' | 'dependency_misconfigured' | 'dependency_check_failed';
export type DependencyHealth = { name: string; status: OperationsHealth; required: boolean; latencyMs: number; code: DependencyHealthCode | null; checkedAt: string };
export type OperationsHealthDetail = { generatedAt: string; status: OperationsHealth; checks: DependencyHealth[] };
export type CacheRegion = { name: string; entries: number | null; estimatedMemoryBytes: number | null; hitCount: number | null; missCount: number | null; hitRatio: number | null };
export type ActionSuccess = { success: true; requestId: string; correlationId: string };
export type CacheKeyInvalidation = { region: string; key: string };
export type MaintenanceState = { enabled: boolean; message: string | null; updatedAt: string; updatedBy: string | null; requestId: string | null; correlationId: string | null };
export type MaintenanceUpdate = { enabled: boolean; message?: string | null };
export type OperationalJobStatus = 'queued' | 'running' | 'completed' | 'failed' | 'cancelled';
export type OperationalJob = { id: string; status: OperationalJobStatus; createdAt: string; startedAt: string | null; completedAt: string | null; durationMs: number | null; retryCount: number; lastError: string | null; executionNode: string | null; jobType: string };
export type OperationalJobs = { items: OperationalJob[]; total: number; limit: number; offset: number };
export type AuditResult = 'STARTED' | 'SUCCESS' | 'FAILURE';
export type AuditEntry = { id: string; timestamp: string; user: string; action: string; resource: string; result: AuditResult };
export type AuditDetail = AuditEntry & { actor: string; requestId: string; correlationId: string; durationMs: number; metadata: Record<string, unknown> };
export type AuditPage = { items: AuditEntry[]; total: number; limit: number; offset: number };
export type PageOptions = { limit?: number; offset?: number };
export type AuditOptions = PageOptions & { user?: string; action?: string; resource?: string; result?: AuditResult; dateFrom?: string; dateTo?: string };

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
  if (!isRecord(value) || !Array.isArray(value.items) || !Number.isInteger(value.total) || !Number.isInteger(value.limit) || !Number.isInteger(value.offset)) throw new AdminApiError('invalid_response');
  const total = Number(value.total), limit = Number(value.limit), offset = Number(value.offset);
  if (total < 0 || limit < 1 || limit > 100 || offset < 0 || value.items.length > limit || value.items.length > total || (value.items.length > 0 && (offset >= total || offset + value.items.length > total))) throw new AdminApiError('invalid_response');
  return { items: value.items.map(assistantFrom), total, limit, offset };
}
function jsonRequest(method: string, body: unknown, signal?: AbortSignal, headers: Record<string,string> = {}): RequestInit { return { method, headers: { 'Content-Type': 'application/json', ...headers }, body: JSON.stringify(body), signal }; }
function behaviourPath(assistantId: string) { return `/admin/assistants/${encodeURIComponent(assistantId)}/behaviour`; }
function knowledgePath(assistantId: string) { return `/admin/assistants/${encodeURIComponent(assistantId)}/knowledge-sources`; }
const awareTimestamp = /^\d{4}-\d{2}-\d{2}T.*(?:Z|[+-]\d{2}:\d{2})$/;
function validTimestamp(value: unknown): value is string { return timestamp(value) && awareTimestamp.test(value); }
function nullableTimestamp(value: unknown): value is string | null { return value === null || validTimestamp(value); }
function nullableString(value: unknown): value is string | null { return value === null || typeof value === 'string'; }
function nonNegativeInteger(value: unknown): value is number {
  return typeof value === 'number' && Number.isInteger(value) && value >= 0;
}
function exactCountSection(value: unknown, keys: string[]): value is Record<string, number> {
  return isRecord(value) && hasExactKeys(value, keys) && keys.every((key) => nonNegativeInteger(value[key]));
}
function operationsSummaryFrom(value: unknown): OperationsSummary {
  const topLevelKeys = ['generated_at','health','maintenance','cache','jobs','audit','assistants','knowledge_sources','ingestion'];
  if (!isRecord(value) || !hasExactKeys(value, topLevelKeys) || !validTimestamp(value.generated_at) ||
    !['healthy','degraded','unhealthy','unknown'].includes(String(value.health)) || typeof value.maintenance !== 'boolean' ||
    !exactCountSection(value.cache, ['regions']) || !exactCountSection(value.jobs, ['running','failed']) ||
    !exactCountSection(value.audit, ['today']) || !exactCountSection(value.assistants, ['total','published']) ||
    !isRecord(value.knowledge_sources) || !hasExactKeys(value.knowledge_sources, ['total','enabled','failed']) ||
    !nonNegativeInteger(value.knowledge_sources.total) || !nonNegativeInteger(value.knowledge_sources.enabled) ||
    !(value.knowledge_sources.failed === null || nonNegativeInteger(value.knowledge_sources.failed)) ||
    !isRecord(value.ingestion) || !hasExactKeys(value.ingestion, ['queued','running','recoverable','failed','oldest_queued_age_seconds','workers_observed']) ||
    !nonNegativeInteger(value.ingestion.queued) || !nonNegativeInteger(value.ingestion.running) ||
    !nonNegativeInteger(value.ingestion.recoverable) || !nonNegativeInteger(value.ingestion.failed) ||
    typeof value.ingestion.oldest_queued_age_seconds !== 'number' || !Number.isFinite(value.ingestion.oldest_queued_age_seconds) ||
    value.ingestion.oldest_queued_age_seconds < 0 || !nonNegativeInteger(value.ingestion.workers_observed)) {
    throw new AdminApiError('invalid_response');
  }
  return {
    generatedAt: value.generated_at,
    health: value.health as OperationsHealth,
    maintenance: value.maintenance,
    cache: { regions: value.cache.regions },
    jobs: { running: value.jobs.running, failed: value.jobs.failed },
    audit: { today: value.audit.today },
    assistants: { total: value.assistants.total, published: value.assistants.published },
    knowledgeSources: {
      total: value.knowledge_sources.total,
      enabled: value.knowledge_sources.enabled,
      failed: value.knowledge_sources.failed,
    },
    ingestion: {
      queued: value.ingestion.queued,
      running: value.ingestion.running,
      recoverable: value.ingestion.recoverable,
      failed: value.ingestion.failed,
      oldestQueuedAgeSeconds: value.ingestion.oldest_queued_age_seconds,
      workersObserved: value.ingestion.workers_observed,
    },
  };
}
const healthStates = ['healthy','degraded','unhealthy','unknown'] as const;
const healthCodes = ['dependency_timeout','dependency_unavailable','dependency_authentication_failed','dependency_misconfigured','dependency_check_failed'] as const;
const jobStatuses = ['queued','running','completed','failed','cancelled'] as const;
const auditResults = ['STARTED','SUCCESS','FAILURE'] as const;
function oneOf<T extends string>(value: unknown, values: readonly T[]): value is T { return typeof value === 'string' && values.includes(value as T); }
function nonNegativeNumber(value: unknown): value is number { return typeof value === 'number' && Number.isFinite(value) && value >= 0; }
function optionalNullableString(value: unknown): value is string | null { return value === undefined || nullableString(value); }
function pageParams(options: PageOptions): URLSearchParams { return new URLSearchParams({ limit: String(options.limit ?? 50), offset: String(options.offset ?? 0) }); }
function validPage(value: Record<string, unknown>): boolean {
  return nonNegativeInteger(value.total) && nonNegativeInteger(value.limit) && Number(value.limit) >= 1 && Number(value.limit) <= 200 && nonNegativeInteger(value.offset) &&
    Array.isArray(value.items) && value.items.length <= Number(value.limit) && value.items.length <= Number(value.total) &&
    (value.items.length === 0 || (Number(value.offset) < Number(value.total) && Number(value.offset) + value.items.length <= Number(value.total)));
}
function operationsRootFrom(value: unknown): OperationsRoot {
  const allowed:OperationsCapability[]=['health','cache','audit','maintenance','jobs','summary'];
  if (!isRecord(value) || !hasExactKeys(value,['generated_at','service','status','capabilities']) || !validTimestamp(value.generated_at) || value.service !== 'operations' || value.status !== 'available' || !Array.isArray(value.capabilities) || !value.capabilities.every((item) => oneOf(item,allowed)) || new Set(value.capabilities).size!==value.capabilities.length) throw new AdminApiError('invalid_response');
  return { generatedAt:value.generated_at, service:'operations', status:'available', capabilities:[...value.capabilities] as OperationsCapability[] };
}
function operationsHealthFrom(value: unknown): OperationsHealthDetail {
  if (!isRecord(value) || !hasExactKeys(value,['generated_at','status','checks']) || !validTimestamp(value.generated_at) || !oneOf(value.status,healthStates) || !Array.isArray(value.checks)) throw new AdminApiError('invalid_response');
  const checks=value.checks.map((item):DependencyHealth=>{
    if (!isRecord(item) || !hasExactKeys(item,['name','status','required','latency_ms','code','checked_at']) || typeof item.name !== 'string' || !/^[a-z0-9_-]{1,64}$/.test(item.name) || !oneOf(item.status,healthStates) || typeof item.required !== 'boolean' || !nonNegativeInteger(item.latency_ms) || !(item.code===null||oneOf(item.code,healthCodes)) || !validTimestamp(item.checked_at)) throw new AdminApiError('invalid_response');
    return {name:item.name,status:item.status,required:item.required,latencyMs:item.latency_ms,code:item.code,checkedAt:item.checked_at};
  });
  return {generatedAt:value.generated_at,status:value.status,checks};
}
function cacheRegionsFrom(value: unknown): CacheRegion[] {
  if (!isRecord(value) || !hasExactKeys(value,['items']) || !Array.isArray(value.items)) throw new AdminApiError('invalid_response');
  return value.items.map((item):CacheRegion=>{
    if (!isRecord(item) || !hasExactKeys(item,['name','entries','estimated_memory_bytes','hit_count','miss_count','hit_ratio']) || typeof item.name !== 'string' || !item.name || ![item.entries,item.estimated_memory_bytes,item.hit_count,item.miss_count].every((field)=>field===null||nonNegativeInteger(field)) || !(item.hit_ratio===null||(nonNegativeNumber(item.hit_ratio)&&item.hit_ratio<=1))) throw new AdminApiError('invalid_response');
    return {name:item.name,entries:item.entries as number|null,estimatedMemoryBytes:item.estimated_memory_bytes as number|null,hitCount:item.hit_count as number|null,missCount:item.miss_count as number|null,hitRatio:item.hit_ratio as number|null};
  });
}
function actionSuccessFrom(value: unknown): ActionSuccess {
  if (!isRecord(value)||!hasExactKeys(value,['success','request_id','correlation_id'])||value.success!==true||typeof value.request_id!=='string'||!value.request_id||typeof value.correlation_id!=='string'||!value.correlation_id) throw new AdminApiError('invalid_response');
  return {success:true,requestId:value.request_id,correlationId:value.correlation_id};
}
async function actionRequest(baseUrl:string,path:string,init:RequestInit):Promise<ActionSuccess>{const response=await request(baseUrl,path,init);if(!response.ok)return failure(response,'operations');return actionSuccessFrom(await successfulJson(response));}
function maintenanceFrom(value:unknown):MaintenanceState{
  if(!isRecord(value)||!hasExactKeys(value,['enabled','message','updated_at','updated_by','request_id','correlation_id'])||typeof value.enabled!=='boolean'||!nullableString(value.message)||!validTimestamp(value.updated_at)||!nullableString(value.updated_by)||!optionalNullableString(value.request_id)||!optionalNullableString(value.correlation_id))throw new AdminApiError('invalid_response');
  return {enabled:value.enabled,message:value.message,updatedAt:value.updated_at,updatedBy:value.updated_by,requestId:value.request_id??null,correlationId:value.correlation_id??null};
}
function operationalJobFrom(value:unknown):OperationalJob{
  if(!isRecord(value)||!hasExactKeys(value,['id','status','created_at','started_at','completed_at','duration_ms','retry_count','last_error','execution_node','job_type'])||!uuid.test(String(value.id))||!oneOf(value.status,jobStatuses)||!validTimestamp(value.created_at)||!nullableTimestamp(value.started_at)||!nullableTimestamp(value.completed_at)||!(value.duration_ms===null||nonNegativeInteger(value.duration_ms))||!nonNegativeInteger(value.retry_count)||!nullableString(value.last_error)||!nullableString(value.execution_node)||typeof value.job_type!=='string'||!value.job_type)throw new AdminApiError('invalid_response');
  return {id:String(value.id),status:value.status,createdAt:value.created_at,startedAt:value.started_at,completedAt:value.completed_at,durationMs:value.duration_ms as number|null,retryCount:value.retry_count,lastError:value.last_error,executionNode:value.execution_node,jobType:value.job_type};
}
function operationalJobsFrom(value:unknown):OperationalJobs{if(!isRecord(value)||!hasExactKeys(value,['items','total','limit','offset'])||!validPage(value))throw new AdminApiError('invalid_response');return {items:(value.items as unknown[]).map(operationalJobFrom),total:value.total as number,limit:value.limit as number,offset:value.offset as number};}
function auditEntryFrom(value:unknown):AuditEntry{if(!isRecord(value)||!hasExactKeys(value,['id','timestamp','user','action','resource','result'])||!uuid.test(String(value.id))||!validTimestamp(value.timestamp)||typeof value.user!=='string'||typeof value.action!=='string'||typeof value.resource!=='string'||!oneOf(value.result,auditResults))throw new AdminApiError('invalid_response');return{id:String(value.id),timestamp:value.timestamp,user:value.user,action:value.action,resource:value.resource,result:value.result};}
function auditPageFrom(value:unknown):AuditPage{if(!isRecord(value)||!hasExactKeys(value,['items','total','limit','offset'])||!validPage(value))throw new AdminApiError('invalid_response');return{items:(value.items as unknown[]).map(auditEntryFrom),total:value.total as number,limit:value.limit as number,offset:value.offset as number};}
function auditDetailFrom(value:unknown):AuditDetail{if(!isRecord(value)||!hasExactKeys(value,['id','timestamp','user','action','resource','result','actor','request_id','correlation_id','duration_ms','metadata'])||typeof value.actor!=='string'||typeof value.request_id!=='string'||!value.request_id||typeof value.correlation_id!=='string'||!value.correlation_id||!nonNegativeInteger(value.duration_ms)||!isRecord(value.metadata))throw new AdminApiError('invalid_response');const item=auditEntryFrom({id:value.id,timestamp:value.timestamp,user:value.user,action:value.action,resource:value.resource,result:value.result});return{...item,actor:value.actor,requestId:value.request_id,correlationId:value.correlation_id,durationMs:value.duration_ms,metadata:value.metadata};}
function knowledgeJobFrom(value: unknown): KnowledgeSourceJob | null {
  if (value === null) return null;
  if (!isRecord(value) || !hasExactKeys(value, ['id','status','current_step','created_at','started_at','completed_at','failure_code','failure_message']) ||
    !uuid.test(String(value.id)) || !['queued','pending','running','completed','failed','cancelled'].includes(String(value.status)) ||
    !(value.current_step === null || ['parse','chunk','embed','persist'].includes(String(value.current_step))) ||
    !validTimestamp(value.created_at) || !nullableTimestamp(value.started_at) || !nullableTimestamp(value.completed_at) ||
    !nullableString(value.failure_code) || !nullableString(value.failure_message)) throw new AdminApiError('invalid_response');
  return { id:String(value.id), status:value.status as IngestionStatus, currentStep:value.current_step as IngestionStep|null,
    createdAt:value.created_at, startedAt:value.started_at, completedAt:value.completed_at,
    failureCode:value.failure_code, failureMessage:value.failure_message };
}
function knowledgeSourceFrom(value: unknown, assistantId: string, detail: boolean): KnowledgeSource {
  if (!isRecord(value) || !hasExactKeys(value, ['id','assistant_id','source_type','name','retrieval_state','url','direct_text','document_id','created_at','updated_at','latest_ingestion','active_job_reused']) ||
    !uuid.test(String(value.id)) || value.assistant_id !== assistantId || !['direct_text','url'].includes(String(value.source_type)) ||
    typeof value.name !== 'string' || !value.name.trim() || value.name.length > 255 || !['enabled','disabled'].includes(String(value.retrieval_state)) ||
    typeof value.document_id !== 'string' || !value.document_id.trim() || !validTimestamp(value.created_at) || !validTimestamp(value.updated_at) ||
    typeof value.active_job_reused !== 'boolean') throw new AdminApiError('invalid_response');
  if (value.source_type === 'url') {
    if (typeof value.url !== 'string' || !isHttpUrl(value.url) || value.direct_text !== null) throw new AdminApiError('invalid_response');
  } else if (value.url !== null || (!detail ? value.direct_text !== null : !(typeof value.direct_text === 'string' && Boolean(value.direct_text.trim()) && value.direct_text.length <= 100000))) {
    throw new AdminApiError('invalid_response');
  }
  return { id:String(value.id), assistantId, sourceType:value.source_type as KnowledgeSourceType, name:value.name.trim(),
    retrievalState:value.retrieval_state as RetrievalState, url:value.url as string|null, directText:value.direct_text as string|null,
    documentId:value.document_id, createdAt:value.created_at, updatedAt:value.updated_at,
    latestIngestion:knowledgeJobFrom(value.latest_ingestion), activeJobReused:value.active_job_reused };
}
function knowledgeSourceListFrom(value: unknown, assistantId: string): KnowledgeSourceList {
  if (!isRecord(value) || !hasExactKeys(value,['items','total','limit','offset']) || !Array.isArray(value.items) ||
    !Number.isInteger(value.total) || !Number.isInteger(value.limit) || !Number.isInteger(value.offset)) throw new AdminApiError('invalid_response');
  const total=Number(value.total),limit=Number(value.limit),offset=Number(value.offset);
  if(total<0||limit<1||limit>100||offset<0||value.items.length>limit||value.items.length>total||(value.items.length>0&&(offset>=total||offset+value.items.length>total))) throw new AdminApiError('invalid_response');
  return {items:value.items.map(item=>knowledgeSourceFrom(item,assistantId,false)),total,limit,offset};
}
function isHttpUrl(value: string) { try { const url=new URL(value); return (url.protocol==='http:'||url.protocol==='https:')&&!url.username&&!url.password&&!url.hash; } catch { return false; } }

function safeMultiline(value: unknown, maximum: number, required: boolean): value is string {
  if (typeof value !== 'string' || value.length > maximum || (required && !value.trim())) return false;
  return ![...value].some((character) =>
    /[\p{Cc}\p{Cf}\p{Cs}]/u.test(character) && character !== '\n' && character !== '\t');
}
function safeSingleLine(value: unknown, maximum: number, required: boolean): value is string {
  return safeMultiline(value, maximum, required) && !value.includes('\n') && !value.includes('\r') && !value.includes('\t');
}
function behaviourDraftFrom(value: unknown): AssistantBehaviourDraft {
  if (!isRecord(value) || !hasExactKeys(value, ['revision','instructions','welcome_message','input_placeholder','suggested_questions','created_at']) ||
    !Number.isInteger(value.revision) || Number(value.revision) < 1 ||
    !safeMultiline(value.instructions, 12000, true) || !safeMultiline(value.welcome_message, 1000, false) ||
    !safeSingleLine(value.input_placeholder, 160, true) || !Array.isArray(value.suggested_questions) ||
    value.suggested_questions.length > 8 || !value.suggested_questions.every((question) => safeSingleLine(question, 240, true)) ||
    !validTimestamp(value.created_at)) throw new AdminApiError('invalid_response');
  return {
    revision: Number(value.revision), instructions: value.instructions, welcomeMessage: value.welcome_message,
    inputPlaceholder: value.input_placeholder, suggestedQuestions: [...value.suggested_questions] as string[], createdAt: value.created_at,
  };
}
function assistantBehaviourFrom(value: unknown, assistantId: string): AssistantBehaviour {
  if (!isRecord(value) || !hasExactKeys(value, ['assistant_id','draft','published','has_unpublished_changes','concurrency_token']) ||
    value.assistant_id !== assistantId || typeof value.has_unpublished_changes !== 'boolean' ||
    typeof value.concurrency_token !== 'string' || !value.concurrency_token || value.concurrency_token.length > 100) {
    throw new AdminApiError('invalid_response');
  }
  const draft = behaviourDraftFrom(value.draft);
  let published: AssistantBehaviourPublished | null = null;
  if (value.published !== null) {
    if (!isRecord(value.published) || !hasExactKeys(value.published, ['revision','published_at']) ||
      !Number.isInteger(value.published.revision) || Number(value.published.revision) < 1 ||
      Number(value.published.revision) > draft.revision || !validTimestamp(value.published.published_at)) {
      throw new AdminApiError('invalid_response');
    }
    published = { revision: Number(value.published.revision), publishedAt: value.published.published_at };
  }
  const expectedUnpublished = published === null || published.revision !== draft.revision;
  if (value.has_unpublished_changes !== expectedUnpublished) throw new AdminApiError('invalid_response');
  return { assistantId, draft, published, hasUnpublishedChanges: value.has_unpublished_changes, concurrencyToken: value.concurrency_token };
}
export interface AdminApi {
  login(email: string, password: string, signal?: AbortSignal): Promise<Administrator>;
  currentUser(signal?: AbortSignal): Promise<Administrator>;
  logout(signal?: AbortSignal): Promise<void>;
  getOperationsSummary(signal?: AbortSignal): Promise<OperationsSummary>;
  getOperations(signal?: AbortSignal): Promise<OperationsRoot>;
  getOperationsHealth(signal?: AbortSignal): Promise<OperationsHealthDetail>;
  listCacheRegions(signal?: AbortSignal): Promise<CacheRegion[]>;
  clearCache(signal?: AbortSignal): Promise<ActionSuccess>;
  clearCacheRegion(region: string, signal?: AbortSignal): Promise<ActionSuccess>;
  invalidateCacheKey(input: CacheKeyInvalidation, signal?: AbortSignal): Promise<ActionSuccess>;
  getMaintenance(signal?: AbortSignal): Promise<MaintenanceState>;
  updateMaintenance(input: MaintenanceUpdate, signal?: AbortSignal): Promise<MaintenanceState>;
  listOperationalJobs(options?: PageOptions & { status?: OperationalJobStatus }, signal?: AbortSignal): Promise<OperationalJobs>;
  getOperationalJob(id: string, signal?: AbortSignal): Promise<OperationalJob>;
  listAuditEntries(options?: AuditOptions, signal?: AbortSignal): Promise<AuditPage>;
  getAuditEntry(id: string, signal?: AbortSignal): Promise<AuditDetail>;
  listAssistants(options?: { limit?: number; offset?: number; status?: AssistantStatus; visibility?: AssistantVisibility }, signal?: AbortSignal): Promise<AssistantList>;
  getAssistant(id: string, signal?: AbortSignal): Promise<AssistantDetail>;
  createAssistant(input: CreateAssistant, signal?: AbortSignal): Promise<Assistant>;
  updateAssistant(id: string, input: UpdateAssistant, signal?: AbortSignal): Promise<Assistant>;
  deleteAssistant(id: string, signal?: AbortSignal): Promise<void>;
  getAssistantBehaviour(id: string, signal?: AbortSignal): Promise<AssistantBehaviour>;
  updateAssistantBehaviour(id: string, input: UpdateAssistantBehaviour, signal?: AbortSignal): Promise<AssistantBehaviour>;
  publishAssistantBehaviour(id: string, input: PublishAssistantBehaviour, signal?: AbortSignal): Promise<AssistantBehaviour>;
  previewAssistantMessage(id: string, input: AssistantPreviewMessage, options?: AssistantPreviewStreamOptions): Promise<{ answer: string }>;
  listKnowledgeSources(assistantId: string, options?: { limit?: number; offset?: number }, signal?: AbortSignal): Promise<KnowledgeSourceList>;
  getKnowledgeSource(assistantId: string, sourceId: string, signal?: AbortSignal): Promise<KnowledgeSource>;
  createKnowledgeSource(assistantId: string, input: CreateKnowledgeSource, idempotencyKey: string, signal?: AbortSignal): Promise<KnowledgeSource>;
  updateKnowledgeSourceRetrieval(assistantId: string, sourceId: string, retrievalState: RetrievalState, signal?: AbortSignal): Promise<KnowledgeSource>;
  reingestKnowledgeSource(assistantId: string, sourceId: string, idempotencyKey: string, signal?: AbortSignal): Promise<KnowledgeSource>;
  deleteKnowledgeSource(assistantId: string, sourceId: string, signal?: AbortSignal): Promise<void>;
}
