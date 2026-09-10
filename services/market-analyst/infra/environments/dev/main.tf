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
  account_id   = "market-analyst-runtime"
  display_name = "Market Analyst Cloud Run runtime identity"
}

module "artifact_registry" {
  source        = "../../modules/artifact_registry"
  project_id    = var.project_id
  region        = var.region
  repository_id = "market-analyst"
}

module "secrets" {
  source                         = "../../modules/secrets"
  project_id                     = var.project_id
  name_prefix                    = "market-analyst-"
  secret_names                   = ["LLM_GATEWAY_API_KEY", "EXA_API_KEY"]
  accessor_service_account_email = google_service_account.runtime.email
}

module "cloud_run" {
  source                = "../../modules/cloud_run_service"
  project_id            = var.project_id
  region                = var.region
  service_name          = "market-analyst"
  image                 = var.image
  container_port        = 8001
  service_account_email = google_service_account.runtime.email
  # LangGraph Server's own health endpoint, not the FastAPI /ready convention
  # the other three HTTP services use.
  startup_probe_path = "/ok"

  env_vars = {
    LLM_GATEWAY_BASE_URL       = var.llm_gateway_base_url
    LLM_MODEL_ROUTE            = "research-fast"
    LLM_TIMEOUT_SECONDS        = "60"
    LLM_MAX_OUTPUT_TOKENS      = "2000"
    EXA_MAX_RESULTS            = "8"
    EXA_CONTENT_MAX_CHARACTERS = "4000"
  }

  secret_env_vars = {
    LLM_GATEWAY_API_KEY = module.secrets.secret_ids["LLM_GATEWAY_API_KEY"]
    EXA_API_KEY         = module.secrets.secret_ids["EXA_API_KEY"]
  }
}
