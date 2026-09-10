interface ImportMetaEnv {
  readonly VITE_ORCHESTRATOR_BASE_URL?: string
  readonly VITE_BACKEND_BASE_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
