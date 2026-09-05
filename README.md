# Distributed Agents Demo

This repository is a simple `uv` workspace for a distributed AI-agent demo.
The LangGraph Orchestrator coordinates independently deployable services; it
does not own their internal agent logic.

## Repository Layout

```text
services/
  orchestrator/        LangGraph workflow control plane
  researcher/          LangGraph RemoteGraph-compatible research agent
  market-agent/        Google ADK gRPC market agent
  analyst/             LangChain HTTPS analysis service
  writer/              HTTPS executive-brief service
packages/
  contracts/           Reference v1 contract artifacts (not a runtime dependency)
infra/                 Terraform layout for GCP deployment
docs/                  Demo, architecture, implementation, and deployment docs
```

## Local Setup

```bash
uv sync --all-packages --all-groups
uv run --env-file services/orchestrator/.env --package orchestrator opentelemetry-instrument uvicorn orchestrator.main:app --reload
```

Use `make lint` and `make test` for workspace checks. Every service declares
its own dependencies and owns the boundary schemas it produces or consumes.
`packages/contracts` is retained as a future reference artifact; no service
imports it at runtime.

## Local Docker

Start the service containers with:

```bash
docker compose up --build
```

Before starting the stack, copy `infra/llm-gateway/.env.example` to
`infra/llm-gateway/.env` and set the gateway-only provider keys and master
key. Agent service `.env` files contain only their own LiteLLM virtual key and
logical route; provider credentials must not be copied into them.

Copy `infra/observability/.env.example` to `infra/observability/.env` and set
`LANGFUSE_SECRET_KEY`, `LANGFUSE_PUBLIC_KEY`, and `LANGFUSE_BASE_URL` to the
values from the Langfuse project settings. The Collector creates the required
Basic Auth header. Applications send OTLP only to the local Collector;
Langfuse credentials are never exposed to service containers.
Set `OTEL_SDK_DISABLED=true` to run a service without tracing.

The `opentelemetry-instrument` runtime owns SDK bootstrap, OTLP export, and
framework instrumentation. Each service owns only its OTel dependencies,
business spans, correlation, and exceptional propagation boundaries in its
local `<service>/telemetry.py` module. There is no shared runtime telemetry
package. Teams must keep the common attribute contract (`app.*`, `gen_ai.*`,
and `langfuse.*`) stable; the Collector owns export policy and credentials.
LiteLLM uses parent-based sampling with root sampling disabled: model, usage,
cost, and gateway latency spans are retained inside sampled business traces,
while standalone Admin UI and health-check traces are discarded at source.
The Collector treats LiteLLM generation spans as the canonical usage and cost
source, preventing agent-framework spans from double-counting token totals.

Every service has its own `services/<service>/Dockerfile`, so service-specific
runtime dependencies and startup commands remain isolated. The Orchestrator is
available at `http://localhost:8000/health`. The deterministic Phase 2 services
are exposed as follows:

| Service | Local contract | Readiness |
| --- | --- | --- |
| Researcher | LangGraph RemoteGraph at `http://localhost:8001`, graph `researcher` | `GET /ok` |
| Market Agent | gRPC `distributed_agents.market.v1.MarketAgent` on `localhost:50051` | gRPC Health Checking |
| Analyst | `POST http://localhost:8002/analyze` | `GET /ready` |
| Writer | `POST http://localhost:8003/write` | `GET /ready` |
| LiteLLM gateway | OpenAI-compatible API on `http://localhost:4000/v1` | `GET /health/liveliness` |
| OTel Collector | OTLP gRPC `localhost:4317`, HTTP `localhost:4318` | Extension on `localhost:13133` |
| PostgreSQL | Checkpoints on `localhost:5434` | `pg_isready` |

The Orchestrator exposes `POST http://localhost:8000/workflows` and stores each
LangGraph thread in PostgreSQL using the workflow `request_id` as `thread_id`.
Repeating a completed request with the same ID returns the checkpointed result.

## Streaming Agent Platform

The browser-facing stream is `POST /workflows/stream` with the same JSON body
as `/workflows`; it returns `text/event-stream`. It emits safe agent activity,
Researcher search/source events, Writer prose deltas, and a terminal workflow
response. Run the frontend locally with:

```bash
cd agent-platform
npm run dev
```

Vite proxies `/api` to the local Orchestrator on port 8000. For a separately
hosted frontend, set `ORCHESTRATOR_ALLOWED_ORIGINS` to its comma-separated
origin list. Agent activities are product-defined summaries; prompts,
chain-of-thought, raw search excerpts, and secrets are never streamed.

Set `<SERVICE>_FAILURE_MODE` to `timeout`, `transient_error`, or
`invalid_response` before starting Compose to demonstrate isolated failures.
Valid service names are `RESEARCHER`, `MARKET`, `ANALYST`, and `WRITER`.
Orchestrator call policies are configurable with
`ORCHESTRATOR_<AGENT>_TIMEOUT_SECONDS`, `_MAX_ATTEMPTS`, and
`_BACKOFF_SECONDS` variables.

Stop the local stack with:

```bash
docker compose down
```
