# Infrastructure

Terraform to deploy this service to Cloud Run as a standalone unit.

```text
infra/
  environments/
    dev/                    # this service's deployable environment
  modules/
    artifact_registry/      # Docker repo for this service's image
    cloud_run_service/      # generic parameterized Cloud Run v2 service
    secrets/                # empty Secret Manager containers + IAM binding
```

## Deploy

The first deploy is two applies: the Cloud Run service can't be created
until its image exists and its secrets have at least one version, and both
are produced by this same Terraform.

```bash
cd environments/dev
cp terraform.tfvars.example terraform.tfvars   # fill in project_id and image
terraform init

# Phase 1 — image repo and empty secret containers only.
terraform apply -target=module.artifact_registry -target=module.secrets

# Seed secrets. Secret Manager IDs are unique per project, so each service
# prefixes its own (researcher-*) to avoid colliding with the other services.
# The virtual key is provisioned by infra/llm-gateway/scripts; Exa remains a
# service-local tool credential.
for KEY in LLM_GATEWAY_API_KEY EXA_API_KEY; do
  grep "^$KEY=" ../../../.env | cut -d= -f2- | tr -d '\n' \
    | gcloud secrets versions add "researcher-$KEY" --data-file=-
done

# Phase 2 — the Cloud Run service itself.
terraform apply
```

Subsequent deploys are a plain `terraform apply`.

This service runs `langgraph dev` (the LangGraph Server's built-in dev
runner) inside its container — fine for a demo, not a production-grade
process manager. The startup probe hits its `/ok` health endpoint.

See `docs/deployment.md` at the repo root for the full cross-service plan
(deployment order, how services find each other, and the simplifications
made for this demo vs. a production setup).
