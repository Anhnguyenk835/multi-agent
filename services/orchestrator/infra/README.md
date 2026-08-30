# Infrastructure

Terraform to deploy this service to Cloud Run. Unlike the other four
services, this one depends on their deployed URLs and provisions its own
Cloud SQL instance for the LangGraph checkpointer.

```text
infra/
  environments/
    dev/                    # this service's deployable environment
  modules/
    artifact_registry/      # Docker repo for this service's image
    cloud_run_service/      # generic parameterized Cloud Run v2 service
    cloud_sql/              # Postgres instance for the checkpointer
    secrets/                # empty Secret Manager containers + IAM binding
```

## Deploy

Deploy `analyst`, `writer`, `researcher`, and `market-agent` first, and note
each one's `url` output.

The first deploy is two applies: the Cloud Run service can't be created
until its image exists and its secrets have at least one version, and both
are produced by this same Terraform.

```bash
cd environments/dev
cp terraform.tfvars.example terraform.tfvars
# fill in project_id, image, and the four *_url variables from the step above
terraform init

# Phase 1 — image repo and empty secret containers only.
terraform apply -target=module.artifact_registry -target=module.secrets

# Seed secrets. Secret Manager IDs are unique per project, so each service
# prefixes its own (orchestrator-*) to avoid colliding with the other services.
# Values can come straight from this service's local .env:
for KEY in LANGSMITH_API_KEY; do
  grep "^$KEY=" ../../../.env | cut -d= -f2- | tr -d '\n' \
    | gcloud secrets versions add "orchestrator-$KEY" --data-file=-
done

# Phase 2 — Cloud SQL, the database-URL secret, and the Cloud Run service.
terraform apply
```

Subsequent deploys are a plain `terraform apply`.

`CHECKPOINT_DATABASE_URL` needs no seeding: Terraform already generates the
DB password via `random_password` inside `module.cloud_sql`, writes the
secret version itself, and orders it ahead of the Cloud Run service.

See `docs/deployment.md` at the repo root for the full cross-service plan
(deployment order, how services find each other, and the simplifications
made for this demo vs. a production setup).
