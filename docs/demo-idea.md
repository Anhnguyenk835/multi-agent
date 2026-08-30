# Distributed AI Research Brief

## Purpose

Build a small, production-oriented demo that shows how independently deployed
AI agents collaborate in one workflow. The demo prioritizes distributed-system
concepts over sophisticated AI behaviour:

- explicit service boundaries and contracts;
- independently deployable and scalable agents;
- parallel work where dependencies allow it;
- framework and protocol independence; and
- observable, isolated service failures.

The intended result is an executive research brief. The result itself is only
the vehicle for demonstrating the architecture.

## User Scenario

A user submits a request such as:

> Analyze the AI coding-agent market and create an executive brief with the
> most important insights.

The system gathers general research and market-specific evidence in parallel,
combines them into structured analysis, then writes a concise brief.

## Agents

| Component | Role | Input | Output |
| --- | --- | --- | --- |
| Orchestrator | Coordinates the workflow; it does not perform domain reasoning. | User query | Final brief or controlled failure |
| Researcher | Collects general findings relevant to the query. | Query | Findings with source metadata |
| Market Agent | Collects market signals and competitor information. | Query | Market signals and competitors |
| Analyst | Synthesizes research and market data into a detailed, cited analysis. | Both research outputs | Markdown analysis with citations |
| Writer | Turns the analysis into a user-facing executive brief. | Analysis + citations | Markdown brief with citations |

## Workflow

```text
User query
    |
    v
Orchestrator
    |
    +--> Researcher -----+
    |                    |
    +--> Market Agent ---+--> Analyst --> Writer --> Executive brief
```

Researcher and Market Agent have no dependency on each other, so they run in
parallel. Analyst starts only after the orchestrator has collected the results
or applied the documented degraded-result policy. Writer runs only after a
valid analysis is available.

## Demonstration Goals

The completed demo must make the following visible:

1. Agents are services, not local functions inside one application.
2. The orchestrator coordinates capabilities but does not own their prompts,
   models, tools, or implementation details.
3. Agents may use different frameworks and protocols as long as their
   contracts remain stable.
4. Independent work is executed concurrently.
5. A request can be traced across the orchestrator and every invoked service.
6. A timeout or failure in one agent is handled explicitly without crashing
   unrelated services.

## Non-Goals

This is not a full agent platform. The demo excludes complex autonomous
planning, human approval flows, event buses, long-term memory, vector-search
infrastructure, Kubernetes, multi-region resilience, and enterprise
authorization.

The design is deliberately small so that the value and cost of distributed
agents remain easy to see.
