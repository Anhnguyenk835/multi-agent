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
  account_id   = "orchestrator-runtime"
  display_name = "Orchestrator Cloud Run runtime identity"
}

module "artifact_registry" {
  source        = "../../modules/artifact_registry"
  project_id    = var.project_id
  region        = var.region
  repository_id = "orchestrator"
}

module "cloud_sql" {
  source        = "../../modules/cloud_sql"
  project_id    = var.project_id
  region        = var.region
  instance_name = "orchestrator-db"
}

# Cloud Run's built-in Cloud SQL connector (the unix socket at
# /cloudsql/<connection_name>) needs this to authenticate — without it the
# socket never comes up and the app's DB connection fails at startup.
resource "google_project_iam_member" "cloudsql_client" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.runtime.email}"
}

# The other services' API keys are human-seeded secrets (empty containers
# created by Terraform). This one Terraform can populate itself, since it
# already generated the DB password inside module.cloud_sql.
resource "google_secret_manager_secret" "checkpoint_database_url" {
  project   = var.project_id
  secret_id = "orchestrator-CHECKPOINT_DATABASE_URL"

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "checkpoint_database_url" {
  secret      = google_secret_manager_secret.checkpoint_database_url.id
  secret_data = module.cloud_sql.database_url
}

resource "google_secret_manager_secret_iam_member" "checkpoint_database_url_accessor" {
  project   = var.project_id
  secret_id = google_secret_manager_secret.checkpoint_database_url.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.runtime.email}"
}

module "secrets" {
  source                         = "../../modules/secrets"
  project_id                     = var.project_id
  name_prefix                    = "orchestrator-"
  secret_names                   = ["LANGSMITH_API_KEY"]
  accessor_service_account_email = google_service_account.runtime.email
}

locals {
  # Cloud Run always terminates TLS at its ingress, so the gRPC address the
  # orchestrator dials must drop the https:// scheme and use the TLS port.
  market_agent_address = "${replace(var.market_agent_url, "https://", "")}:443"
}

module "cloud_run" {
  source                            = "../../modules/cloud_run_service"
  project_id                        = var.project_id
  region                            = var.region
  service_name                      = "orchestrator"
  image                             = var.image
  container_port                    = 8000
  service_account_email             = google_service_account.runtime.email
  startup_probe_path                = "/ready"
  cloudsql_instance_connection_name = module.cloud_sql.connection_name
  # The public-facing entry point — the frontend calls this URL directly.
  allow_public_access = true

  env_vars = {
    RESEARCHER_URL               = var.researcher_url
    MARKET_AGENT_ADDRESS         = local.market_agent_address
    MARKET_AGENT_USE_TLS         = "true"
    ANALYST_URL                  = var.analyst_url
    WRITER_URL                   = var.writer_url
    ORCHESTRATOR_ALLOWED_ORIGINS = var.allowed_origins
    LANGSMITH_TRACING            = "true"
    LANGSMITH_PROJECT            = "distributed-agents-demo"
    LANGSMITH_HIDE_INPUTS        = "false"
    LANGSMITH_HIDE_OUTPUTS       = "false"
  }

  secret_env_vars = {
    CHECKPOINT_DATABASE_URL = google_secret_manager_secret.checkpoint_database_url.secret_id
    LANGSMITH_API_KEY       = module.secrets.secret_ids["LANGSMITH_API_KEY"]
  }
}
