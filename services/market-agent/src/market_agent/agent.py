from collections.abc import AsyncGenerator
from datetime import datetime

from google.adk.agents import BaseAgent, InvocationContext, LlmAgent
from google.adk.events import Event
from google.adk.models.lite_llm import LiteLlm
from google.adk.tools import FunctionTool

from market_agent.fixtures import market_fixture
from market_agent.llm_schema import LLMMarketResponse
from market_agent.prompts import SYSTEM_PROMPT
from market_agent.settings import MarketExaSettings
from market_agent.tools import ExaSourceResult, build_search_function, parse_function_response

SUBMIT_TOOL_NAME = "submit_market_analysis"


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


def submit_market_analysis(response: LLMMarketResponse) -> dict[str, str]:
    """Submit your final, grounded market analysis. Call this exactly once,
    when you have gathered enough grounded material and are ready to finish.

    Args:
        response: The structured market analysis: signals and competitors,
            each signal citing the `tag` of its supporting search result.
    """
    return {"status": "received"}


def build_live_agent(name: str, model_string: str, exa_settings: MarketExaSettings) -> LlmAgent:
    """Build a native ADK tool-calling agent for `model_string`.

    `model_string` uses litellm's provider-prefixed form, e.g.
    `"openai/gpt-4o-mini"` — ADK has no native OpenAI client, so `LiteLlm`
    is the only supported bridge to it.

    The final structured answer is delivered as a call to the synthetic
    `submit_market_analysis` tool rather than via `LlmAgent.output_schema`,
    matching the tag-grounding pattern used by Researcher's search tool.
    """
    search = build_search_function(exa_settings)
    return LlmAgent(
        name=name,
        model=LiteLlm(model=model_string),
        instruction=SYSTEM_PROMPT,
        tools=[FunctionTool(search), FunctionTool(submit_market_analysis)],
    )


def collect_search_sources(events: list[Event]) -> dict[str, ExaSourceResult]:
    """Scan every `search` function-response in `events` into a tag -> source map."""
    sources_by_tag: dict[str, ExaSourceResult] = {}
    for event in events:
        for function_response in event.get_function_responses():
            if function_response.name != "search" or function_response.response is None:
                continue
            for result in parse_function_response(function_response.response):
                sources_by_tag[result.tag] = result
    return sources_by_tag


def build_market_output(
    structured: LLMMarketResponse, sources_by_tag: dict[str, ExaSourceResult]
) -> dict[str, object]:
    signals: list[dict[str, object]] = []
    for signal in structured.signals:
        matched = sources_by_tag.get(signal.source_tag)
        if matched is None:
            raise ValueError(f"LLM signal referenced unknown source_tag {signal.source_tag!r}")
        signals.append(
            {
                "topic": signal.topic,
                "observation": signal.observation,
                "source": {
                    "title": matched.title,
                    "url": matched.url,
                    "publisher": matched.publisher,
                    "published_at_unix_ms": _to_unix_ms(matched.published_at),
                    "retrieved_at_unix_ms": _to_unix_ms(matched.retrieved_at),
                    "content": matched.content,
                },
            }
        )
    return {"market_signals": signals, "competitors": structured.competitors}


def extract_market_output(events: list[Event]) -> dict[str, object] | None:
    """Reduce a finished agent run's events into the `MarketResult`-shaped dict.

    Returns None if the model never called `submit_market_analysis`.
    """
    submitted_args: dict[str, object] | None = None
    for event in events:
        for function_call in event.get_function_calls():
            if function_call.name == SUBMIT_TOOL_NAME and function_call.args:
                submitted_args = function_call.args

    if submitted_args is None:
        return None

    structured = LLMMarketResponse.model_validate(submitted_args["response"])
    sources_by_tag = collect_search_sources(events)
    return build_market_output(structured, sources_by_tag)
