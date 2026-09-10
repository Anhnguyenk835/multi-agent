from collections.abc import Callable
from datetime import datetime
from typing import Any

from distributed_agent_contracts import model_timeout_budget
from google.adk.agents import LlmAgent
from google.adk.events import Event
from google.adk.labs.openai import OpenAILlm
from google.adk.tools import FunctionTool
from openai import AsyncOpenAI
from pydantic import BaseModel

from competitor_analyst.errors import ProviderConfigurationError
from competitor_analyst.models import (
    CompetitorDiscoveryInput,
    CompetitorProfileInput,
    CompetitorSynthesisInput,
)
from competitor_analyst.prompts import DISCOVERY_PROMPT, PROFILE_PROMPT, SYNTHESIS_PROMPT
from competitor_analyst.settings import CompetitorAISettings, CompetitorSearchSettings
from competitor_analyst.tools import ExaSourceResult, build_search_function, parse_function_response

SUBMIT_DISCOVERY_TOOL_NAME = "submit_competitor_discovery"
SUBMIT_PROFILE_TOOL_NAME = "submit_competitor_profile"
SUBMIT_SYNTHESIS_TOOL_NAME = "submit_competitor_synthesis"


def submit_competitor_discovery(response: CompetitorDiscoveryInput) -> dict[str, str]:
    """Submit the grounded competitor set discovered for this app market."""
    return {"status": "received"}


def submit_competitor_profile(response: CompetitorProfileInput) -> dict[str, str]:
    """Submit one evidence-backed competitor profile."""
    return {"status": "received"}


def submit_competitor_synthesis(response: CompetitorSynthesisInput) -> dict[str, str]:
    """Submit the cross-competitor synthesis and opportunity gaps."""
    return {"status": "received"}


def build_discovery_agent(
    ai_settings: CompetitorAISettings,
    search_settings: CompetitorSearchSettings,
    *,
    deadline_at: datetime | None,
    max_search_calls: int,
) -> LlmAgent:
    search = build_search_function(
        search_settings,
        deadline_at=deadline_at,
        max_calls=max_search_calls,
        state_key="discovery_search_count",
        phase="discovery",
    )
    return _build_agent(
        name="competitor_discovery",
        instruction=DISCOVERY_PROMPT,
        tools=[FunctionTool(search), FunctionTool(submit_competitor_discovery)],
        settings=ai_settings,
        deadline_at=deadline_at,
    )


def build_profile_agent(
    ai_settings: CompetitorAISettings,
    search_settings: CompetitorSearchSettings,
    *,
    deadline_at: datetime | None,
    max_search_calls: int,
) -> LlmAgent:
    search = build_search_function(
        search_settings,
        deadline_at=deadline_at,
        max_calls=max_search_calls,
        state_key="profile_search_count",
        phase="profile",
    )
    return _build_agent(
        name="competitor_profiler",
        instruction=PROFILE_PROMPT,
        tools=[FunctionTool(search), FunctionTool(submit_competitor_profile)],
        settings=ai_settings,
        deadline_at=deadline_at,
    )


def build_synthesis_agent(
    ai_settings: CompetitorAISettings,
    *,
    deadline_at: datetime | None,
) -> LlmAgent:
    return _build_agent(
        name="competitor_synthesis",
        instruction=SYNTHESIS_PROMPT,
        tools=[FunctionTool(submit_competitor_synthesis)],
        settings=ai_settings,
        deadline_at=deadline_at,
    )


def _build_agent(
    *,
    name: str,
    instruction: str,
    tools: list[FunctionTool],
    settings: CompetitorAISettings,
    deadline_at: datetime | None,
) -> LlmAgent:
    if not settings.gateway_api_key:
        raise ProviderConfigurationError("LLM_GATEWAY_API_KEY is required")
    gateway_client = AsyncOpenAI(
        api_key=settings.gateway_api_key,
        base_url=settings.gateway_base_url,
        timeout=settings.llm_timeout_seconds,
        max_retries=0,
    )
    if deadline_at is not None:
        gateway_client.chat.completions = _DeadlineAwareCompletions(
            gateway_client.chat.completions,
            settings,
            deadline_at,
        )
    return LlmAgent(
        name=name,
        model=OpenAILlm(
            model=settings.model_route,
            max_tokens=settings.llm_max_output_tokens,
            client=gateway_client,
        ),
        instruction=instruction,
        tools=tools,
    )


class _DeadlineAwareCompletions:
    """Recalculate the remaining provider budget before every ADK model turn."""

    def __init__(
        self, delegate: Any, settings: CompetitorAISettings, deadline_at: datetime
    ) -> None:
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
            raise TimeoutError("competitor analyst deadline reached before model call")
        kwargs["timeout"] = budget.client_seconds
        kwargs["extra_body"] = {
            **(kwargs.get("extra_body") or {}),
            "request_timeout": budget.provider_attempt_seconds,
        }
        return await self._delegate.create(**kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._delegate, name)


def collect_search_sources(events: list[Event]) -> dict[str, ExaSourceResult]:
    sources_by_tag: dict[str, ExaSourceResult] = {}
    for event in events:
        for function_response in event.get_function_responses():
            if function_response.name != "search" or function_response.response is None:
                continue
            for result in parse_function_response(function_response.response):
                sources_by_tag[result.tag] = result
    return sources_by_tag


def extract_submitted_model[ModelT: BaseModel](
    events: list[Event],
    *,
    tool_name: str,
    model_type: type[ModelT],
) -> ModelT | None:
    submitted: dict[str, object] | None = None
    for event in events:
        for function_call in event.get_function_calls():
            if function_call.name == tool_name and function_call.args:
                submitted = function_call.args
    if submitted is None:
        return None
    return model_type.model_validate(submitted["response"])


def submit_tool_names() -> dict[str, Callable[..., dict[str, str]]]:
    return {
        SUBMIT_DISCOVERY_TOOL_NAME: submit_competitor_discovery,
        SUBMIT_PROFILE_TOOL_NAME: submit_competitor_profile,
        SUBMIT_SYNTHESIS_TOOL_NAME: submit_competitor_synthesis,
    }
