from dataclasses import dataclass

import openai
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
from market_agent.settings import AIMode, DemoSettings

_NO_RETRY = (
    openai.AuthenticationError,
    openai.PermissionDeniedError,
    openai.BadRequestError,
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
                settings.ai,
                settings.exa,
            )
            try:
                events = await _run_agent(agent, query, request_id)
            except _NO_RETRY as error:
                raise ProviderConfigurationError(
                    "LLM gateway rejected the market agent request"
                ) from error
            except Exception as error:
                raise ProviderUnavailableError("LLM gateway is unavailable") from error
            output = extract_market_output(events)

        if output is None:
            raise InvalidOutputError("market agent completed without an output event")

        return MarketResult(
            market_signals=list(output["market_signals"]),
            competitors=list(output["competitors"]),
        )
