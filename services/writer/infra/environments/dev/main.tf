terraform {
  required_version = ">= 1.9.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

resource "google_service_account" "runtime" {
  project      = var.project_id
  account_id   = "writer-runtime"
  display_name = "Writer Cloud Run runtime identity"
}

module "artifact_registry" {
  source        = "../../modules/artifact_registry"
  project_id    = var.project_id
  region        = var.region
  repository_id = "writer"
}

module "secrets" {
  source                         = "../../modules/secrets"
  project_id                     = var.project_id
  name_prefix                    = "writer-"
  secret_names                   = ["LLM_GATEWAY_API_KEY"]
  accessor_service_account_email = google_service_account.runtime.email
}

module "cloud_run" {
  source                = "../../modules/cloud_run_service"
  project_id            = var.project_id
  region                = var.region
  service_name          = "writer"
  image                 = var.image
  container_port        = 8003
  service_account_email = google_service_account.runtime.email
  startup_probe_path    = "/ready"

  env_vars = {
    AI_MODE               = "live"
    LLM_GATEWAY_BASE_URL  = var.llm_gateway_base_url
    LLM_MODEL_ROUTE       = "brief-streaming"
    LLM_TIMEOUT_SECONDS   = "30"
    LLM_MAX_OUTPUT_TOKENS = "3000"
    DEMO_FAILURE_MODE     = "none"
  }

  secret_env_vars = {
    LLM_GATEWAY_API_KEY = module.secrets.secret_ids["LLM_GATEWAY_API_KEY"]
  }
}
