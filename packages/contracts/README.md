# Contracts

This package retains reference service-boundary contracts. Version `v1` is the
current wire contract; incompatible changes create a new versioned module or
Protobuf package rather than changing existing fields. It is deliberately not
a runtime dependency: each independently deployable service owns its own copy
of the schemas it produces or consumes.

## Contract Types

| Boundary | Source of truth | Current version |
| --- | --- | --- |
| Market Analyst RemoteGraph | `market_analyst.py` Pydantic input/output and `MarketAnalystRemoteState` | `v1` |
| Competitor Analyst gRPC | `proto/distributed_agent_contracts/competitor/v1/competitor.proto` | `v1` |
| Analyst HTTPS | `analyst.py` Pydantic models | `v1` |
| Writer HTTPS | `writer.py` Pydantic models | `v1` |
| Orchestrator HTTPS | `orchestrator.py` Pydantic models | `v1` |

All requests carry `contract_version`, `request_id`, `trace_id`, `attempt`, and
an optional `deadline_at`. Responses additionally carry `status`, `warnings`,
and, for failures, a structured error.

The shared error-code catalog is: `VALIDATION_ERROR`, `UNAUTHORIZED`,
`FORBIDDEN`, `DEADLINE_EXCEEDED`, `UPSTREAM_UNAVAILABLE`,
`UPSTREAM_INVALID_RESPONSE`, `RATE_LIMITED`, `WORKFLOW_ABORTED`, and
`INTERNAL_ERROR`. A failed response requires one of these codes; successful and
degraded responses cannot include an error object.

## Generate Competitor Stubs

```bash
make generate-contract-reference-proto
```

The command writes the reference stubs to
`src/distributed_agent_contracts/competitor/v1/`. The Competitor Analyst and
Orchestrator consume the same generated v1 stubs.
