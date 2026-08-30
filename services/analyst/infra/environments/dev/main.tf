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
  account_id   = "analyst-runtime"
  display_name = "Analyst Cloud Run runtime identity"
}

module "artifact_registry" {
  source        = "../../modules/artifact_registry"
  project_id    = var.project_id
  region        = var.region
  repository_id = "analyst"
}

module "secrets" {
  source                         = "../../modules/secrets"
  project_id                     = var.project_id
  name_prefix                    = "analyst-"
  secret_names                   = ["OPENAI_API_KEY", "LANGSMITH_API_KEY"]
  accessor_service_account_email = google_service_account.runtime.email
}

module "cloud_run" {
  source                = "../../modules/cloud_run_service"
  project_id            = var.project_id
  region                = var.region
  service_name          = "analyst"
  image                 = var.image
  container_port        = 8002
  service_account_email = google_service_account.runtime.email
  startup_probe_path    = "/ready"

  env_vars = {
    AI_MODE                = "live"
    OPENAI_MODEL           = "gpt-4o-mini"
    LLM_TIMEOUT_SECONDS    = "30"
    DEMO_FAILURE_MODE      = "none"
    LANGSMITH_TRACING      = "true"
    LANGSMITH_PROJECT      = "distributed-agents-demo"
    LANGSMITH_HIDE_INPUTS  = "false"
    LANGSMITH_HIDE_OUTPUTS = "false"
  }

  secret_env_vars = {
    OPENAI_API_KEY    = module.secrets.secret_ids["OPENAI_API_KEY"]
    LANGSMITH_API_KEY = module.secrets.secret_ids["LANGSMITH_API_KEY"]
  }
}
