output "url" {
  value = module.cloud_run.url
}

output "artifact_registry_repository" {
  value = module.artifact_registry.repository_url
}
