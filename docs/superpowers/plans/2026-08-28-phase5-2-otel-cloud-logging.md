# Phase 5.2: Production OpenTelemetry and Cloud Logging Implementation Plan

## Goal

Produce one standards-based distributed trace and correlated structured Cloud
Logging records for each workflow across Orchestrator, Researcher, Market
Agent, Analyst, and Writer.

This plan is independent from Phase 5.1 LangSmith tracing. It uses W3C
`traceparent`/`tracestate` plus OpenTelemetry (OTel), and it remains valuable
when LangSmith is disabled.

## Target Architecture

```text
Client
  └─ Orchestrator root OTel span
      ├─ HTTP/RemoteGraph → Researcher child span
      ├─ gRPC metadata → Market Agent child span
      ├─ HTTPS → Analyst child span
      └─ HTTPS → Writer child span

All services ── structured stdout JSON ──> Cloud Logging
All services ── OTLP ──> OpenTelemetry Collector ──> Google Cloud Trace
```

Cloud Logging is the log backend; it does not require OTel by itself. OTel is
used here to create/propagate technical spans and populate trace/span fields in
each log record. Google recommends W3C `traceparent` over the legacy Google
header, and gRPC propagates it through metadata. [Google trace context documentation](https://docs.cloud.google.com/trace/docs/trace-context)

## Scope and Constraints

- No authentication or authorization work in this demo phase.
- Keep the existing business `request_id` and `trace_id` contract fields. They
  are log attributes; they are not substituted for the 32-hex-character OTel
  trace ID.
- Each service owns local observability code/configuration. Do not introduce a
  shared Python package.
- Use Cloud Logging structured JSON on stdout/stderr. Do not use an OTel log
  exporter for application logs in the first implementation.
- Never set raw query, prompt, Exa content, response body, API key, token,
  cookie, or authorization header as an OTel span attribute or log field.

## Standard Resource and Log Schema

Every service configures these OTel resource attributes:

```text
service.name = orchestrator | researcher | market-agent | analyst | writer
service.version = application release/version
deployment.environment = local | dev | prod
cloud.region = deployment region (when available)
```

Every application log emits JSON with:

```text
severity, message, service, operation, request_id, business_trace_id,
otel_trace_id, otel_span_id, trace_sampled, attempt, outcome, latency_ms
```

For Cloud Logging correlation, also emit its reserved fields:

```text
logging.googleapis.com/trace = projects/PROJECT_ID/traces/OTEL_TRACE_ID
logging.googleapis.com/spanId = OTEL_SPAN_ID
logging.googleapis.com/trace_sampled = true|false
```

Cloud Logging can correlate structured log entries with traces using these
fields. [Cloud Trace/Logging correlation](https://docs.cloud.google.com/trace/docs/trace-log-integration)

## Task 1: Add local OTel bootstrap and redacting JSON logging

**Files:**
- Create local `observability.py` in every service package.
- Create local `logging.py` or extend `observability.py` in every service.
- Modify every service `pyproject.toml`.
- Create a local test module in every service.

- [ ] Add direct dependencies appropriate to each service: `opentelemetry-api`,
  `opentelemetry-sdk`, `opentelemetry-exporter-otlp-proto-grpc`,
  `opentelemetry-instrumentation-fastapi` (Orchestrator/Analyst/Writer),
  `opentelemetry-instrumentation-httpx` (Orchestrator),
  `opentelemetry-instrumentation-grpc` (Orchestrator/Market), and ASGI/FastAPI
  instrumentation required by the deployed Researcher server.
- [ ] Implement `configure_observability(service_name)` once per service. It
  builds a resource, parent-based sampler, tracer provider, OTLP span exporter,
  batch span processor, W3C `TraceContextTextMapPropagator`, and a JSON logger.
  It is idempotent so test app factories can run repeatedly.
- [ ] Implement a logging filter/formatter that reads the current OTel span
  context and maps it to the standard log schema plus Cloud Logging reserved
  fields. If no valid span exists, fields are null/absent rather than invented.
- [ ] Implement an allow-list redactor used before logging attributes. Retain
  counters, provider/model, exception class, status code, and a stable hash of
  an allowed identifier. Remove/replace fields named or resembling `api_key`,
  `token`, `authorization`, `cookie`, `password`, `secret`, `prompt`, and
  `content`.
- [ ] Test JSON formatting and redaction; assert valid OTel context produces
  Cloud Logging trace/span fields and that a secret never appears in rendered
  JSON.

## Task 2: Instrument inbound service boundaries

**Files:**
- Modify: `services/orchestrator/src/orchestrator/main.py`
- Modify: `services/analyst/src/analyst/main.py`
- Modify: `services/writer/src/writer/main.py`
- Modify: `services/market-agent/src/market_agent/server.py`
- Modify: Researcher application/server startup configuration.

- [ ] FastAPI services: call `FastAPIInstrumentor.instrument_app(app)` after
  application construction. Add application middleware only for business log
  fields (`request_id`, attempt); let OTel own parent extraction and span
  creation.
- [ ] Market Agent: install the OTel gRPC aio server interceptor before adding
  the servicer. Validate that incoming metadata is extracted before
  `AnalyzeMarket` logs or invokes the runner.
- [ ] Researcher: perform a focused compatibility spike against the exact
  `langgraph dev`/Agent Server version used by this repo. Prefer its ASGI/FastAPI
  instrumentation hook or launch under `opentelemetry-instrument`; confirm that
  the HTTP request which backs RemoteGraph creates a server span. Do not claim
  coverage until a parent-child integration test proves it.
- [ ] Name business spans inside inbound spans: `workflow.run`,
  `researcher.collect_findings`, `market.analyze`, `analyst.analyze`, and
  `writer.write`. Add only safe attributes such as attempt, mode, provider,
  result count, and outcome.

## Task 3: Instrument and verify all outbound propagation

**Files:**
- Modify: `services/orchestrator/src/orchestrator/clients/researcher.py`
- Modify: `services/orchestrator/src/orchestrator/clients/http.py`
- Modify: `services/orchestrator/src/orchestrator/clients/market.py`
- Modify: clients/tools in downstream services that make outbound provider or
  search calls where safe.
- Test: `services/orchestrator/tests/test_otel_propagation.py`.

- [ ] HTTP: instrument `httpx.AsyncClient`; confirm its client span injects
  `traceparent` and `tracestate` into Analyst/Writer requests. Preserve the
  current correlation checks and error mappings.
- [ ] RemoteGraph: verify the installed SDK's underlying HTTP path is covered
  by httpx instrumentation. If it is not, wrap the client transport or inject
  W3C headers at the SDK-supported request hook; do not put headers in graph
  state.
- [ ] gRPC: instrument the aio client and pass metadata through
  `AnalyzeMarket`. Confirm a new Market server span uses the Orchestrator client
  span as parent. The W3C context is carried through gRPC metadata, not the
  `.proto` message.
- [ ] Preserve W3C `tracestate` and sampling decisions. Never use the legacy
  `X-Cloud-Trace-Context` as the primary format; accepting it as an ingress
  compatibility fallback is optional.
- [ ] Add unit tests using an in-memory span exporter and fake HTTP/gRPC
  handlers: all child spans have the root trace ID and correct parent span ID.

## Task 4: Deploy an OTLP pipeline suitable for production

**Files:**
- Create: `infra/observability/otel-collector.yaml`
- Modify: `docker-compose.yml`
- Modify: `infra/environments/dev/*` and `docs/deployment.md`
- Create: `docs/observability.md`

- [ ] Local development: add an OpenTelemetry Collector service to Compose.
  Export spans to a debug/logging exporter for deterministic tests; configure
  application `OTEL_EXPORTER_OTLP_ENDPOINT` to the collector.
- [ ] Production: deploy an OpenTelemetry Collector appropriate to the runtime
  topology (a Cloud Run sidecar or a managed/shared collector endpoint) and use
  workload identity/ADC to export OTLP telemetry to Google Cloud's Telemetry
  API. Google recommends an OTel Collector/OTLP pipeline for Cloud Trace.
  [Cloud Trace setup](https://docs.cloud.google.com/trace/docs/setup)
- [ ] Configure exporter timeouts, bounded queues, and batch sizes so telemetry
  export cannot block agent requests. On queue overflow, drop telemetry and
  increment a local dropped-span metric/log rather than failing user work.
- [ ] Configure sampling: always-on in local/dev; parent-based ratio sampling
  in production. Start with a documented ratio and move to collector tail
  sampling for errors/slow traces when traffic requires it.
- [ ] Set Cloud Run/collector service accounts with only telemetry/log writing
  permissions necessary for the deployment. This is cloud infrastructure IAM,
  not service-to-service request authentication.

## Task 5: Prove end-to-end trace and logging behaviour

**Files:**
- Create: `tests/integration/test_phase5_otel_trace.py`
- Create: `tests/integration/test_phase5_structured_logs.py`
- Modify: `README.md` and `docs/observability.md`.

- [ ] Integration test, opt-in with `RUN_OTEL_INTEGRATION_TESTS=1`: send one
  workflow request through a real compose stack and query/capture collector
  output. Assert one trace ID has spans from all five `service.name` values.
- [ ] Assert expected relationships: Orchestrator is root; Researcher, Market,
  Analyst, and Writer are descendant spans. Allow retry spans to be siblings
  under their service invocation.
- [ ] Capture one structured log from each service and assert same
  `request_id`, same OTel trace ID, non-empty service name, and no secret/raw
  prompt data.
- [ ] Add failure-path coverage for injected timeout/transient modes: span
  status is error, retry attempts are visible, and the workflow response is
  unchanged.

## Acceptance Criteria

- A workflow request yields a single W3C trace across all five services.
- Logs from every service link to the trace in Cloud Logging and are searchable
  by `request_id`.
- HTTP, RemoteGraph, and gRPC each preserve `traceparent` parentage.
- OTel runs correctly whether Phase 5.1 LangSmith is enabled or disabled.
- Raw prompts, provider credentials, and sensitive response content are absent
  from spans and structured logs.
- `make test` and `make lint` pass; collector integration tests remain opt-in.
