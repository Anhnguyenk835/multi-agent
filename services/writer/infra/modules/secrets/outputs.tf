# Keyed by the logical name (without prefix) so call sites stay readable:
# module.secrets.secret_ids["LLM_GATEWAY_API_KEY"] -> "writer-LLM_GATEWAY_API_KEY".
output "secret_ids" {
  value = { for name, secret in google_secret_manager_secret.this : name => secret.secret_id }
}
