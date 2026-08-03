export interface AssistantWidgetDemoConfig {
  apiBaseUrl: string
  assistantId: string
}

interface AssistantWidgetDemoEnvironment {
  readonly VITE_ASSISTANT_API_BASE_URL?: string
  readonly VITE_ASSISTANT_ID?: string
}

type ConfigurationVariable = 'VITE_ASSISTANT_API_BASE_URL' | 'VITE_ASSISTANT_ID'

export type AssistantWidgetDemoConfigResult =
  | { ok: true; config: AssistantWidgetDemoConfig }
  | { ok: false; variables: readonly ConfigurationVariable[]; reason: 'missing' | 'invalid' }

function normalizeApiBaseUrl(value: string): string | undefined {
  try {
    const url = new URL(value)
    if (!['http:', 'https:'].includes(url.protocol)) return undefined
    if (url.username || url.password || url.search || url.hash) return undefined
    return url.toString().replace(/\/+$/, '')
  } catch {
    return undefined
  }
}

export function readAssistantWidgetDemoConfig(
  environment: AssistantWidgetDemoEnvironment = import.meta.env,
): AssistantWidgetDemoConfigResult {
  const rawApiBaseUrl = environment.VITE_ASSISTANT_API_BASE_URL?.trim() ?? ''
  const assistantId = environment.VITE_ASSISTANT_ID?.trim() ?? ''
  const missing: ConfigurationVariable[] = []

  if (!rawApiBaseUrl) missing.push('VITE_ASSISTANT_API_BASE_URL')
  if (!assistantId) missing.push('VITE_ASSISTANT_ID')
  if (missing.length > 0) return { ok: false, variables: missing, reason: 'missing' }

  const apiBaseUrl = normalizeApiBaseUrl(rawApiBaseUrl)
  const invalid: ConfigurationVariable[] = []
  if (!apiBaseUrl) invalid.push('VITE_ASSISTANT_API_BASE_URL')
  if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(assistantId)) invalid.push('VITE_ASSISTANT_ID')
  if (invalid.length > 0 || !apiBaseUrl) {
    return { ok: false, variables: invalid, reason: 'invalid' }
  }

  return { ok: true, config: { apiBaseUrl, assistantId } }
}
