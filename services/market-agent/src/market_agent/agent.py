from datetime import datetime
from typing import Any

from distributed_agent_contracts import model_timeout_budget
from google.adk.agents import LlmAgent
from google.adk.events import Event
from google.adk.labs.openai import OpenAILlm
from google.adk.tools import FunctionTool
from openai import AsyncOpenAI

from market_agent.errors import ProviderConfigurationError
from market_agent.llm_schema import LLMMarketResponse
from market_agent.prompts import SYSTEM_PROMPT
from market_agent.settings import MarketAISettings, MarketExaSettings
from market_agent.tools import ExaSourceResult, build_search_function, parse_function_response

SUBMIT_TOOL_NAME = "submit_market_analysis"


def _to_unix_ms(value: datetime | str | None) -> int:
    if value is None:
        return 0
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    return int(value.timestamp() * 1000)


def submit_market_analysis(response: LLMMarketResponse) -> dict[str, str]:
    """Submit your final, grounded market analysis. Call this exactly once,
    when you have gathered enough grounded material and are ready to finish.

    Args:
        response: The structured market analysis: signals and competitors,
            each signal citing the `tag` of its supporting search result.
    """
    return {"status": "received"}


def build_live_agent(
    name: str,
    ai_settings: MarketAISettings,
    exa_settings: MarketExaSettings,
    *,
    deadline_at: datetime | None = None,
) -> LlmAgent:
    """Build an ADK tool-calling agent backed by the LiteLLM gateway.

    ADK retains its native tool loop. Its OpenAI-compatible model adapter is
    given an SDK client pointed at LiteLLM, so the logical route stays in the
    agent configuration while provider choice and fallback remain at the
    gateway.

    The final structured answer is delivered as a call to the synthetic
    `submit_market_analysis` tool rather than via `LlmAgent.output_schema`,
    matching the tag-grounding pattern used by Researcher's search tool.
    """
    if not ai_settings.gateway_api_key:
        raise ProviderConfigurationError("LLM_GATEWAY_API_KEY is required")

    search = build_search_function(exa_settings, deadline_at=deadline_at)
    gateway_client = AsyncOpenAI(
        api_key=ai_settings.gateway_api_key,
        base_url=ai_settings.gateway_base_url,
        timeout=ai_settings.llm_timeout_seconds,
        max_retries=0,
    )
    if deadline_at is not None:
        gateway_client.chat.completions = _DeadlineAwareCompletions(
            gateway_client.chat.completions,
            ai_settings,
            deadline_at,
        )
    return LlmAgent(
        name=name,
        model=OpenAILlm(
            model=ai_settings.model_route,
            max_tokens=ai_settings.llm_max_output_tokens,
            client=gateway_client,
        ),
        instruction=SYSTEM_PROMPT,
        tools=[FunctionTool(search), FunctionTool(submit_market_analysis)],
    )


class _DeadlineAwareCompletions:
    """Add a fresh remaining-budget calculation to every ADK model turn."""

    def __init__(self, delegate: Any, settings: MarketAISettings, deadline_at: datetime) -> None:
        self._delegate = delegate
        self._settings = settings
        self._deadline_at = deadline_at

    async def create(self, **kwargs: Any):
        budget = model_timeout_budget(
            self._deadline_at,
            configured_seconds=self._settings.llm_timeout_seconds,
            provider_attempts=self._settings.gateway_max_provider_attempts,
        )
        if budget.provider_attempt_seconds <= 0 or budget.client_seconds <= 0:
            raise TimeoutError("market agent deadline reached before model call")
        kwargs["timeout"] = budget.client_seconds
        kwargs["extra_body"] = {
            **(kwargs.get("extra_body") or {}),
            "request_timeout": budget.provider_attempt_seconds,
        }
        return await self._delegate.create(**kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._delegate, name)


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
