variable "project_id" {
  type        = string
  description = "GCP project ID for the gateway environment."
}

variable "region" {
  type        = string
  description = "GCP region for gateway resources."
  default     = "asia-southeast1"
}

variable "image" {
  type        = string
  description = "Pinned official LiteLLM database image run directly by Cloud Run."
  default     = "ghcr.io/berriai/litellm-database:v1.98.0"
}
