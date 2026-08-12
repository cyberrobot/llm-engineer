interface ImportMetaEnv {
  readonly VITE_ASSISTANT_API_BASE_URL?: string
  readonly VITE_ASSISTANT_ID?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
