resource "google_secret_manager_secret" "this" {
  for_each  = toset(var.secret_names)
  project   = var.project_id
  secret_id = "${var.name_prefix}${each.value}"

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_iam_member" "accessor" {
  for_each  = google_secret_manager_secret.this
  project   = var.project_id
  secret_id = each.value.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${var.accessor_service_account_email}"
}
