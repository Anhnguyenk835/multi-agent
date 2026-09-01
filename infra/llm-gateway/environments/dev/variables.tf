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
  description = "Full image reference for the pinned LiteLLM gateway image."
}
