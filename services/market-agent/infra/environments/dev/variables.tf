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
  description = "Full image reference for the market-agent container, e.g. REGION-docker.pkg.dev/PROJECT/market-agent/market-agent:TAG."
}

variable "llm_gateway_base_url" {
  type        = string
  description = "Private LiteLLM Proxy OpenAI-compatible base URL, including /v1."
}
