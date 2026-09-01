# Researcher

LangGraph research agent, served as a `RemoteGraph` (`langgraph dev`) that
the Orchestrator calls directly. `AI_MODE` switches between a deterministic
fixture and a real ReAct search agent behind the same
`ResearcherInput`/`ResearcherOutput` contract.

## Architecture

```mermaid
flowchart TD
    I[ResearcherInput<br/>query, request_id, trace_id] --> R[RemoteGraph / LangGraph Server]
    R --> G[run_react_agent]
    G --> M{LangChain create_agent<br/>LiteLLM logical route}
    M -->|search, max 3 calls| S[Local Exa search tool<br/>tools.py]
    S -->|tagged results| M
    M -->|submit LLMFindingsResponse| V[Validate source tags]
    V -->|known tags| O[ResearcherOutput<br/>grounded findings]
    V -->|unknown tag| E[GroundingError]
```

## Live ReAct Flow

```text
1. Orchestrator calls the `researcher` RemoteGraph with request and trace IDs.
2. `run_react_agent` creates a request-local LangChain agent and Exa tool.
3. The model decides whether to call `search`; middleware limits it to 3 calls.
4. Each search result receives a stable tag: {tool_call_id}#{position}.
5. The model submits `LLMFindingsResponse` containing only source tags.
6. Researcher resolves tags against tool messages and builds source objects itself.
7. Researcher returns a schema-validated `ResearcherOutput`; unknown tags fail.
```

- `AI_MODE=fixture` (default): two hardcoded findings, no API keys.
- `search` calls Exa directly — no shared code with Market Agent.
- Findings cite a string tag (`tool_call_id#position`); an unknown tag fails
  the run. The service builds every `Source` itself, never trusting model text.
- `ToolCallLimitMiddleware` caps search at 3 calls; the model submits via a
  synthetic `LLMFindingsResponse` tool call, not free text.
- The OpenAI-compatible `ChatOpenAI` client calls LiteLLM; provider selection
  and fallback are owned by the gateway.
- `request_id` and `trace_id` remain in the service contract for correlation.

| File | Responsibility |
| --- | --- |
| `graph.py` | Fixture/live graphs |
| `tools.py` | `search` tool + tag bookkeeping |
| `llm_schema.py` / `prompts.py` | Model-facing schema and prompt |

## Configuration

`services/researcher/.env` (own copy, not shared): `AI_MODE`,
`LLM_GATEWAY_BASE_URL`, `LLM_GATEWAY_API_KEY`, `LLM_MODEL_ROUTE`,
`EXA_API_KEY`, `EXA_MAX_RESULTS`, `EXA_CONTENT_MAX_CHARACTERS`,
`LLM_TIMEOUT_SECONDS`, `LLM_MAX_OUTPUT_TOKENS`.

## Run

```bash
cd services/researcher
uv run --package researcher langgraph dev --config langgraph.json --port 8001 --no-browser  # standalone
docker compose up --build researcher                                                        # full stack
uv run --package researcher pytest services/researcher/tests -v                             # tests
```
