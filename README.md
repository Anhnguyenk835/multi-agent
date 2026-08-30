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
uv run --package orchestrator uvicorn orchestrator.main:app --reload
```

Use `make lint` and `make test` for workspace checks. Every service declares
its own dependencies and owns the boundary schemas it produces or consumes.
`packages/contracts` is retained as a future reference artifact; no service
imports it at runtime.

## LangSmith tracing

Set `LANGSMITH_TRACING=true` and provide `LANGSMITH_API_KEY` to trace one
workflow across Orchestrator, Researcher, Market Agent, Analyst, and Writer.
The Orchestrator propagates LangSmith context through RemoteGraph, gRPC, and
HTTPS. Compose sets `LANGSMITH_HIDE_INPUTS=true` and
`LANGSMITH_HIDE_OUTPUTS=true`, so traces retain hierarchy and safe metadata
without recording raw prompts or responses.

## Local Docker

Start the service containers with:

```bash
docker compose up --build
```

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
