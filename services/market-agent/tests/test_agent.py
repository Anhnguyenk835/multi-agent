from google.adk.events import Event
from google.adk.tools import FunctionTool
from google.genai import types
from market_agent.agent import (
    SUBMIT_TOOL_NAME,
    build_market_output,
    collect_search_sources,
    extract_market_output,
    submit_market_analysis,
)
from market_agent.llm_schema import LLMMarketResponse, LLMSignal
from market_agent.tools import ExaSourceResult


def test_model_ids_are_canonicalized_from_environment(monkeypatch) -> None:
    from market_agent.settings import AIMode, MarketAISettings

    monkeypatch.setenv("AI_MODE", AIMode.LIVE.value)
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setenv("OPENAI_MODEL", "GPT\u20114o\u2011mini")

    settings = MarketAISettings.from_environment()

    assert settings.openai_model == "gpt-4o-mini"


def test_submit_tool_registered_name_matches_submit_tool_name_constant() -> None:
    """Regression test: `extract_market_output` matches function calls by
    name against `SUBMIT_TOOL_NAME`, but ADK derives a `FunctionTool`'s
    registered name from the wrapped function's own `__name__` — if those
    two ever drift apart, the model's real tool call is silently never
    recognized as the final answer."""
    assert FunctionTool(submit_market_analysis).name == SUBMIT_TOOL_NAME


def _function_call_event(name: str, call_id: str, args: dict[str, object]) -> Event:
    return Event(
        author="market_researcher",
        content=types.Content(
            role="model",
            parts=[types.Part(function_call=types.FunctionCall(id=call_id, name=name, args=args))],
        ),
    )


def _function_response_event(name: str, call_id: str, response: dict[str, object]) -> Event:
    return Event(
        author="market_researcher",
        content=types.Content(
            role="user",
            parts=[
                types.Part(
                    function_response=types.FunctionResponse(
                        id=call_id, name=name, response=response
                    )
                )
            ],
        ),
    )


def test_collect_search_sources_reads_function_responses_by_tag() -> None:
    response_payload = {
        "results": [
            {
                "tag": "fc-1#0",
                "title": "Live market source",
                "url": "https://example.com/market",
                "publisher": "example.com",
                "published_at": None,
                "retrieved_at": "2026-01-02T00:00:00+00:00",
                "content": "Buyers prioritize workflow integration.",
            }
        ]
    }
    events = [
        _function_call_event("search", "fc-1", {"query": "AI coding assistants"}),
        _function_response_event("search", "fc-1", response_payload),
    ]

    sources = collect_search_sources(events)

    assert sources == {
        "fc-1#0": ExaSourceResult(
            tag="fc-1#0",
            title="Live market source",
            url="https://example.com/market",
            publisher="example.com",
            published_at=None,
            retrieved_at=sources["fc-1#0"].retrieved_at,
            content="Buyers prioritize workflow integration.",
        )
    }


def test_build_market_output_grounds_signal_in_matched_source() -> None:
    source = ExaSourceResult(
        tag="fc-1#0",
        title="Live market source",
        url="https://example.com/market",
        publisher="example.com",
        published_at=None,
        retrieved_at=None,
        content="Buyers prioritize workflow integration.",
    )
    structured = LLMMarketResponse(
        signals=[
            LLMSignal(topic="Integration", observation="Buyers want integration.", source_tag="fc-1#0")
        ],
        competitors=["Example Competitor"],
    )

    output = build_market_output(structured, {"fc-1#0": source})

    assert output["competitors"] == ["Example Competitor"]
    assert output["market_signals"][0]["source"]["url"] == "https://example.com/market"


def test_build_market_output_rejects_unknown_source_tag() -> None:
    structured = LLMMarketResponse(
        signals=[LLMSignal(topic="Bad", observation="Ungrounded.", source_tag="fc-99#0")],
        competitors=["Example Competitor"],
    )

    try:
        build_market_output(structured, {})
    except ValueError as exc:
        assert "fc-99#0" in str(exc)
    else:
        raise AssertionError("expected ValueError for unknown source_tag")


def test_extract_market_output_end_to_end() -> None:
    response_payload = {
        "results": [
            {
                "tag": "fc-1#0",
                "title": "Live market source",
                "url": "https://example.com/market",
                "publisher": "example.com",
                "published_at": None,
                "retrieved_at": "2026-01-02T00:00:00+00:00",
                "content": "Buyers prioritize workflow integration.",
            }
        ]
    }
    events = [
        _function_call_event("search", "fc-1", {"query": "AI coding assistants"}),
        _function_response_event("search", "fc-1", response_payload),
        _function_call_event(
            SUBMIT_TOOL_NAME,
            "fc-2",
            {
                "response": {
                    "signals": [
                        {
                            "topic": "Integration",
                            "observation": "Buyers want integration.",
                            "source_tag": "fc-1#0",
                        }
                    ],
                    "competitors": ["Example Competitor"],
                }
            },
        ),
    ]

    output = extract_market_output(events)

    assert output is not None
    assert output["competitors"] == ["Example Competitor"]
    assert len(output["market_signals"]) == 1
    assert output["market_signals"][0]["source"]["url"] == "https://example.com/market"


def test_extract_market_output_returns_none_without_submit_call() -> None:
    events = [_function_call_event("search", "fc-1", {"query": "AI coding assistants"})]
    assert extract_market_output(events) is None
