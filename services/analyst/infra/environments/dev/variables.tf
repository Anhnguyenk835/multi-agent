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
  description = "Full image reference for the analyst container, e.g. REGION-docker.pkg.dev/PROJECT/analyst/analyst:TAG."
}
