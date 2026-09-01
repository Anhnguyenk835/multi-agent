# LiteLLM Gateway Infrastructure

This directory owns the production inference boundary. OpenAI, Gemini, and
Anthropic credentials exist only on the LiteLLM runtime. Agent deployments use
one service-scoped `LLM_GATEWAY_API_KEY` and an internal `/v1` endpoint.

## Local Runtime

Copy `.env.example` to `.env`, set the five gateway-only secrets, then start
the full stack from the repository root:

```bash
docker compose up
```

`docker-compose.yml` includes this directory's LiteLLM Compose file, which
started from the official file fetched with `curl -sSLO` and remains the sole
local gateway runtime definition. It uses LiteLLM's version-pinned
database-ready image; there is no gateway Dockerfile to build or maintain.

The diagnostic port is bound to `127.0.0.1:4000`. Generate one virtual key per
service after the proxy is healthy:

```bash
export LLM_GATEWAY_ADMIN_URL=http://127.0.0.1:4000
export LITELLM_MASTER_KEY=<gateway-master-key>
./scripts/provision-virtual-key.sh researcher
```

Store the resulting value only as that service's `LLM_GATEWAY_API_KEY`. The
gateway returns a generated virtual key once; rotate by provisioning a new key,
updating the service secret, then revoking the old key through LiteLLM's key
management API.

## Cloud Run Deployment

The `environments/dev` Terraform stack creates the gateway's Artifact Registry
repository, Cloud SQL database, Secret Manager containers, and internal-only
Cloud Run service. It deliberately does not seed provider keys or the master
key, because Terraform state must not hold them.

```bash
cd environments/dev
cp terraform.tfvars.example terraform.tfvars
terraform init
terraform apply -target=module.cloud_sql -target=module.secrets
```

Seed `llm-gateway-OPENAI_API_KEY`, `llm-gateway-GEMINI_API_KEY`,
`llm-gateway-ANTHROPIC_API_KEY`, `llm-gateway-LITELLM_MASTER_KEY`, and
`llm-gateway-LITELLM_SALT_KEY` in Secret Manager, then run `terraform apply`.
Cloud Run runs the pinned official image directly and mounts the non-secret
`config.yaml` from Secret Manager. Set each agent environment's
`llm_gateway_base_url` to the `gateway_url` output with `/v1` appended.
