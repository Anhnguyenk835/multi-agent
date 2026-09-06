const trimTrailingSlash = (value: string) => value.replace(/\/$/, '')

export const env = Object.freeze({
  orchestratorBaseUrl: trimTrailingSlash(import.meta.env.VITE_ORCHESTRATOR_BASE_URL || '/api'),
})
