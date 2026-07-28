import type { AssistantConfig } from '../types/config'

export const assistantConfig: AssistantConfig = {
  enabled: false,
  apiBaseUrl: import.meta.env.VITE_ASSISTANT_API_BASE_URL?.trim() ?? '',
}
