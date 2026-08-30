# Contracts

This package retains reference service-boundary contracts. Version `v1` is the
current wire contract; incompatible changes create a new versioned module or
Protobuf package rather than changing existing fields. It is deliberately not
a runtime dependency: each independently deployable service owns its own copy
of the schemas it produces or consumes.

## Contract Types

| Boundary | Source of truth | Current version |
| --- | --- | --- |
| Researcher RemoteGraph | `researcher.py` Pydantic input/output and `ResearcherRemoteState` | `v1` |
| Market Agent gRPC | `proto/distributed_agent_contracts/market/v1/market.proto` | `v1` |
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

## Generate Market Stubs

```bash
make generate-market-proto
```

The command writes the reference stubs to
`src/distributed_agent_contracts/market/v1/`. The Market Agent and
Orchestrator each keep their own generated v1 stubs; `tests/contract_compatibility`
checks their descriptors match.
