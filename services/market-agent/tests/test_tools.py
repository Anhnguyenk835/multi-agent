from types import SimpleNamespace

import pytest
from market_agent.settings import MarketExaSettings
from market_agent.tools import ExaSourceResult, build_search_function, parse_function_response


def _exa_result(**overrides: object) -> SimpleNamespace:
    defaults: dict[str, object] = {
        "url": "https://www.example.com/market",
        "title": "Example Market Source",
        "published_date": None,
        "text": "Buyers prioritize workflow integration.",
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
        self.state: dict[str, object] = {}


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


@pytest.mark.anyio
async def test_search_function_stops_calling_exa_after_budget_exhausted() -> None:
    settings = MarketExaSettings(exa_api_key="test-key", exa_max_results=2)
    client = _FakeExaClient(results=[_exa_result()])
    search = build_search_function(settings, client_factory=lambda settings: client)
    tool_context = _FakeToolContext("fc-1")

    for _ in range(3):
        result = await search(query="AI coding assistants", tool_context=tool_context)
        assert result["results"]

    result = await search(query="AI coding assistants", tool_context=tool_context)

    assert result["results"] == []
    assert "error" in result
    assert len(client.calls) == 3


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
                "content": "Buyers prioritize workflow integration.",
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
            content="Buyers prioritize workflow integration.",
        )
    ]
