from dataclasses import dataclass

import litellm
from google.adk.events import Event
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from market_agent.agent import DeterministicMarketAgent, build_live_agent, extract_market_output
from market_agent.errors import (
    InvalidOutputError,
    ProviderConfigurationError,
    ProviderUnavailableError,
)
from market_agent.langsmith_tracing import trace_operation
from market_agent.litellm_langsmith import litellm_trace_context
from market_agent.settings import AIMode, DemoSettings

_NO_RETRY = (
    litellm.exceptions.AuthenticationError,
    litellm.exceptions.PermissionDeniedError,
    litellm.exceptions.BadRequestError,
)


@dataclass(frozen=True)
class MarketResult:
    market_signals: list[dict[str, object]]
    competitors: list[str]


async def _run_agent(agent, query: str, request_id: str) -> list[Event]:
    runner = Runner(
        agent=agent,
        app_name="market-agent",
        session_service=InMemorySessionService(),
        auto_create_session=True,
    )
    content = types.Content(role="user", parts=[types.Part(text=query)])
    events: list[Event] = []
    with litellm_trace_context(request_id):
        async for event in runner.run_async(
            user_id="orchestrator",
            session_id=request_id,
            new_message=content,
        ):
            events.append(event)
    return events


class MarketAgentRunner:
    def __init__(self, settings: DemoSettings | None = None) -> None:
        self._settings = settings or DemoSettings.from_environment()

    async def analyze(self, query: str, request_id: str) -> MarketResult:
        settings = self._settings
        with trace_operation(
            "market-agent.runner",
            metadata={
                "service": "market-agent",
                "request_id": request_id,
                "mode": settings.ai.ai_mode,
                "query_length": len(query),
            },
            inputs={"query": query, "request_id": request_id},
        ) as run:
            if settings.ai.ai_mode is not AIMode.LIVE:
                events = await _run_agent(
                    DeterministicMarketAgent(name="market_researcher"), query, request_id
                )
                output = next(
                    (event.output for event in events if isinstance(event.output, dict)), None
                )
            else:
                agent = build_live_agent(
                    "market_researcher",
                    f"openai/{settings.ai.openai_model}",
                    settings.exa,
                )
                try:
                    events = await _run_agent(agent, query, request_id)
                except _NO_RETRY as error:
                    raise ProviderConfigurationError(
                        "OpenAI rejected the market agent request"
                    ) from error
                except Exception as error:
                    raise ProviderUnavailableError("OpenAI is unavailable") from error
                output = extract_market_output(events)

            if output is None:
                raise InvalidOutputError("market agent completed without an output event")

            result = MarketResult(
                market_signals=list(output["market_signals"]),
                competitors=list(output["competitors"]),
            )
            if run is not None:
                run.end(
                    outputs={
                        "market_signals": result.market_signals,
                        "competitors": result.competitors,
                    }
                )
            return result
