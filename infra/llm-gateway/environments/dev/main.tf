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
  account_id   = "llm-gateway-runtime"
  display_name = "LiteLLM gateway Cloud Run runtime identity"
}

module "cloud_sql" {
  source        = "../../../../services/orchestrator/infra/modules/cloud_sql"
  project_id    = var.project_id
  region        = var.region
  instance_name = "llm-gateway-db"
  database_name = "litellm"
  database_user = "litellm"
}

resource "google_project_iam_member" "cloudsql_client" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.runtime.email}"
}

module "secrets" {
  source                         = "../../../../services/researcher/infra/modules/secrets"
  project_id                     = var.project_id
  name_prefix                    = "llm-gateway-"
  secret_names                   = ["OPENAI_API_KEY", "GEMINI_API_KEY", "ANTHROPIC_API_KEY", "LITELLM_MASTER_KEY", "LITELLM_SALT_KEY"]
  accessor_service_account_email = google_service_account.runtime.email
}

# Terraform creates this secret itself because it already owns the generated
# Cloud SQL password. Provider credentials and the master key remain external
# inputs and are never stored in Terraform state.
resource "google_secret_manager_secret" "database_url" {
  project   = var.project_id
  secret_id = "llm-gateway-DATABASE_URL"

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "database_url" {
  secret      = google_secret_manager_secret.database_url.id
  secret_data = module.cloud_sql.database_url
}

resource "google_secret_manager_secret_iam_member" "database_url_accessor" {
  project   = var.project_id
  secret_id = google_secret_manager_secret.database_url.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.runtime.email}"
}

# The configuration contains model aliases and policy, but no provider
# credentials. A secret volume lets Cloud Run use the official image directly.
resource "google_secret_manager_secret" "config" {
  project   = var.project_id
  secret_id = "llm-gateway-CONFIG"

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "config" {
  secret      = google_secret_manager_secret.config.id
  secret_data = file("${path.module}/../../config.yaml")
}

resource "google_secret_manager_secret_iam_member" "config_accessor" {
  project   = var.project_id
  secret_id = google_secret_manager_secret.config.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.runtime.email}"
}

module "cloud_run" {
  source                            = "../../../../services/researcher/infra/modules/cloud_run_service"
  project_id                        = var.project_id
  region                            = var.region
  service_name                      = "llm-gateway"
  image                             = var.image
  container_port                    = 4000
  service_account_email             = google_service_account.runtime.email
  startup_probe_path                = "/health/liveliness"
  cloudsql_instance_connection_name = module.cloud_sql.connection_name
  ingress                           = "INGRESS_TRAFFIC_INTERNAL_ONLY"

  # LiteLLM virtual keys authenticate callers. Cloud Run ingress restricts
  # network reachability to the project; Cloud Run IAM is left public so the
  # standard OpenAI SDK can call the internal URL without an ID-token adapter.
  allow_public_access = true

  env_vars = {
    PORT = "4000"
  }

  container_args = [
    "--config",
    "/etc/litellm/config.yaml",
    "--host",
    "0.0.0.0",
    "--port",
    "4000",
    "--telemetry",
    "False",
    "--use_v2_migration_resolver",
    "--enforce_prisma_migration_check",
  ]

  secret_volume_mounts = {
    litellm_config = {
      secret_id  = google_secret_manager_secret.config.secret_id
      mount_path = "/etc/litellm"
      file_name  = "config.yaml"
    }
  }

  secret_env_vars = {
    OPENAI_API_KEY     = module.secrets.secret_ids["OPENAI_API_KEY"]
    GEMINI_API_KEY     = module.secrets.secret_ids["GEMINI_API_KEY"]
    ANTHROPIC_API_KEY  = module.secrets.secret_ids["ANTHROPIC_API_KEY"]
    LITELLM_MASTER_KEY = module.secrets.secret_ids["LITELLM_MASTER_KEY"]
    LITELLM_SALT_KEY   = module.secrets.secret_ids["LITELLM_SALT_KEY"]
    DATABASE_URL       = google_secret_manager_secret.database_url.secret_id
  }
}
