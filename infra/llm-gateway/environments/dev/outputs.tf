output "gateway_url" {
  value       = module.cloud_run.url
  description = "Internal Cloud Run URL. Append /v1 for agent LLM_GATEWAY_BASE_URL."
}

output "artifact_registry_repository" {
  value = module.artifact_registry.repository_url
}
