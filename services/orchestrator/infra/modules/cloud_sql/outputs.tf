output "connection_name" {
  value = google_sql_database_instance.this.connection_name
}

# Cloud Run's built-in Cloud SQL connector mounts the instance as a unix
# socket at /cloudsql/<connection_name> — no VPC connector needed.
output "database_url" {
  value     = "postgresql://${var.database_user}:${random_password.db.result}@/${var.database_name}?host=/cloudsql/${google_sql_database_instance.this.connection_name}&sslmode=disable"
  sensitive = true
}
