# Implementation Plan

## Definition of Done

The demo is complete when a user can submit a research query and receive an
executive brief generated through four independently runnable services. One
trace must show Researcher and Market Agent running in parallel, then Analyst
and Writer running in sequence. A controlled timeout in either parallel branch
must result in the documented degraded or failed workflow outcome.

## Phase 1: Contracts and Repository Foundation

1. Create a monorepo layout for `services/orchestrator`,
   `services/researcher`, `services/market-agent`, `services/analyst`,
   `services/writer`, `packages/contracts`, `infra`, and `docs`.
2. Define the Researcher input/output state for its remote-agent API,
   versioned Protobuf schemas for Market Agent, and versioned Pydantic or
   OpenAPI schemas for the HTTP services.
3. Define shared envelope fields, response statuses, error codes, and the
   source-metadata schema.
4. Add contract tests that prove valid and invalid payload behaviour without
   calling an LLM.

**Exit criterion:** all services can import their contract types and contract
validation runs in CI.

## Phase 2: Deterministic Agent Services

**Status:** Complete.

1. Implement each agent behind its actual transport using deterministic fixture
   data.
2. Implement health and readiness endpoints where appropriate.
3. Ensure each service returns the incoming `request_id` and propagates the
   `trace_id`.
4. Add a configurable failure mode for timeout, transient error, and invalid
   response scenarios.

**Exit criterion:** every service can be started and exercised independently
with a contract-valid response.

## Phase 3: LangGraph Orchestration

**Status:** Complete.

1. Define the top-level state, including branch statuses and warnings.
2. Implement concurrent Researcher and Market invocation.
3. Implement the join and its normal, degraded, and terminal-failure paths.
4. Invoke Researcher through `RemoteGraph`, Market Agent through gRPC, and
   Analyst and Writer through their independent HTTPS contracts.
5. Add per-agent timeout, retry, exponential backoff, and error mapping.
6. Configure durable StateGraph checkpointing for the deployed environment.

**Exit criterion:** local end-to-end workflow proves fan-out/fan-in and all
failure-policy branches using fixtures.

## Phase 4: AI Behaviour

1. Replace fixture responses with small, bounded LLM/tool implementations.
2. Require Researcher and Market Agent to return source metadata with each
   claim or signal.
3. Validate all LLM outputs against the agent response schema before returning
   them to the orchestrator.
4. Keep prompts and model configuration private to each agent service.
5. Keep Writer constrained to the Analyst output so it cannot invent a second
   research process.

**Exit criterion:** a realistic query yields a source-backed, schema-valid
brief without changing the orchestrator contracts.

## Phase 5: Observability and Security

1. Add structured logging and correlation IDs in every service.
2. Add LangSmith tracing for the orchestrator and Researcher; use Cloud Logging
   and the propagated trace context for all services.
3. Propagate trace context through `RemoteGraph`, gRPC, and HTTPS calls.
4. Authenticate service-to-service requests and test an unauthorized request
   is rejected.
5. Add redaction rules for prompts and sensitive content in logs.

**Exit criterion:** one request can be followed across all relevant logs and
traces, and unauthenticated calls cannot invoke private agents.

## Phase 6: Deployment and Demo Validation

1. Build immutable container images and deploy the services using Terraform.
2. Configure the deployed URLs and credentials through runtime configuration,
   not source code.
3. Run the happy path, one degraded-path scenario, and total parallel-stage
   failure in the deployed environment.
4. Record timings proving the two independent calls overlap.
5. Write a short demo script and expected outputs.

**Exit criterion:** the cloud deployment satisfies the definition of done and
can be recreated from Terraform.

## Focused Test Matrix

| Scenario | Expected result |
| --- | --- |
| All agents succeed | Final brief with no degraded warning. |
| Market Agent times out after retries | Final brief includes a market-data warning. |
| Researcher and Market Agent both fail | Workflow ends before Analyst. |
| Analyst returns invalid schema | Orchestrator fails safely; Writer is not called. |
| Repeated request with same idempotency key | No duplicate externally visible work or side effects. |
| Unauthorized inter-service call | Request is rejected before agent execution. |
