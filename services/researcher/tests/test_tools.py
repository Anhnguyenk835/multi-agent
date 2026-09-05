import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from langchain_core.messages import ToolMessage
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from researcher import telemetry
from researcher.settings import ResearcherExaSettings
from researcher.tools import ExaSourceResult, build_search_tool, parse_tool_message


def _exa_result(**overrides: object) -> SimpleNamespace:
    defaults: dict[str, object] = {
        "url": "https://www.example.com/article",
        "title": "Example Article",
        "published_date": "2026-01-01T00:00:00.000Z",
        "text": "Teams are adopting AI coding agents.",
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
        {
            "args": {"query": "AI coding agents"},
            "type": "tool_call",
            "id": "call-1",
            "name": "search",
        }
    )
    payload = json.loads(result.content)

    assert len(payload["results"]) == 1
    entry = payload["results"][0]
    assert entry["tag"] == "call-1#0"
    assert entry["title"] == "Example Article"
    assert entry["url"] == "https://www.example.com/article"
    assert entry["publisher"] == "example.com"
    assert entry["content"] == "Teams are adopting AI coding agents."


@pytest.mark.anyio
async def test_search_tool_has_logical_and_external_search_spans(monkeypatch) -> None:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(telemetry, "_tracer", provider.get_tracer("test"))
    settings = ResearcherExaSettings(exa_api_key="test-key", exa_max_results=2)
    tool = build_search_tool(
        settings,
        client_factory=lambda settings: _FakeExaClient(results=[_exa_result()]),
    )

    with telemetry.operation_span("researcher.run_react_agent"):
        await tool.ainvoke(
            {
                "args": {"query": "AI coding agents"},
                "type": "tool_call",
                "id": "call-1",
                "name": "search",
            }
        )

    spans = {span.name: span for span in exporter.get_finished_spans()}
    logical = spans["search"]
    external = spans["tool.search"]
    assert json.loads(logical.attributes["langfuse.observation.input"]) == {
        "query": "AI coding agents"
    }
    assert json.loads(logical.attributes["langfuse.observation.output"]) == {"result_count": 1}
    assert external.parent.span_id == logical.context.span_id


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
                    "content": "Teams are adopting AI coding agents.",
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
            content="Teams are adopting AI coding agents.",
        )
    ]
