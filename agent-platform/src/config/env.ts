const trimTrailingSlash = (value: string) => value.replace(/\/$/, '')

export const env = Object.freeze({
  orchestratorBaseUrl: trimTrailingSlash(import.meta.env.VITE_ORCHESTRATOR_BASE_URL || '/api'),
  backendBaseUrl: trimTrailingSlash(import.meta.env.VITE_BACKEND_BASE_URL || '/backend-api'),
})
