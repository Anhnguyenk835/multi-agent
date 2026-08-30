# Phase 5.1: End-to-End LangSmith Tracing Implementation Plan

## Goal

Show one LangSmith trace tree for a single workflow invocation across
Orchestrator, Researcher, Market Agent, Analyst, and Writer, without adding a
shared runtime package or service-to-service authentication.

## Architecture

```text
Client
  └─ Orchestrator (root LangSmith run)
      ├─ RemoteGraph ──> Researcher (child run)
      ├─ gRPC ─────────> Market Agent (child run)
      ├─ HTTPS ────────> Analyst (child run)
      └─ HTTPS ────────> Writer (child run)
```

LangSmith's `langsmith-trace` and `baggage` headers are the cross-service
parent context. They are distinct from the existing business-level
`request_id` and `trace_id` fields: retain those fields as searchable
correlation metadata, but do not treat either as a LangSmith run ID.

Each service owns its local tracing/redaction module. `packages/contracts`
remains unused at runtime, and no `packages/observability` package is added.

## Scope and Constraints

- No authentication or authorization work in this phase.
- Trace all five services, not only the two LangChain/LangGraph services.
- Do not put raw prompts, API keys, bearer tokens, cookies, or full remote
  responses into LangSmith. Trace timing, hierarchy, model/provider metadata,
  counts, and redacted summaries instead.
- Preserve fixture-mode behaviour and all existing public HTTP/gRPC/RemoteGraph
  payloads.
- LangSmith propagation is additive: `langsmith-trace` and `baggage` are
  transport headers/metadata, never contract fields.
- Both caller and receiver must opt in to propagation. LangSmith supports
  `RunTree.to_headers()` at the caller and `tracing_context(parent=headers)` at
  the receiver. See the official [distributed tracing guide](https://docs.langchain.com/langsmith/distributed-tracing).

## Configuration Contract

Every service reads these environment variables, with tracing disabled by
default in local tests:

| Variable | Meaning |
| --- | --- |
| `LANGSMITH_TRACING` | `true` enables export; absent/`false` is a no-op. |
| `LANGSMITH_API_KEY` | Secret, injected only at deployment/runtime. |
| `LANGSMITH_PROJECT` | Default `distributed-agents-demo`. |
| `LANGSMITH_ENDPOINT` | Optional self-hosted/custom endpoint. |
| `LANGSMITH_REDACTION_MODE` | `strict` (default in deployed environments) or `off` (local debugging only). |

The API key is never read into a log record or included in a trace metadata
dictionary.

## Task 1: Establish safe local LangSmith helpers

**Files:**
- Create: `services/orchestrator/src/orchestrator/langsmith_tracing.py`
- Create: `services/researcher/src/researcher/langsmith_tracing.py`
- Create: `services/market-agent/src/market_agent/langsmith_tracing.py`
- Create: `services/analyst/src/analyst/langsmith_tracing.py`
- Create: `services/writer/src/writer/langsmith_tracing.py`
- Create corresponding unit tests in each service.

- [ ] Add `langsmith` as a direct dependency to each service's `pyproject.toml`.
  Do not rely on LangChain's transitive dependency.
- [ ] In each local helper, build a `langsmith.Client` configured with an
  anonymizer/redaction callable and a metadata transformer. It may retain:
  `service.name`, `request_id`, `workflow_status`, `attempt`, provider/model,
  result counts, and elapsed time. It must remove secret-shaped keys and mask
  configured PII patterns.
- [ ] Add `current_headers() -> dict[str, str]`. It returns
  `get_current_run_tree().to_headers()` when there is an active run, otherwise
  `{}`. This ensures disabled tracing does not create synthetic context.
- [ ] Add `parent_context(headers: Mapping[str, str])` as a thin wrapper for
  `langsmith.tracing_context(parent=headers, client=local_client)`. Header keys
  must be normalized to lowercase before use because gRPC metadata is
  lowercase.
- [ ] Add a `trace_service_operation` wrapper/decorator that records only a
  redacted input/output summary. Name spans consistently:
  `orchestrator.workflow`, `researcher.graph`, `market-agent.analyze`,
  `analyst.analyze`, and `writer.write`.
- [ ] Test the helper with a fake/disabled client: no secret-shaped value is in
  processed input, output, or metadata; absent context produces no headers.

Use LangSmith's client-level anonymizer or per-function
`process_inputs`/`process_outputs`; these transform trace payloads without
altering the value returned to the application. [LangSmith masking guidance](https://docs.langchain.com/langsmith/mask-inputs-outputs)

## Task 2: Make Orchestrator the root run and propagation owner

**Files:**
- Modify: `services/orchestrator/src/orchestrator/main.py`
- Modify: `services/orchestrator/src/orchestrator/workflow.py`
- Modify: `services/orchestrator/src/orchestrator/clients/researcher.py`
- Modify: `services/orchestrator/src/orchestrator/clients/http.py`
- Modify: `services/orchestrator/src/orchestrator/clients/market.py`
- Test: `services/orchestrator/tests/test_langsmith_tracing.py`

- [ ] Start `orchestrator.workflow` around `WorkflowService.run`, with
  redacted input and metadata containing `request_id`, existing business
  `trace_id`, and query length—not raw query text.
- [ ] Ensure retry attempts remain child runs of the workflow root. Add attempt
  number and target service as metadata, but do not create a second root run.
- [ ] RemoteGraph: obtain `current_headers()` immediately before `ainvoke` and
  pass `langsmith-trace` and `baggage` through LangGraph's invocation
  `configurable` values. Retain normal request payload unchanged. The
  Researcher plan below consumes those configurable values.
- [ ] HTTPS: extend `_post` with optional headers and inject the current
  LangSmith headers on calls to Analyst and Writer.
- [ ] gRPC: pass the same header pairs as ASCII metadata in
  `MarketAgentStub.AnalyzeMarket(..., metadata=...)`.
- [ ] Add tests that monkeypatch the outbound clients and assert that all three
  transport paths receive `langsmith-trace` and `baggage` when a root run is
  active, and no headers when tracing is disabled.

## Task 3: Accept the parent in Researcher and trace graph/LLM work

**Files:**
- Modify: `services/researcher/src/researcher/graph.py`
- Modify: `services/researcher/langgraph.json`
- Modify: `services/researcher/pyproject.toml`
- Test: `services/researcher/tests/test_langsmith_tracing.py`

- [ ] Remove the stale `../../packages/contracts` entry from `langgraph.json`.
- [ ] Read `langsmith-trace` and `baggage` from the graph invocation's
  `configurable` mapping. Do not copy them into graph state or output.
- [ ] Wrap fixture and live graph execution in `parent_context(headers)` so
  `researcher.graph` becomes a child of `orchestrator.workflow`.
- [ ] Configure the compiled LangChain agent/graph with a local
  `LangChainTracer(client=redacting_client)` callback. This keeps LLM and tool
  runs nested below the Researcher run while applying the redaction policy.
- [ ] Add traceable wrappers for the local Exa search tool and final grounding
  step. Record source count and domain list only; never persist full Exa text
  unless explicitly approved by the redaction policy.
- [ ] Test that configurable parent headers are used, the output contract is
  unchanged, and fixture/live execution does not emit raw query content to the
  trace serializer.

## Task 4: Instrument Market Agent, Analyst, and Writer

**Files:**
- Modify: `services/market-agent/src/market_agent/server.py`
- Modify: `services/market-agent/src/market_agent/runner.py`
- Modify: `services/market-agent/src/market_agent/tools.py`
- Modify: `services/analyst/src/analyst/main.py`
- Modify: `services/analyst/src/analyst/analysis.py`
- Modify: `services/analyst/src/analyst/llm_client.py`
- Modify: `services/writer/src/writer/main.py`
- Modify: `services/writer/src/writer/brief.py`
- Modify: `services/writer/src/writer/llm_client.py`
- Test: one tracing test module per service.

- [ ] Market Agent: read `context.invocation_metadata()`, enter
  `parent_context(dict(metadata))`, then trace the server handler, runner,
  search calls, and fallback attempt. gRPC metadata may carry both
  `langsmith-trace` and `baggage`.
- [ ] Analyst/Writer: add a FastAPI middleware that stores the inbound
  LangSmith headers for the request. Wrap `/analyze` and `/write` in their
  parent context, then trace structured generation and provider fallback.
- [ ] For all three services, use redacted summaries such as item counts,
  schema name, provider, model, status, and latency. Do not pass Pydantic
  request objects with raw findings/prompts as a traced function argument.
- [ ] Test each server boundary with a supplied parent header and assert the
  operation is linked to that parent context; test no tracing headers changes
  no public response.

## Task 5: Integration verification and operational documentation

**Files:**
- Create: `tests/integration/test_phase5_langsmith_tracing.py`
- Modify: `README.md`
- Modify: `docs/deployment.md`
- Modify: service READMEs.

- [ ] Add a skipped-by-default integration test enabled by
  `RUN_LANGSMITH_INTEGRATION_TESTS=1`. It sends one workflow request to a real
  compose/deployed stack with a dedicated test project, then queries LangSmith
  by `request_id` metadata.
- [ ] Assert one root workflow run and descendants named for Researcher,
  Market Agent, Analyst, and Writer. Assert parentage, not only equal tags.
- [ ] Add a cleanup/retention note for test traces and never use production
  project credentials in CI.
- [ ] Document the environment variables, redaction policy, and that no
  service-to-service authentication is included in this demo phase.

## Acceptance Criteria

- A single workflow invocation renders as one LangSmith tree containing all
  five service operations.
- RemoteGraph, gRPC, and HTTPS all preserve LangSmith parentage.
- Trace payloads contain no configured secret/PII patterns and do not contain
  raw prompt/query content in strict mode.
- Existing fixture-mode/unit/integration behaviour remains intact.
- `make test` and `make lint` pass; LangSmith integration is opt-in.
