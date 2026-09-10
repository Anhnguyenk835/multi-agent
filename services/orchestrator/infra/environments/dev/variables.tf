variable "project_id" {
  type        = string
  description = "GCP project ID for the development environment."
}

variable "region" {
  type        = string
  description = "GCP region for regional resources."
  default     = "asia-southeast1"
}

variable "image" {
  type        = string
  description = "Full image reference for the orchestrator container, e.g. REGION-docker.pkg.dev/PROJECT/orchestrator/orchestrator:TAG."
}

variable "market_analyst_url" {
  type        = string
  description = "Cloud Run URL of the deployed Market Analyst service (output of its own `terraform apply`)."
}

variable "competitor_analyst_url" {
  type        = string
  description = "Cloud Run URL of the deployed Competitor Analyst service (output of its own `terraform apply`). The https:// scheme is stripped and :443 appended to form the gRPC-over-TLS address."
}

variable "analyst_url" {
  type        = string
  description = "Cloud Run URL of the deployed analyst service (output of its own `terraform apply`)."
}

variable "writer_url" {
  type        = string
  description = "Cloud Run URL of the deployed writer service (output of its own `terraform apply`)."
}

variable "allowed_origins" {
  type        = string
  description = "Comma-separated CORS origins allowed to call the orchestrator (e.g. the frontend's deployed URL)."
  default     = "*"
}
