variable "project_id" {
  type = string
}

variable "secret_names" {
  type        = list(string)
  description = "Logical secret names (usually the env var name). Values are seeded manually after apply — never from Terraform."
}

variable "name_prefix" {
  type        = string
  description = "Prefixed onto each secret ID. Secret Manager IDs are unique per project, preventing collisions such as LLM_GATEWAY_API_KEY."
}

variable "accessor_service_account_email" {
  type = string
}
