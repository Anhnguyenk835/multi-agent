from dataclasses import dataclass

import openai
from google.adk.events import Event
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from market_agent.agent import build_live_agent, extract_market_output
from market_agent.errors import (
    InvalidOutputError,
    ProviderConfigurationError,
    ProviderUnavailableError,
)
from market_agent.settings import DemoSettings
from market_agent.telemetry import operation_span

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
        with operation_span(
            "market-agent.run_adk_agent",
            observation_type="agent",
            attributes={"app.agent": "market"},
        ):
            try:
                agent = build_live_agent(
                    "market_researcher",
                    settings.ai,
                    settings.exa,
                )
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
