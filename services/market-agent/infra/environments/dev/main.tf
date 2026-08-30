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
  account_id   = "market-agent-runtime"
  display_name = "Market Agent Cloud Run runtime identity"
}

module "artifact_registry" {
  source        = "../../modules/artifact_registry"
  project_id    = var.project_id
  region        = var.region
  repository_id = "market-agent"
}

module "secrets" {
  source                         = "../../modules/secrets"
  project_id                     = var.project_id
  name_prefix                    = "market-agent-"
  secret_names                   = ["OPENAI_API_KEY", "EXA_API_KEY", "LANGSMITH_API_KEY"]
  accessor_service_account_email = google_service_account.runtime.email
}

module "cloud_run" {
  source                = "../../modules/cloud_run_service"
  project_id            = var.project_id
  region                = var.region
  service_name          = "market-agent"
  image                 = var.image
  container_port        = 50051
  service_account_email = google_service_account.runtime.email

  # gRPC: needs end-to-end HTTP/2, and there is no HTTP path to probe, so
  # the module falls back to Cloud Run's default TCP probe.
  use_http2          = true
  startup_probe_path = null

  env_vars = {
    AI_MODE                    = "live"
    OPENAI_MODEL               = "gpt-4o-mini"
    LLM_TIMEOUT_SECONDS        = "60"
    EXA_MAX_RESULTS            = "8"
    EXA_CONTENT_MAX_CHARACTERS = "4000"
    DEMO_FAILURE_MODE          = "none"
    LANGSMITH_TRACING          = "true"
    LANGSMITH_PROJECT          = "distributed-agents-demo"
    LANGSMITH_HIDE_INPUTS      = "false"
    LANGSMITH_HIDE_OUTPUTS     = "false"
  }

  secret_env_vars = {
    OPENAI_API_KEY    = module.secrets.secret_ids["OPENAI_API_KEY"]
    EXA_API_KEY       = module.secrets.secret_ids["EXA_API_KEY"]
    LANGSMITH_API_KEY = module.secrets.secret_ids["LANGSMITH_API_KEY"]
  }
}
