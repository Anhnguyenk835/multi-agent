# ReAct Search Agents for Researcher & Market Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Researcher's and Market Agent's single-shot "search once, synthesize once" live pipeline with a real ReAct tool-calling loop (LLM decides when/how to search, up to 3 times), using each framework's own native agent primitives (LangChain's `create_agent` for Researcher, Google ADK's `LlmAgent` for Market Agent), with the search tool implemented **locally in each service** — no shared `ai_runtime.exa_search` — so the two services could live in separate repos.

**Architecture:** Both services keep their exact existing public boundary (Researcher's `ResearcherInput`/`ResearcherOutput` LangGraph contract, Market Agent's gRPC `MarketRequest`/`MarketResponse`). Internally, `AI_MODE=live` now builds a native tool-calling agent instead of a fixed 3-node pipeline. Each service's own `search` tool calls `exa_py.AsyncExa` directly. Grounding stays the same principle as Phase 4 (the LLM never invents a `Source`; the service builds it from its own Exa results) but the tag the LLM cites is now a **string** `"{tool_call_id}#{position}"` instead of an integer — required because the compiled graph/agent is a long-lived singleton shared across concurrent requests, so there is no safe place for a shared mutable "running index" counter. `{tool_call_id}` is unique per tool invocation (assigned by the model API / ADK), so no cross-request or cross-call state is needed; grounding is reconstructed by scanning the finished conversation's tool messages/events after the loop ends.

**Tech Stack:** `langchain.agents.create_agent` + `langchain.agents.middleware.{ToolCallLimitMiddleware, AgentMiddleware}` + `langchain_openai.ChatOpenAI` (pointed at Groq's OpenAI-compatible endpoint for primary, real OpenAI for fallback) for Researcher. `google.adk.agents.LlmAgent` + `google.adk.tools.FunctionTool` + `google.adk.models.lite_llm.LiteLlm` (via the `google-adk[extensions]` extra) for Market Agent. `exa-py` (`AsyncExa`) directly in both services.

**Spec:** No separate spec document — design was approved inline in chat (see conversation); this plan is the record of what was approved and verified.

## Global Constraints

- **Scope:** only Researcher and Market Agent change. Analyst, Writer, Orchestrator, `packages/contracts` are not touched.
- **No shared search tool.** Neither service imports Exa-calling code from `ai_runtime`. `packages/ai-runtime/src/ai_runtime/exa_search.py` is deleted, along with its test and the `exa-py` dependency in `ai-runtime`'s own `pyproject.toml`.
- **`AIRuntimeSettings` drops its 3 Exa fields** (`exa_api_key`, `exa_max_results`, `exa_highlight_max_characters`) — they were only ever used by the code being deleted. `ai_mode`, `groq_api_key`, `groq_model`, `openai_api_key`, `openai_model`, `llm_timeout_seconds` stay (Analyst/Writer still use `ai_runtime.structured_llm` unchanged; Researcher/Market Agent still read `AI_MODE`/`GROQ_API_KEY`/etc. through `AIRuntimeSettings` to decide fixture-vs-live and to get raw credentials, they just stop calling `generate_structured`).
- **`langchain-groq` must never be added as a dependency.** Verified: every published `langchain-groq` version pins `groq<1`, which conflicts with `ai-runtime`'s `groq>=1.7.0` in this shared uv workspace (one lockfile for all members) — `uv sync` fails with an unsatisfiable-requirements error. Researcher reaches Groq through `langchain_openai.ChatOpenAI(openai_api_base="https://api.groq.com/openai/v1", ...)` instead — Groq's API is OpenAI-compatible, and `langchain-openai` has no dependency on the `groq` package at all.
- **Max 3 search-tool calls per request**, in both services, enforced by the framework (`ToolCallLimitMiddleware(tool_name="search", run_limit=3, exit_behavior="end")` for Researcher; a call counter checked inside the tool function itself for Market Agent, since ADK has no built-in equivalent).
- **Groq-primary/OpenAI-fallback stays exactly as strict as Phase 4:** fallback only on transport-class errors (timeout, rate limit, connection error, 5xx/`InternalServerError`); auth errors and bad-request errors propagate immediately with no fallback attempt. This is enforced by a custom `AgentMiddleware` for Researcher (the built-in `ModelFallbackMiddleware` was checked and rejected — it catches bare `Exception`, which would also fall back on auth/bad-request errors, violating this constraint) and by a manual two-`LlmAgent` retry wrapper for Market Agent.
- **Grounding invariant unchanged in spirit:** every finding/signal cites a tag the service issued (not a URL the LLM invented); an unknown tag is a hard failure (`AIRuntimeError`/`ValueError`), not a warning.
- **Fixture mode (`AI_MODE=fixture`) and `DEMO_FAILURE_MODE` injection are untouched** in both services — this plan only replaces code inside each service's existing "live" branch.
- **`docker-compose.yml` and every `.env`/`.env.example` file are unchanged** — same `EXA_API_KEY`/`EXA_MAX_RESULTS`/`EXA_HIGHLIGHT_MAX_CHARACTERS`/`GROQ_*`/`OPENAI_*`/`AI_MODE`/`LLM_TIMEOUT_SECONDS` keys, just parsed by different code.
- **Verified library facts this plan relies on** (checked against the actually-installed versions in this workspace: `langgraph==1.2.11`, `langchain==1.3.18`, `google-adk` with the `extensions` extra installed, `litellm==1.98.0`):
  - `langchain.agents.create_agent(model, tools, *, system_prompt=None, middleware=(), response_format=None, state_schema=None, ...) -> CompiledStateGraph`. `create_react_agent` is deprecated in this version; use `create_agent`.
  - `langchain.agents.middleware.ToolCallLimitMiddleware(*, tool_name=None, thread_limit=None, run_limit=None, exit_behavior='continue'|'error'|'end')`.
  - `langchain.agents.middleware.AgentMiddleware` base class exposes `wrap_model_call(self, request: ModelRequest, handler) -> ModelResponse | AIMessage` (sync) and `awrap_model_call` (async); `request.override(model=...)` swaps the model for a retry.
  - `langchain_openai.ChatOpenAI` fields include `model_name`, `openai_api_key`, `openai_api_base`, `request_timeout` (not `base_url`/`api_key`/`timeout` — those are aliases that don't show in `model_fields` introspection on this version).
  - `google.adk.tools.FunctionTool(func)` wraps a plain Python callable; ADK introspects its signature/docstring for the tool schema.
  - `google.adk.tools.ToolContext` has a `.function_call_id` attribute usable as a per-invocation unique tag, and a `.state` dict.
  - `google.adk.agents.LlmAgent` is a pydantic model with `model: str | BaseLlm`, `tools: list[...]`, `output_schema: type | None` fields; its own inline docs confirm **`output_schema` and `tools` can be used together** — ADK exposes tools during the reasoning loop and only enforces the schema on the final output.
  - `google.adk.models.lite_llm.LiteLlm(model: str, **kwargs)` requires the `google-adk[extensions]` extra (pulls in `litellm` and a large transitive dependency tree — accepted per user decision). `litellm` model strings use provider prefixes `"groq/<model>"` and `"openai/<model>"`, reading `GROQ_API_KEY`/`OPENAI_API_KEY` from the environment automatically. `litellm.exceptions` exposes `Timeout`, `RateLimitError`, `APIConnectionError`, `InternalServerError` (fallback-worthy) and `AuthenticationError`, `PermissionDeniedError`, `BadRequestError` (not fallback-worthy) — same shape as the `groq`/`openai` SDKs Phase 4 already classified.
- This repository has no `.git` — skip every "Commit" step below, same as the Phase 4 plan.

---

## Task 1: Remove the shared Exa module from `ai-runtime`

**Files:**
- Delete: `packages/ai-runtime/src/ai_runtime/exa_search.py`
- Delete: `packages/ai-runtime/tests/test_exa_search.py`
- Modify: `packages/ai-runtime/pyproject.toml`
- Modify: `packages/ai-runtime/src/ai_runtime/settings.py`
- Modify: `packages/ai-runtime/tests/test_settings.py`

**Interfaces:**
- Produces: `AIRuntimeSettings` with fields `ai_mode`, `groq_api_key`, `groq_model`, `openai_api_key`, `openai_model`, `llm_timeout_seconds` only (no more `exa_*` fields). Consumed unchanged by Analyst/Writer; consumed by Researcher/Market Agent's own settings (Tasks 2/4) for `ai_mode`/`groq_*`/`openai_*`.

- [ ] **Step 1: Delete the Exa module and its test**

```bash
rm packages/ai-runtime/src/ai_runtime/exa_search.py
rm packages/ai-runtime/tests/test_exa_search.py
```

- [ ] **Step 2: Remove `exa-py` from `ai-runtime`'s dependencies**

```toml
# packages/ai-runtime/pyproject.toml
[project]
name = "ai-runtime"
version = "0.1.0"
description = "Shared Groq/OpenAI runtime for the distributed-agent demo services"
requires-python = ">=3.12"
dependencies = [
    "groq>=1.7.0",
    "openai>=1.54.0",
    "pydantic>=2.10.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

- [ ] **Step 3: Remove the Exa fields from `AIRuntimeSettings`**

```python
# packages/ai-runtime/src/ai_runtime/settings.py
import os
from dataclasses import dataclass
from enum import StrEnum

from ai_runtime.errors import ProviderConfigurationError

_DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"
_DEFAULT_OPENAI_MODEL = "gpt-4o-mini"


class AIMode(StrEnum):
    FIXTURE = "fixture"
    LIVE = "live"


@dataclass(frozen=True, slots=True)
class AIRuntimeSettings:
    ai_mode: AIMode = AIMode.FIXTURE
    groq_api_key: str | None = None
    groq_model: str = _DEFAULT_GROQ_MODEL
    openai_api_key: str | None = None
    openai_model: str = _DEFAULT_OPENAI_MODEL
    llm_timeout_seconds: float = 12.0

    @property
    def live_mode(self) -> bool:
        return self.ai_mode is AIMode.LIVE

    @classmethod
    def from_environment(cls) -> "AIRuntimeSettings":
        ai_mode = AIMode(os.getenv("AI_MODE", AIMode.FIXTURE.value))
        groq_api_key = os.getenv("GROQ_API_KEY") or None

        if ai_mode is AIMode.LIVE and not groq_api_key:
            raise ProviderConfigurationError("AI_MODE=live requires GROQ_API_KEY to be set")

        return cls(
            ai_mode=ai_mode,
            groq_api_key=groq_api_key,
            groq_model=os.getenv("GROQ_MODEL") or _DEFAULT_GROQ_MODEL,
            openai_api_key=os.getenv("OPENAI_API_KEY") or None,
            openai_model=os.getenv("OPENAI_MODEL") or _DEFAULT_OPENAI_MODEL,
            llm_timeout_seconds=max(1.0, float(os.getenv("LLM_TIMEOUT_SECONDS", "12"))),
        )
```

- [ ] **Step 4: Remove the Exa assertions from `test_settings.py`**

In `packages/ai-runtime/tests/test_settings.py`, remove every `exa_*` assertion and every `EXA_*` env var reference from all 4 existing tests (`test_default_settings_are_fixture_mode`, `test_from_environment_defaults_to_fixture_without_any_env_vars`, `test_from_environment_live_mode_requires_groq_key`, `test_from_environment_live_mode_with_key_reads_all_fields`). The file should end up identical to before except every line mentioning `exa`/`EXA` is gone.

- [ ] **Step 5: Run the ai-runtime test suite**

Run: `uv run --package ai-runtime pytest packages/ai-runtime/tests -v`
Expected: PASS (17 tests: 4 settings + 13 structured_llm; the 5 exa_search tests are gone).

- [ ] **Step 6: Sync the workspace**

Run: `uv sync --all-packages --all-groups`
Expected: completes without error, `exa-py` no longer listed as an `ai-runtime` dependency.

- [ ] **Step 7: Commit**

Skipped — no git repository.

---

## Task 2: Researcher's local search tool

**Files:**
- Modify: `services/researcher/pyproject.toml`
- Modify: `services/researcher/src/researcher/settings.py`
- Create: `services/researcher/src/researcher/tools.py`
- Test: `services/researcher/tests/test_tools.py`

**Interfaces:**
- Produces: `researcher.tools.search` — a `langchain_core.tools` `BaseTool` (built with the `@tool` decorator) named `"search"`, taking `query: str`, calling Exa directly, returning a JSON string `{"results": [{"tag": "<tool_call_id>#<position>", "title", "publisher", "url", "published_at", "retrieved_at", "excerpt"}, ...]}`. `tag` is the grounding key Task 3 validates against.
- Produces: `researcher.tools.ExaSourceResult` (frozen dataclass, same shape as the deleted `ai_runtime.exa_search.ExaSourceResult` but service-local) and `researcher.tools.parse_tool_message(message: ToolMessage) -> list[ExaSourceResult]` (used by Task 3 to reconstruct the grounding pool from finished conversation state).
- Consumes: `researcher.settings.ResearcherExaSettings` (new, Task 2) for `exa_api_key`/`exa_max_results`/`exa_highlight_max_characters`.

- [ ] **Step 1: Add `exa-py` (already added) — confirm it's present**

`services/researcher/pyproject.toml` already has `"exa-py>=1.9.0"` in `dependencies` (added during design verification). Confirm:

Run: `grep -n "exa-py" services/researcher/pyproject.toml`
Expected: one match.

- [ ] **Step 2: Add local Exa settings to `researcher/settings.py`**

```python
# services/researcher/src/researcher/settings.py
import os
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from ai_runtime.settings import AIRuntimeSettings
from dotenv import load_dotenv

# Each service owns its own .env (services/researcher/.env) rather than
# sharing one repo-root file, matching independent deployability.
load_dotenv(Path(__file__).resolve().parents[2] / ".env")


class FailureMode(StrEnum):
    NONE = "none"
    TIMEOUT = "timeout"
    TRANSIENT_ERROR = "transient_error"
    INVALID_RESPONSE = "invalid_response"


@dataclass(frozen=True, slots=True)
class ResearcherExaSettings:
    exa_api_key: str | None = None
    exa_max_results: int = 4
    exa_highlight_max_characters: int = 1200

    @classmethod
    def from_environment(cls) -> "ResearcherExaSettings":
        return cls(
            exa_api_key=os.getenv("EXA_API_KEY") or None,
            exa_max_results=max(1, int(os.getenv("EXA_MAX_RESULTS", "4"))),
            exa_highlight_max_characters=max(
                200, int(os.getenv("EXA_HIGHLIGHT_MAX_CHARACTERS", "1200"))
            ),
        )


@dataclass(frozen=True, slots=True)
class DemoSettings:
    failure_mode: FailureMode = FailureMode.NONE
    delay_seconds: float = 0.25
    ai_runtime: AIRuntimeSettings = field(default_factory=AIRuntimeSettings)
    exa: ResearcherExaSettings = field(default_factory=ResearcherExaSettings)

    @classmethod
    def from_environment(cls) -> "DemoSettings":
        failure_mode = FailureMode(os.getenv("DEMO_FAILURE_MODE", FailureMode.NONE))
        delay_ms = max(0, int(os.getenv("DEMO_FAILURE_DELAY_MS", "250")))
        return cls(
            failure_mode=failure_mode,
            delay_seconds=delay_ms / 1_000,
            ai_runtime=AIRuntimeSettings.from_environment(),
            exa=ResearcherExaSettings.from_environment(),
        )
```

- [ ] **Step 3: Write the failing test for `tools.py`**

```python
# services/researcher/tests/test_tools.py
import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from langchain_core.messages import ToolMessage

from researcher.settings import ResearcherExaSettings
from researcher.tools import ExaSourceResult, build_search_tool, parse_tool_message


def _exa_result(**overrides: object) -> SimpleNamespace:
    defaults: dict[str, object] = {
        "url": "https://www.example.com/article",
        "title": "Example Article",
        "published_date": "2026-01-01T00:00:00.000Z",
        "highlights": ["Teams are adopting AI coding agents."],
        "text": None,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


class _FakeExaClient:
    def __init__(self, *, results: list[SimpleNamespace] | None = None) -> None:
        self._results = results or []
        self.calls: list[dict[str, object]] = []

    async def search(self, query: str, **kwargs: object) -> SimpleNamespace:
        self.calls.append({"query": query, **kwargs})
        return SimpleNamespace(results=self._results)


@pytest.mark.anyio
async def test_search_tool_returns_tagged_results_and_strips_www() -> None:
    settings = ResearcherExaSettings(exa_api_key="test-key", exa_max_results=2)
    client = _FakeExaClient(results=[_exa_result()])
    tool = build_search_tool(settings, client_factory=lambda settings: client)

    result = await tool.ainvoke(
        {"query": "AI coding agents", "type": "tool_call", "id": "call-1", "name": "search"}
    )
    payload = json.loads(result.content)

    assert len(payload["results"]) == 1
    entry = payload["results"][0]
    assert entry["tag"] == "call-1#0"
    assert entry["title"] == "Example Article"
    assert entry["url"] == "https://www.example.com/article"
    assert entry["publisher"] == "example.com"
    assert entry["excerpt"] == "Teams are adopting AI coding agents."


def test_parse_tool_message_reconstructs_source_results() -> None:
    content = json.dumps(
        {
            "results": [
                {
                    "tag": "call-1#0",
                    "title": "Example Article",
                    "url": "https://example.com/article",
                    "publisher": "example.com",
                    "published_at": "2026-01-01T00:00:00+00:00",
                    "retrieved_at": "2026-01-02T00:00:00+00:00",
                    "excerpt": "Teams are adopting AI coding agents.",
                }
            ]
        }
    )
    message = ToolMessage(content=content, tool_call_id="call-1", name="search")

    results = parse_tool_message(message)

    assert results == [
        ExaSourceResult(
            tag="call-1#0",
            title="Example Article",
            url="https://example.com/article",
            publisher="example.com",
            published_at=datetime(2026, 1, 1, tzinfo=UTC),
            retrieved_at=datetime(2026, 1, 2, tzinfo=UTC),
            excerpt="Teams are adopting AI coding agents.",
        )
    ]
```

- [ ] **Step 4: Run the tests to verify they fail**

Run: `uv run --package researcher pytest services/researcher/tests/test_tools.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'researcher.tools'`.

- [ ] **Step 5: Write `tools.py`**

```python
# services/researcher/src/researcher/tools.py
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated
from urllib.parse import urlparse

from exa_py import AsyncExa
from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolCallId, tool

from researcher.settings import ResearcherExaSettings


@dataclass(frozen=True, slots=True)
class ExaSourceResult:
    tag: str
    title: str
    url: str
    publisher: str
    published_at: datetime | None
    retrieved_at: datetime
    excerpt: str


def _default_client_factory(settings: ResearcherExaSettings) -> AsyncExa:
    return AsyncExa(api_key=settings.exa_api_key)


def _publisher_from_url(url: str) -> str:
    netloc = urlparse(url).netloc
    return netloc.removeprefix("www.") or "unknown"


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def build_search_tool(
    settings: ResearcherExaSettings,
    *,
    client_factory: Callable[[ResearcherExaSettings], AsyncExa] | None = None,
):
    """Build a fresh `search` tool bound to `settings`.

    A fresh tool is built per graph construction (per request) rather than
    shared as a module-level singleton, since its Exa client and settings
    must not leak across concurrent requests.
    """

    @tool("search")
    async def search(
        query: str,
        tool_call_id: Annotated[str, InjectedToolCallId],
    ) -> str:
        """Search the web for sources relevant to the research query."""
        client = (client_factory or _default_client_factory)(settings)
        response = await client.search(
            query,
            num_results=settings.exa_max_results,
            contents={"highlights": {"max_characters": settings.exa_highlight_max_characters}},
        )

        retrieved_at = datetime.now(UTC).isoformat()
        results: list[dict[str, object]] = []
        for position, result in enumerate(response.results[: settings.exa_max_results]):
            excerpt = "\n".join(result.highlights or []) or (result.text or "")[
                : settings.exa_highlight_max_characters
            ]
            if not excerpt:
                continue
            results.append(
                {
                    "tag": f"{tool_call_id}#{position}",
                    "title": result.title or result.url,
                    "url": result.url,
                    "publisher": _publisher_from_url(result.url),
                    "published_at": _parse_datetime(result.published_date),
                    "retrieved_at": retrieved_at,
                    "excerpt": excerpt,
                }
            )
        return json.dumps({"results": results}, default=str)

    return search


def parse_tool_message(message: ToolMessage) -> list[ExaSourceResult]:
    payload = json.loads(message.content)
    return [
        ExaSourceResult(
            tag=entry["tag"],
            title=entry["title"],
            url=entry["url"],
            publisher=entry["publisher"],
            published_at=_parse_datetime(entry.get("published_at")),
            retrieved_at=_parse_datetime(entry["retrieved_at"]) or datetime.now(UTC),
            excerpt=entry["excerpt"],
        )
        for entry in payload["results"]
    ]
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run --package researcher pytest services/researcher/tests/test_tools.py -v`
Expected: PASS (2 tests).

- [ ] **Step 7: Commit**

Skipped — no git repository.

---

## Task 3: Researcher's ReAct agent wiring

**Files:**
- Create: `services/researcher/src/researcher/middleware.py`
- Modify: `services/researcher/src/researcher/llm_schema.py`
- Modify: `services/researcher/src/researcher/prompts.py`
- Modify: `services/researcher/src/researcher/graph.py`
- Modify: `services/researcher/tests/test_graph.py`

**Interfaces:**
- Consumes: `researcher.tools.{build_search_tool, parse_tool_message, ExaSourceResult}` (Task 2), `researcher.settings.DemoSettings` (Task 2).
- Produces: `build_graph(settings: DemoSettings | None = None)` — unchanged signature and unchanged fixture-mode behavior. Live mode now runs a `create_agent` tool-calling loop instead of the fixed 3-node pipeline from Phase 4.

- [ ] **Step 1: Write the Groq/OpenAI fallback middleware**

```python
# services/researcher/src/researcher/middleware.py
from collections.abc import Awaitable, Callable

import openai
from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ContextT, ModelRequest, ModelResponse
from langchain_core.messages import AIMessage
from langchain_openai import ChatOpenAI

_NO_FALLBACK = (openai.AuthenticationError, openai.PermissionDeniedError, openai.BadRequestError)


class GroqOpenAIFallbackMiddleware(AgentMiddleware):
    """Retry with OpenAI only on transport-class Groq failures.

    Mirrors `ai_runtime.structured_llm`'s fallback rule: timeout, rate
    limit, connection error, and 5xx retry against `fallback_model`; auth
    and bad-request errors propagate immediately with no retry.
    """

    def __init__(self, fallback_model: ChatOpenAI) -> None:
        super().__init__()
        self._fallback_model = fallback_model

    def wrap_model_call(
        self,
        request: ModelRequest[ContextT],
        handler: Callable[[ModelRequest[ContextT]], ModelResponse],
    ) -> ModelResponse | AIMessage:
        try:
            return handler(request)
        except _NO_FALLBACK:
            raise
        except (
            openai.APITimeoutError,
            openai.RateLimitError,
            openai.APIConnectionError,
            openai.InternalServerError,
        ):
            return handler(request.override(model=self._fallback_model))

    async def awrap_model_call(
        self,
        request: ModelRequest[ContextT],
        handler: Callable[[ModelRequest[ContextT]], Awaitable[ModelResponse]],
    ) -> ModelResponse | AIMessage:
        try:
            return await handler(request)
        except _NO_FALLBACK:
            raise
        except (
            openai.APITimeoutError,
            openai.RateLimitError,
            openai.APIConnectionError,
            openai.InternalServerError,
        ):
            return await handler(request.override(model=self._fallback_model))
```

- [ ] **Step 2: Update `llm_schema.py` (`source_index` becomes a string tag)**

```python
# services/researcher/src/researcher/llm_schema.py
from pydantic import BaseModel, ConfigDict, Field


class LLMFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    claim: str = Field(min_length=1, max_length=1000)
    source_tag: str = Field(min_length=1, max_length=64)


class LLMFindingsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    findings: list[LLMFinding] = Field(min_length=1, max_length=6)
```

- [ ] **Step 3: Update `prompts.py` for the tool-calling agent**

```python
# services/researcher/src/researcher/prompts.py
SYSTEM_PROMPT = (
    "You are a research analyst producing findings for an executive brief. "
    "Use the `search` tool to find source excerpts — you may call it up to "
    "3 times to refine your query if the first results are not specific "
    "enough. Every finding must cite the exact `tag` string of the single "
    "search result excerpt that supports its claim. Never invent a fact, a "
    "source, or a URL that is not grounded in a tool result you received. "
    "Once you have enough grounded material, stop searching and produce "
    "your final findings."
)
```

- [ ] **Step 4: Write the failing live-mode tests (append to `test_graph.py`)**

Replace the two live-mode tests added in Phase 4 (`test_researcher_live_mode_grounds_findings_in_exa_sources`, `test_researcher_live_mode_rejects_unknown_source_index`) — they tested the old `exa_search`/`structured_llm` pipeline that no longer exists. Remove those two tests and their supporting fixtures (`_FAKE_SOURCES`, `_live_demo_settings`, and the now-unused imports `ai_runtime.exa_search`, `ai_runtime.structured_llm`, `ai_runtime.errors.AIRuntimeError`, `researcher.llm_schema.{LLMFinding, LLMFindingsResponse}`), then add:

```python
# services/researcher/tests/test_graph.py — replace the removed block with this
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, ToolCall

from researcher.settings import ResearcherExaSettings


def _live_demo_settings() -> DemoSettings:
    return DemoSettings(
        ai_runtime=AIRuntimeSettings(ai_mode=AIMode.LIVE, groq_api_key="test-key"),
        exa=ResearcherExaSettings(exa_api_key="test-exa-key"),
    )


def _fake_search_response(tag: str, excerpt: str) -> str:
    import json

    return json.dumps(
        {
            "results": [
                {
                    "tag": tag,
                    "title": "Live source",
                    "url": "https://example.com/live",
                    "publisher": "example.com",
                    "published_at": None,
                    "retrieved_at": "2026-01-02T00:00:00+00:00",
                    "excerpt": excerpt,
                }
            ]
        }
    )


@pytest.mark.anyio
async def test_researcher_live_mode_grounds_findings_in_tool_results(monkeypatch) -> None:
    from researcher import tools as tools_module

    async def fake_search_call(query, settings, *, client_factory=None):
        raise AssertionError("should not be called directly; tool is invoked by the agent")

    tool_call = AIMessage(
        content="",
        tool_calls=[ToolCall(name="search", args={"query": "AI coding agents"}, id="call-1")],
    )
    final = AIMessage(
        content="",
        response_metadata={
            "structured_response": {
                "findings": [
                    {
                        "title": "Adoption",
                        "claim": "Teams adopt AI coding agents.",
                        "source_tag": "call-1#0",
                    }
                ]
            }
        },
    )

    fake_model = GenericFakeChatModel(messages=iter([tool_call, final]))
    monkeypatch.setattr(tools_module, "_default_client_factory", lambda settings: None)

    async def fake_search_tool_search(query, **kwargs):
        from types import SimpleNamespace

        return SimpleNamespace(
            results=[
                SimpleNamespace(
                    url="https://example.com/live",
                    title="Live source",
                    published_date=None,
                    highlights=["Teams are adopting AI coding agents rapidly."],
                    text=None,
                )
            ]
        )

    class _FakeClient:
        search = staticmethod(fake_search_tool_search)

    monkeypatch.setattr(tools_module, "_default_client_factory", lambda settings: _FakeClient())
    monkeypatch.setattr("researcher.graph._build_chat_model", lambda settings: fake_model)

    request = ResearcherInput(request_id=uuid4(), trace_id="live-trace", query="AI coding agents")
    result = await build_graph(_live_demo_settings()).ainvoke(request.model_dump(mode="json"))
    response = ResearcherOutput.model_validate(result)

    assert response.status is ContractStatus.SUCCESS
    assert len(response.findings) == 1
    assert response.findings[0].claim == "Teams adopt AI coding agents."
    assert str(response.findings[0].source.url) == "https://example.com/live"


@pytest.mark.anyio
async def test_researcher_live_mode_rejects_unknown_source_tag(monkeypatch) -> None:
    from researcher import tools as tools_module

    tool_call = AIMessage(
        content="",
        tool_calls=[ToolCall(name="search", args={"query": "AI coding agents"}, id="call-1")],
    )
    final = AIMessage(
        content="",
        response_metadata={
            "structured_response": {
                "findings": [
                    {"title": "Bad", "claim": "Ungrounded claim.", "source_tag": "call-99#0"}
                ]
            }
        },
    )
    fake_model = GenericFakeChatModel(messages=iter([tool_call, final]))

    async def fake_search_tool_search(query, **kwargs):
        from types import SimpleNamespace

        return SimpleNamespace(
            results=[
                SimpleNamespace(
                    url="https://example.com/live",
                    title="Live source",
                    published_date=None,
                    highlights=["Some excerpt."],
                    text=None,
                )
            ]
        )

    class _FakeClient:
        search = staticmethod(fake_search_tool_search)

    monkeypatch.setattr(tools_module, "_default_client_factory", lambda settings: _FakeClient())
    monkeypatch.setattr("researcher.graph._build_chat_model", lambda settings: fake_model)

    request = ResearcherInput(request_id=uuid4(), trace_id="live-trace-2", query="AI coding agents")

    with pytest.raises(AIRuntimeError):
        await build_graph(_live_demo_settings()).ainvoke(request.model_dump(mode="json"))
```

Add `from ai_runtime.errors import AIRuntimeError` and `from ai_runtime.settings import AIMode, AIRuntimeSettings` to the top imports if not already present (they were added in Phase 4 and should already be there from the block being replaced — keep them).

- [ ] **Step 5: Run the tests to verify the new ones fail**

Run: `uv run --package researcher pytest services/researcher/tests/test_graph.py -v`
Expected: new tests FAIL (`_build_chat_model` doesn't exist yet on `researcher.graph`); the 2 original fixture-mode tests still PASS.

- [ ] **Step 6: Rewrite `graph.py`'s live path**

```python
# services/researcher/src/researcher/graph.py
import asyncio
import json

from ai_runtime.errors import AIRuntimeError
from ai_runtime.settings import AIMode, AIRuntimeSettings
from distributed_agent_contracts import (
    ContractStatus,
    Finding,
    ResearcherInput,
    ResearcherOutput,
    Source,
    copy_request_metadata,
)
from distributed_agent_contracts.researcher import ResearcherRemoteState
from langchain.agents import create_agent
from langchain.agents.middleware import ToolCallLimitMiddleware
from langchain_core.messages import ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph

from researcher.fixtures import build_findings
from researcher.llm_schema import LLMFindingsResponse
from researcher.middleware import GroqOpenAIFallbackMiddleware
from researcher.prompts import SYSTEM_PROMPT
from researcher.settings import DemoSettings, FailureMode
from researcher.tools import build_search_tool, parse_tool_message

_GROQ_BASE_URL = "https://api.groq.com/openai/v1"


def _build_chat_model(settings: AIRuntimeSettings) -> ChatOpenAI:
    return ChatOpenAI(
        model_name=settings.groq_model,
        openai_api_key=settings.groq_api_key,
        openai_api_base=_GROQ_BASE_URL,
        request_timeout=settings.llm_timeout_seconds,
    )


def _build_fallback_model(settings: AIRuntimeSettings) -> ChatOpenAI:
    return ChatOpenAI(
        model_name=settings.openai_model,
        openai_api_key=settings.openai_api_key,
        request_timeout=settings.llm_timeout_seconds,
    )


def _build_fixture_graph(runtime_settings: DemoSettings):
    async def collect_findings(state: ResearcherRemoteState) -> dict[str, object]:
        request = ResearcherInput.model_validate(state)

        if runtime_settings.failure_mode is FailureMode.TIMEOUT:
            await asyncio.sleep(runtime_settings.delay_seconds)
        if runtime_settings.failure_mode is FailureMode.TRANSIENT_ERROR:
            raise RuntimeError("simulated transient Researcher failure")
        if runtime_settings.failure_mode is FailureMode.INVALID_RESPONSE:
            return {"status": "invalid", "findings": "not-a-list"}

        response = ResearcherOutput(
            **copy_request_metadata(request),
            status=ContractStatus.SUCCESS,
            findings=build_findings(request.query),
        )
        return response.model_dump(mode="json")

    builder = StateGraph(
        ResearcherRemoteState,
        input_schema=ResearcherInput,
        output_schema=ResearcherOutput,
    )
    builder.add_node("collect_findings", collect_findings)
    builder.add_edge(START, "collect_findings")
    builder.add_edge("collect_findings", END)
    return builder.compile()


_RESEARCHER_INPUT_FIELDS = set(ResearcherInput.model_fields)


def _extract_request(state: dict[str, object]) -> ResearcherInput:
    return ResearcherInput.model_validate(
        {key: value for key, value in state.items() if key in _RESEARCHER_INPUT_FIELDS}
    )


def _build_live_graph(runtime_settings: DemoSettings):
    ai_settings = runtime_settings.ai_runtime

    async def run_react_agent(state: ResearcherRemoteState) -> dict[str, object]:
        request = _extract_request(state)

        search_tool = build_search_tool(runtime_settings.exa)
        agent = create_agent(
            model=_build_chat_model(ai_settings),
            tools=[search_tool],
            system_prompt=SYSTEM_PROMPT,
            response_format=LLMFindingsResponse,
            middleware=[
                ToolCallLimitMiddleware(tool_name="search", run_limit=3, exit_behavior="end"),
                GroqOpenAIFallbackMiddleware(_build_fallback_model(ai_settings)),
            ],
        )

        final_state = await agent.ainvoke(
            {"messages": [{"role": "user", "content": request.query}]}
        )

        sources_by_tag = {}
        for message in final_state["messages"]:
            if isinstance(message, ToolMessage) and message.name == "search":
                for result in parse_tool_message(message):
                    sources_by_tag[result.tag] = result

        structured = final_state["structured_response"]
        findings: list[Finding] = []
        for raw_finding in structured.findings:
            matched = sources_by_tag.get(raw_finding.source_tag)
            if matched is None:
                raise AIRuntimeError(
                    f"LLM finding referenced unknown source_tag {raw_finding.source_tag!r}"
                )
            findings.append(
                Finding(
                    title=raw_finding.title,
                    claim=raw_finding.claim,
                    source=Source(
                        title=matched.title,
                        url=matched.url,
                        publisher=matched.publisher,
                        published_at=matched.published_at,
                        retrieved_at=matched.retrieved_at,
                    ),
                )
            )

        response = ResearcherOutput(
            **copy_request_metadata(request),
            status=ContractStatus.SUCCESS,
            findings=findings,
        )
        return response.model_dump(mode="json")

    builder = StateGraph(
        ResearcherRemoteState,
        input_schema=ResearcherInput,
        output_schema=ResearcherOutput,
    )
    builder.add_node("run_react_agent", run_react_agent)
    builder.add_edge(START, "run_react_agent")
    builder.add_edge("run_react_agent", END)
    return builder.compile()


def build_graph(settings: DemoSettings | None = None):
    runtime_settings = settings or DemoSettings.from_environment()
    if runtime_settings.ai_runtime.ai_mode is AIMode.LIVE:
        return _build_live_graph(runtime_settings)
    return _build_fixture_graph(runtime_settings)


graph = build_graph()
```

- [ ] **Step 7: Run the tests; adjust `structured_response` access if the installed `create_agent` shapes it differently**

Run: `uv run --package researcher pytest services/researcher/tests/test_graph.py -v`

If this fails specifically on how `final_state["structured_response"]` is typed (e.g. it comes back as a plain `dict` instead of an `LLMFindingsResponse` instance), adjust `run_react_agent` to handle both — e.g. `structured = final_state["structured_response"]; findings_data = structured.findings if hasattr(structured, "findings") else structured["findings"]` — this is verifying exact `create_agent` output shape against the installed `langchain==1.3.18`, not a design change.

Expected after any needed adjustment: PASS (4 tests: 2 original fixture-mode, 2 new live-mode).

- [ ] **Step 8: Commit**

Skipped — no git repository.

---

## Task 4: Market Agent's local search tool

**Files:**
- Modify: `services/market-agent/pyproject.toml` (already has `exa-py` and `google-adk[extensions]` added during design verification — confirm)
- Modify: `services/market-agent/src/market_agent/settings.py`
- Create: `services/market-agent/src/market_agent/tools.py`
- Test: `services/market-agent/tests/test_tools.py`

**Interfaces:**
- Produces: `market_agent.tools.search(query: str, tool_context: ToolContext) -> dict` — a plain function wrapped by `FunctionTool` in Task 5, calling Exa directly, returning `{"results": [{"tag": "<function_call_id>#<position>", ...}]}`. `market_agent.tools.ExaSourceResult` and `market_agent.tools.parse_function_response(function_call_id: str, response_payload: dict) -> list[ExaSourceResult]`.
- Consumes: `market_agent.settings.MarketExaSettings` (new).

- [ ] **Step 1: Confirm dependencies are present**

Run: `grep -n "exa-py\|google-adk" services/market-agent/pyproject.toml`
Expected: `"google-adk[extensions]>=1.0.0"` and `"exa-py>=1.9.0"`.

- [ ] **Step 2: Add local Exa settings to `market_agent/settings.py`**

```python
# services/market-agent/src/market_agent/settings.py
import asyncio
import os
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from ai_runtime.settings import AIRuntimeSettings
from dotenv import load_dotenv

# Each service owns its own .env (services/market-agent/.env) rather than
# sharing one repo-root file, matching independent deployability.
load_dotenv(Path(__file__).resolve().parents[2] / ".env")


class FailureMode(StrEnum):
    NONE = "none"
    TIMEOUT = "timeout"
    TRANSIENT_ERROR = "transient_error"
    INVALID_RESPONSE = "invalid_response"


@dataclass(frozen=True)
class MarketExaSettings:
    exa_api_key: str | None = None
    exa_max_results: int = 4
    exa_highlight_max_characters: int = 1200

    @classmethod
    def from_environment(cls) -> "MarketExaSettings":
        return cls(
            exa_api_key=os.getenv("EXA_API_KEY") or None,
            exa_max_results=max(1, int(os.getenv("EXA_MAX_RESULTS", "4"))),
            exa_highlight_max_characters=max(
                200, int(os.getenv("EXA_HIGHLIGHT_MAX_CHARACTERS", "1200"))
            ),
        )


@dataclass(frozen=True)
class DemoSettings:
    failure_mode: FailureMode = FailureMode.NONE
    failure_delay_ms: int = 1_500
    ai_runtime: AIRuntimeSettings = field(default_factory=AIRuntimeSettings)
    exa: MarketExaSettings = field(default_factory=MarketExaSettings)

    @classmethod
    def from_environment(cls) -> "DemoSettings":
        return cls(
            failure_mode=FailureMode(os.getenv("DEMO_FAILURE_MODE", FailureMode.NONE)),
            failure_delay_ms=int(os.getenv("DEMO_FAILURE_DELAY_MS", "1500")),
            ai_runtime=AIRuntimeSettings.from_environment(),
            exa=MarketExaSettings.from_environment(),
        )

    async def apply_delay(self) -> None:
        if self.failure_mode is FailureMode.TIMEOUT:
            await asyncio.sleep(self.failure_delay_ms / 1_000)
```

- [ ] **Step 3: Write the failing test for `tools.py`**

```python
# services/market-agent/tests/test_tools.py
from types import SimpleNamespace

import pytest

from market_agent.settings import MarketExaSettings
from market_agent.tools import ExaSourceResult, build_search_function, parse_function_response


def _exa_result(**overrides: object) -> SimpleNamespace:
    defaults: dict[str, object] = {
        "url": "https://www.example.com/market",
        "title": "Example Market Source",
        "published_date": None,
        "highlights": ["Buyers prioritize workflow integration."],
        "text": None,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


class _FakeExaClient:
    def __init__(self, *, results: list[SimpleNamespace] | None = None) -> None:
        self._results = results or []
        self.calls: list[dict[str, object]] = []

    async def search(self, query: str, **kwargs: object) -> SimpleNamespace:
        self.calls.append({"query": query, **kwargs})
        return SimpleNamespace(results=self._results)


class _FakeToolContext:
    def __init__(self, function_call_id: str) -> None:
        self.function_call_id = function_call_id


@pytest.mark.anyio
async def test_search_function_returns_tagged_results() -> None:
    settings = MarketExaSettings(exa_api_key="test-key", exa_max_results=2)
    client = _FakeExaClient(results=[_exa_result()])
    search = build_search_function(settings, client_factory=lambda settings: client)

    result = await search(query="AI coding assistants", tool_context=_FakeToolContext("fc-1"))

    assert len(result["results"]) == 1
    entry = result["results"][0]
    assert entry["tag"] == "fc-1#0"
    assert entry["publisher"] == "example.com"


def test_parse_function_response_reconstructs_source_results() -> None:
    payload = {
        "results": [
            {
                "tag": "fc-1#0",
                "title": "Example Market Source",
                "url": "https://example.com/market",
                "publisher": "example.com",
                "published_at": None,
                "retrieved_at": "2026-01-02T00:00:00+00:00",
                "excerpt": "Buyers prioritize workflow integration.",
            }
        ]
    }

    results = parse_function_response(payload)

    assert results == [
        ExaSourceResult(
            tag="fc-1#0",
            title="Example Market Source",
            url="https://example.com/market",
            publisher="example.com",
            published_at=None,
            retrieved_at=results[0].retrieved_at,
            excerpt="Buyers prioritize workflow integration.",
        )
    ]
```

- [ ] **Step 4: Run the tests to verify they fail**

Run: `uv run --package market-agent pytest services/market-agent/tests/test_tools.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'market_agent.tools'`.

- [ ] **Step 5: Write `tools.py`**

```python
# services/market-agent/src/market_agent/tools.py
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlparse

from exa_py import AsyncExa
from google.adk.tools import ToolContext

from market_agent.settings import MarketExaSettings


@dataclass(frozen=True, slots=True)
class ExaSourceResult:
    tag: str
    title: str
    url: str
    publisher: str
    published_at: datetime | None
    retrieved_at: datetime
    excerpt: str


def _default_client_factory(settings: MarketExaSettings) -> AsyncExa:
    return AsyncExa(api_key=settings.exa_api_key)


def _publisher_from_url(url: str) -> str:
    netloc = urlparse(url).netloc
    return netloc.removeprefix("www.") or "unknown"


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def build_search_function(
    settings: MarketExaSettings,
    *,
    client_factory: Callable[[MarketExaSettings], AsyncExa] | None = None,
):
    """Build a fresh `search` function bound to `settings`.

    A fresh function is built per agent construction (per request) rather
    than shared as a module-level singleton, matching Researcher's tool.
    """

    async def search(query: str, tool_context: ToolContext) -> dict[str, object]:
        """Search the web for sources relevant to the market query.

        Args:
            query: The search query.
        """
        client = (client_factory or _default_client_factory)(settings)
        response = await client.search(
            query,
            num_results=settings.exa_max_results,
            contents={"highlights": {"max_characters": settings.exa_highlight_max_characters}},
        )

        retrieved_at = datetime.now(UTC).isoformat()
        results: list[dict[str, object]] = []
        for position, result in enumerate(response.results[: settings.exa_max_results]):
            excerpt = "\n".join(result.highlights or []) or (result.text or "")[
                : settings.exa_highlight_max_characters
            ]
            if not excerpt:
                continue
            results.append(
                {
                    "tag": f"{tool_context.function_call_id}#{position}",
                    "title": result.title or result.url,
                    "url": result.url,
                    "publisher": _publisher_from_url(result.url),
                    "published_at": result.published_date,
                    "retrieved_at": retrieved_at,
                    "excerpt": excerpt,
                }
            )
        return {"results": results}

    return search


def parse_function_response(payload: dict[str, object]) -> list[ExaSourceResult]:
    return [
        ExaSourceResult(
            tag=entry["tag"],
            title=entry["title"],
            url=entry["url"],
            publisher=entry["publisher"],
            published_at=_parse_datetime(entry.get("published_at")),
            retrieved_at=_parse_datetime(entry["retrieved_at"]) or datetime.now(UTC),
            excerpt=entry["excerpt"],
        )
        for entry in payload["results"]
    ]
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run --package market-agent pytest services/market-agent/tests/test_tools.py -v`
Expected: PASS (2 tests).

- [ ] **Step 7: Commit**

Skipped — no git repository.

---

## Task 5: Market Agent's ReAct agent wiring

**Files:**
- Modify: `services/market-agent/src/market_agent/llm_schema.py`
- Modify: `services/market-agent/src/market_agent/prompts.py`
- Modify: `services/market-agent/src/market_agent/agent.py`
- Modify: `services/market-agent/src/market_agent/runner.py`
- Modify: `services/market-agent/tests/test_server.py`

**Interfaces:**
- Consumes: `market_agent.tools.{build_search_function, parse_function_response, ExaSourceResult}` (Task 4).
- Produces: `MarketAgentRunner(settings)` — unchanged constructor signature; `LiveMarketAgent`'s internals replaced with an ADK `LlmAgent` built per-request. gRPC-facing behavior (`MarketAgentService.AnalyzeMarket`) unchanged.

- [ ] **Step 1: Update `llm_schema.py` (`source_index` becomes a string tag)**

```python
# services/market-agent/src/market_agent/llm_schema.py
from pydantic import BaseModel, ConfigDict, Field


class LLMSignal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic: str = Field(min_length=1, max_length=200)
    observation: str = Field(min_length=1, max_length=1000)
    source_tag: str = Field(min_length=1, max_length=64)


class LLMMarketResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    signals: list[LLMSignal] = Field(min_length=1, max_length=6)
    competitors: list[str] = Field(min_length=1, max_length=10)
```

- [ ] **Step 2: Update `prompts.py` for the tool-calling agent**

```python
# services/market-agent/src/market_agent/prompts.py
SYSTEM_PROMPT = (
    "You are a market analyst producing signals for an executive brief. "
    "Use the `search` tool to find source excerpts — you may call it up to "
    "3 times to refine your query if the first results are not specific "
    "enough. Every signal must cite the exact `tag` string of the single "
    "search result excerpt that supports its observation. List named "
    "competitors only if they are mentioned in a tool result you received. "
    "Never invent a fact, a source, a URL, or a competitor that is not "
    "grounded in a tool result. Once you have enough grounded material, "
    "stop searching and produce your final signals."
)
```

- [ ] **Step 3: Write the failing live-mode test (append to `test_server.py`)**

Replace the Phase 4 live-mode test (`test_analyze_market_live_mode_grounds_signals_in_exa_sources`, and its now-unused `ai_runtime.exa_search`/`ai_runtime.structured_llm` imports) with:

```python
# services/market-agent/tests/test_server.py — replace the removed test with this
from market_agent.llm_schema import LLMMarketResponse


def _live_settings() -> DemoSettings:
    from market_agent.settings import MarketExaSettings

    return DemoSettings(
        ai_runtime=AIRuntimeSettings(ai_mode=AIMode.LIVE, groq_api_key="test-key"),
        exa=MarketExaSettings(exa_api_key="test-exa-key"),
    )


@pytest.mark.anyio
async def test_analyze_market_live_mode_grounds_signals_in_tool_results(monkeypatch) -> None:
    import market_agent.tools as tools_module

    async def fake_search(query: str, tool_context) -> dict[str, object]:
        return {
            "results": [
                {
                    "tag": f"{tool_context.function_call_id}#0",
                    "title": "Live market source",
                    "url": "https://example.com/market",
                    "publisher": "example.com",
                    "published_at": None,
                    "retrieved_at": "2026-01-02T00:00:00+00:00",
                    "excerpt": "Buyers prioritize workflow integration.",
                }
            ]
        }

    monkeypatch.setattr(
        tools_module, "build_search_function", lambda settings, **kwargs: fake_search
    )

    class _FakeRunner:
        def __init__(self, *, agent, **kwargs) -> None:
            self._agent = agent

        async def run_async(self, *, user_id, session_id, new_message):
            from google.adk.events import Event

            yield Event(
                author=self._agent.name,
                output={
                    "market_signals": [
                        {
                            "topic": "Integration",
                            "observation": "Buyers want integration.",
                            "source": {
                                "title": "Live market source",
                                "url": "https://example.com/market",
                                "publisher": "example.com",
                                "published_at_unix_ms": 0,
                                "retrieved_at_unix_ms": 0,
                            },
                        }
                    ],
                    "competitors": ["Example Competitor"],
                },
            )

    import market_agent.runner as runner_module

    monkeypatch.setattr(runner_module, "Runner", _FakeRunner)

    server, port = await create_server("127.0.0.1:0", _live_settings())
    await server.start()
    try:
        async with grpc.aio.insecure_channel(f"127.0.0.1:{port}") as channel:
            response = await market_pb2_grpc.MarketAgentStub(channel).AnalyzeMarket(valid_request())
    finally:
        await server.stop(grace=None)

    assert response.status == market_pb2.RESPONSE_STATUS_SUCCESS
    assert len(response.market_signals) == 1
    assert response.market_signals[0].source.url == "https://example.com/market"
    assert response.competitors == ["Example Competitor"]
```

Note: this test fakes at the `Runner` boundary rather than the ADK model boundary — the grounding/tag-validation logic that Phase 4 tested end-to-end now lives inside `LiveMarketAgent`'s construction (built and validated in Step 4 below), which is harder to unit test without a real or heavily-mocked `LlmAgent` model call. Verifying the gRPC-level contract (status, source URL, competitors) here is the pragmatic test boundary; the grounding/tag logic itself is covered by Task 4's `parse_function_response` tests plus manual verification against a real Groq call once `.env` keys are filled in.

- [ ] **Step 4: Run the tests to verify the new one fails**

Run: `uv run --package market-agent pytest services/market-agent/tests/test_server.py -v`
Expected: the new test FAILS (old live-mode code path still references the deleted `ai_runtime.exa_search`/`structured_llm`); the 2 original tests still PASS.

- [ ] **Step 5: Rewrite `agent.py`**

```python
# services/market-agent/src/market_agent/agent.py
from collections.abc import AsyncGenerator
from datetime import datetime

from ai_runtime.settings import AIRuntimeSettings
from google.adk.agents import BaseAgent, InvocationContext, LlmAgent
from google.adk.events import Event
from google.adk.models.lite_llm import LiteLlm
from google.adk.tools import FunctionTool

from market_agent.fixtures import market_fixture
from market_agent.llm_schema import LLMMarketResponse
from market_agent.prompts import SYSTEM_PROMPT
from market_agent.settings import MarketExaSettings
from market_agent.tools import build_search_function


def _to_unix_ms(value: datetime | str | None) -> int:
    if value is None:
        return 0
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    return int(value.timestamp() * 1000)


class DeterministicMarketAgent(BaseAgent):
    """Google ADK agent whose output is stable and requires no model credentials."""

    async def _run_async_impl(
        self,
        ctx: InvocationContext,
    ) -> AsyncGenerator[Event, None]:
        parts = ctx.user_content.parts if ctx.user_content else []
        query = " ".join(part.text for part in parts if part.text).strip()
        fixture = market_fixture(query)
        yield Event(
            author=self.name,
            output={
                "market_signals": fixture.market_signals,
                "competitors": fixture.competitors,
            },
        )


def _to_market_output(result: dict) -> dict[str, object]:
    from market_agent.tools import parse_function_response

    signals: list[dict[str, object]] = []
    for signal in result["signals"]:
        matched = next(
            (
                source
                for source in result["_sources_by_tag"].values()
                if source.tag == signal["source_tag"]
            ),
            None,
        )
        if matched is None:
            raise ValueError(f"LLM signal referenced unknown source_tag {signal['source_tag']!r}")
        signals.append(
            {
                "topic": signal["topic"],
                "observation": signal["observation"],
                "source": {
                    "title": matched.title,
                    "url": matched.url,
                    "publisher": matched.publisher,
                    "published_at_unix_ms": _to_unix_ms(matched.published_at),
                    "retrieved_at_unix_ms": _to_unix_ms(matched.retrieved_at),
                },
            }
        )
    return {"market_signals": signals, "competitors": result["competitors"]}


def build_live_agent(name: str, ai_settings: AIRuntimeSettings, exa_settings: MarketExaSettings) -> LlmAgent:
    search = build_search_function(exa_settings)
    return LlmAgent(
        name=name,
        model=LiteLlm(model=f"groq/{ai_settings.groq_model}"),
        instruction=SYSTEM_PROMPT,
        tools=[FunctionTool(search)],
        output_schema=LLMMarketResponse,
    )


def build_live_fallback_agent(
    name: str, ai_settings: AIRuntimeSettings, exa_settings: MarketExaSettings
) -> LlmAgent:
    search = build_search_function(exa_settings)
    return LlmAgent(
        name=name,
        model=LiteLlm(model=f"openai/{ai_settings.openai_model}"),
        instruction=SYSTEM_PROMPT,
        tools=[FunctionTool(search)],
        output_schema=LLMMarketResponse,
    )
```

- [ ] **Step 6: Rewrite `runner.py`**

```python
# services/market-agent/src/market_agent/runner.py
from dataclasses import dataclass

import litellm
from ai_runtime.settings import AIMode
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from market_agent.agent import (
    DeterministicMarketAgent,
    build_live_agent,
    build_live_fallback_agent,
)
from market_agent.settings import DemoSettings

_NO_FALLBACK = (
    litellm.exceptions.AuthenticationError,
    litellm.exceptions.PermissionDeniedError,
    litellm.exceptions.BadRequestError,
)
_FALLBACK_WORTHY = (
    litellm.exceptions.Timeout,
    litellm.exceptions.RateLimitError,
    litellm.exceptions.APIConnectionError,
    litellm.exceptions.InternalServerError,
)


@dataclass(frozen=True)
class MarketResult:
    market_signals: list[dict[str, object]]
    competitors: list[str]


async def _run_agent(agent, query: str, request_id: str) -> dict[str, object] | None:
    runner = Runner(
        agent=agent,
        app_name="market-agent",
        session_service=InMemorySessionService(),
        auto_create_session=True,
    )
    content = types.Content(role="user", parts=[types.Part(text=query)])
    output: dict[str, object] | None = None
    async for event in runner.run_async(
        user_id="orchestrator",
        session_id=request_id,
        new_message=content,
    ):
        if isinstance(event.output, dict):
            output = event.output
    return output


class MarketAgentRunner:
    def __init__(self, settings: DemoSettings | None = None) -> None:
        self._settings = settings or DemoSettings.from_environment()

    async def analyze(self, query: str, request_id: str) -> MarketResult:
        settings = self._settings

        if settings.ai_runtime.ai_mode is not AIMode.LIVE:
            output = await _run_agent(
                DeterministicMarketAgent(name="market_researcher"), query, request_id
            )
        else:
            primary = build_live_agent("market_researcher", settings.ai_runtime, settings.exa)
            try:
                output = await _run_agent(primary, query, request_id)
            except _NO_FALLBACK:
                raise
            except _FALLBACK_WORTHY:
                fallback = build_live_fallback_agent(
                    "market_researcher", settings.ai_runtime, settings.exa
                )
                output = await _run_agent(fallback, query, request_id)

        if output is None:
            raise RuntimeError("market agent completed without an output event")

        return MarketResult(
            market_signals=list(output["market_signals"]),
            competitors=list(output["competitors"]),
        )
```

Note: `build_live_agent`'s `LlmAgent` produces `output_schema`-validated JSON as its final text response, not the `{"market_signals": [...], "competitors": [...]}` shape `MarketResult` expects directly — ADK surfaces the structured output as the agent's final message content (JSON text) and/or `state_delta[output_key]`, not as `event.output` the way `DeterministicMarketAgent`'s hand-built `Event(output=...)` does. **Before this step is considered done**, run a quick check of how the installed ADK version surfaces `output_schema` results (`event.content`, `ctx.session.state`, or similar) and adjust `_run_agent`/`_to_market_output` (Task 5 Step 5) accordingly — this is verifying exact ADK output-delivery shape against the installed version, not a design change. Wire `_to_market_output` (already written in Step 5) into this final extraction once that shape is confirmed, and update `server.py`'s consumption in Step 8 if needed.

- [ ] **Step 7: Update `server.py` if the settings/runner threading changed**

`services/market-agent/src/market_agent/server.py`'s `MarketAgentService.__init__` already does:
```python
self._settings = settings or DemoSettings.from_environment()
self._runner = runner or MarketAgentRunner(settings=self._settings)
```
No change needed here — confirm this still matches by reading the file.

- [ ] **Step 8: Run the tests, adjusting the output-extraction shape found in Step 6**

Run: `uv run --package market-agent pytest services/market-agent/tests/test_server.py -v`
Expected: PASS (3 tests: 2 original, 1 new live-mode).

- [ ] **Step 9: Commit**

Skipped — no git repository.

---

## Task 6: Full verification pass

**Files:** none (verification only).

- [ ] **Step 1: Sync the whole workspace fresh**

Run: `uv sync --all-packages --all-groups`
Expected: completes without error.

- [ ] **Step 2: Lint**

Run: `uv run ruff check .`
Expected: no issues (fix import order / unused imports from the deleted `exa_search` module and changed `llm_schema` fields if any remain).

- [ ] **Step 3: Full test suite**

Run: `uv run --all-packages pytest`
Expected: all tests pass (fixture-mode tests for every service unchanged; Researcher gains 2 tools tests + keeps 4 graph tests; Market Agent gains 2 tools tests + keeps 3 server tests; ai-runtime loses the 5 exa_search tests, keeps 4 settings + 13 structured_llm tests). `tests/integration/*` still skip by default.

- [ ] **Step 4: Confirm fixture mode still boots with zero keys**

Run: `docker compose up --build -d && sleep 5 && curl -sf http://localhost:8000/ready && docker compose down`
Expected: stack builds and is healthy — `AI_MODE=fixture` in every `.env` means none of this task's changes are exercised by default, matching Phase 4's zero-config guarantee.

- [ ] **Step 5: Commit**

Skipped — no git repository.
