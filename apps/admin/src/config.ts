export const ADMIN_API_VARIABLE = 'VITE_ADMIN_API_BASE_URL' as const;
type Environment = { readonly VITE_ADMIN_API_BASE_URL?: string };
export type AdminConfigResult = { ok: true; apiBaseUrl: string } | { ok: false; variable: typeof ADMIN_API_VARIABLE; reason: 'missing' | 'invalid' };

export function readAdminConfig(environment: Environment = import.meta.env as Environment): AdminConfigResult {
  const raw = environment.VITE_ADMIN_API_BASE_URL?.trim() ?? '';
  if (!raw) return { ok: false, variable: ADMIN_API_VARIABLE, reason: 'missing' };
  try {
    const url = new URL(raw);
    if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.hash || url.search) throw new Error();
    return { ok: true, apiBaseUrl: url.toString().replace(/\/+$/, '') };
  } catch {
    return { ok: false, variable: ADMIN_API_VARIABLE, reason: 'invalid' };
  }
}
