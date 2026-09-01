variable "project_id" {
  type = string
}

variable "region" {
  type = string
}

variable "service_name" {
  type = string
}

variable "image" {
  type        = string
  description = "Full image reference, e.g. REGION-docker.pkg.dev/PROJECT/REPO/IMAGE:TAG."
}

variable "container_port" {
  type = number
}

variable "service_account_email" {
  type = string
}

variable "env_vars" {
  type    = map(string)
  default = {}
}

variable "secret_env_vars" {
  type        = map(string)
  description = "Env var name -> Secret Manager secret ID. Mounted as the secret's latest version."
  default     = {}
}

variable "cpu" {
  type    = string
  default = "1"
}

variable "memory" {
  type    = string
  default = "512Mi"
}

variable "min_instances" {
  type    = number
  default = 0
}

variable "max_instances" {
  type    = number
  default = 2
}

variable "allow_public_access" {
  type        = bool
  default     = true
  description = "Demo simplification: no per-caller IAM, every service is reachable directly."
}

variable "ingress" {
  type        = string
  default     = "INGRESS_TRAFFIC_ALL"
  description = "Cloud Run ingress policy, for example INGRESS_TRAFFIC_INTERNAL_ONLY."
}

variable "startup_probe_path" {
  type        = string
  default     = null
  description = "HTTP path for the startup probe. Leave null for gRPC services (falls back to a TCP probe)."
}

variable "use_http2" {
  type        = bool
  default     = false
  description = "Serve HTTP/2 (h2c) to the container. Required for gRPC services."
}

variable "cloudsql_instance_connection_name" {
  type    = string
  default = null
}
