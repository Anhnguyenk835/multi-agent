resource "random_password" "db" {
  length  = 24
  special = false
}

resource "google_sql_database_instance" "this" {
  project          = var.project_id
  region           = var.region
  name             = var.instance_name
  database_version = "POSTGRES_17"

  settings {
    tier = var.tier
    # New Cloud SQL instances default to ENTERPRISE_PLUS, which rejects
    # legacy shared-core tiers like db-g1-small (it only accepts the
    # pricier db-perf-optimized-* tiers). ENTERPRISE is the edition that
    # still accepts db-g1-small.
    edition = "ENTERPRISE"
    ip_configuration {
      ipv4_enabled = true
    }
  }

  # Demo simplification: let `terraform destroy` actually tear this down.
  deletion_protection = false
}

resource "google_sql_database" "this" {
  project  = var.project_id
  instance = google_sql_database_instance.this.name
  name     = var.database_name
}

resource "google_sql_user" "this" {
  project  = var.project_id
  instance = google_sql_database_instance.this.name
  name     = var.database_user
  password = random_password.db.result
}
