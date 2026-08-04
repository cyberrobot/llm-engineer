export type Administrator = { id: string; email: string; role: 'administrator' };
export type AdminApiErrorKind = 'unauthenticated'|'invalid_credentials'|'throttled'|'invalid_request'|'forbidden'|'network'|'server'|'invalid_response';
export class AdminApiError extends Error { readonly kind: AdminApiErrorKind; constructor(kind: AdminApiErrorKind) { super('The administrator request could not be completed.'); this.name='AdminApiError'; this.kind=kind; } }

function userFrom(value: unknown): Administrator {
  if (!value || typeof value !== 'object' || !('user' in value)) throw new AdminApiError('invalid_response');
  const user = value.user;
  if (!user || typeof user !== 'object' || !('id' in user) || typeof user.id !== 'string' || !('email' in user) || typeof user.email !== 'string' || !('role' in user) || user.role !== 'administrator') throw new AdminApiError('invalid_response');
  return { id: user.id, email: user.email, role: user.role };
}

async function request(baseUrl: string, path: string, init: RequestInit): Promise<Response> {
  try { return await fetch(`${baseUrl}${path}`, { ...init, credentials: 'include', headers: { Accept: 'application/json', ...init.headers } }); }
  catch (error) { if (error instanceof DOMException && error.name === 'AbortError') throw error; throw new AdminApiError('network'); }
}

async function failure(response: Response, context: 'login'|'session'|'logout'): Promise<never> {
  let code: unknown;
  try { const body: unknown = await response.json(); code = body && typeof body === 'object' && 'detail' in body && body.detail && typeof body.detail === 'object' && 'code' in body.detail ? body.detail.code : undefined; } catch { /* deliberately discard raw bodies */ }
  if (response.status === 401) throw new AdminApiError(context === 'login' && code === 'invalid_credentials' ? 'invalid_credentials' : 'unauthenticated');
  if (response.status === 429 && code === 'too_many_login_attempts') throw new AdminApiError('throttled');
  if (response.status === 400) throw new AdminApiError('invalid_request');
  if (response.status === 403) throw new AdminApiError('forbidden');
  throw new AdminApiError(response.status >= 500 ? 'server' : 'invalid_response');
}

export function createAdminApi(baseUrl: string) {
  return {
    async login(email: string, password: string, signal?: AbortSignal) { const response=await request(baseUrl,'/admin/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email,password}),signal}); if(!response.ok) return failure(response,'login'); return userFrom(await response.json()); },
    async currentUser(signal?: AbortSignal) { const response=await request(baseUrl,'/admin/auth/me',{method:'GET',signal}); if(!response.ok) return failure(response,'session'); return userFrom(await response.json()); },
    async logout(signal?: AbortSignal) { const response=await request(baseUrl,'/admin/auth/logout',{method:'POST',signal}); if(!response.ok) return failure(response,'logout'); if(response.status !== 204) throw new AdminApiError('invalid_response'); },
  };
}
export type AdminApi = ReturnType<typeof createAdminApi>;
