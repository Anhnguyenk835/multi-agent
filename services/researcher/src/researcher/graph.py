import asyncio
from datetime import UTC, datetime

from distributed_agent_contracts import (
    ContractError,
    ContractStatus,
    ErrorCode,
    Finding,
    ResearcherInput,
    ResearcherOutput,
    ResearcherRemoteState,
    Source,
    copy_request_metadata,
)
from langchain.agents import create_agent
from langchain.agents.middleware import ToolCallLimitMiddleware, wrap_model_call
from langchain.agents.structured_output import ToolStrategy
from langchain_core.messages import ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph

from researcher.errors import GroundingError, ProviderConfigurationError, ToolCallLimitReachedError
from researcher.llm_schema import LLMFindingsResponse
from researcher.prompts import SYSTEM_PROMPT
from researcher.settings import DemoSettings, ResearcherAISettings
from researcher.telemetry import ReactAgentTelemetry, extracted_request_context, operation_span
from researcher.tools import build_search_tool, parse_tool_message


def _build_chat_model(
    settings: ResearcherAISettings,
    *,
    timeout_seconds: float | None = None,
    gateway_timeout_seconds: float | None = None,
) -> ChatOpenAI:
    if not settings.gateway_api_key:
        raise ProviderConfigurationError("LLM_GATEWAY_API_KEY is required")

    timeout = timeout_seconds or settings.llm_timeout_seconds
    return ChatOpenAI(
        model=settings.model_route,
        api_key=settings.gateway_api_key,
        base_url=settings.gateway_base_url,
        timeout=timeout,
        max_completion_tokens=settings.llm_max_output_tokens,
        # LiteLLM owns retry and fallback policy. Retrying here would multiply
        # provider attempts and bypass the route's bounded failure budget.
        max_retries=0,
        extra_body=(
            {"request_timeout": gateway_timeout_seconds}
            if gateway_timeout_seconds is not None
            else None
        ),
    )


def _deadline_middleware(settings: ResearcherAISettings, deadline_at: datetime | None):
    @wrap_model_call
    async def apply_deadline(request, handler):
        remaining = _remaining_seconds(deadline_at)
        if remaining is None:
            return await handler(request)

        gateway_timeout, client_timeout = _model_timeouts(settings, remaining)
        if gateway_timeout <= 0 or client_timeout <= 0:
            raise TimeoutError("researcher deadline reached before model call")
        model = _build_chat_model(
            settings,
            timeout_seconds=client_timeout,
            gateway_timeout_seconds=gateway_timeout,
        )
        return await handler(request.override(model=model))

    return apply_deadline


def _model_timeouts(
    settings: ResearcherAISettings,
    remaining: float,
) -> tuple[float, float]:
    # LiteLLM's request_timeout is per provider attempt. Divide the shared
    # budget so primary/retry/fallback all finish before the graph deadline.
    provider_budget = (remaining - 2.0) / settings.gateway_max_provider_attempts
    return min(settings.llm_timeout_seconds, provider_budget), remaining - 1.0


_RESEARCHER_INPUT_FIELDS = set(ResearcherInput.model_fields)


def _extract_request(state: dict[str, object]) -> ResearcherInput:
    return ResearcherInput.model_validate(
        {key: value for key, value in state.items() if key in _RESEARCHER_INPUT_FIELDS}
    )


def _build_graph(runtime_settings: DemoSettings):
    ai_settings = runtime_settings.ai

    async def run_react_agent(
        state: ResearcherRemoteState,
        config: RunnableConfig,
    ) -> dict[str, object]:
        request = _extract_request(state)
        configurable = config.get("configurable", {})
        carrier = configurable.get("otel_headers", {})
        with (
            extracted_request_context(request, carrier),
            operation_span(
                "researcher.run_react_agent",
                observation_type="agent",
                attributes={"app.agent": "researcher", "app.attempt": request.attempt},
            ),
        ):
            remaining = _remaining_seconds(request.deadline_at)
            if remaining is not None and remaining <= 0:
                return _deadline_response(request)

            turn_telemetry = ReactAgentTelemetry(
                ai_settings.model_route,
                tool_names={"search"},
            )
            search_tool = build_search_tool(
                runtime_settings.exa,
                deadline_at=request.deadline_at,
                telemetry=turn_telemetry,
            )
            agent = create_agent(
                model=_build_chat_model(ai_settings),
                tools=[search_tool],
                system_prompt=SYSTEM_PROMPT,
                response_format=ToolStrategy(LLMFindingsResponse),
                middleware=[
                    turn_telemetry.middleware(),
                    _deadline_middleware(ai_settings, request.deadline_at),
                    ToolCallLimitMiddleware(tool_name="search", run_limit=3, exit_behavior="end"),
                ],
            )
            try:
                if remaining is None:
                    final_state = await agent.ainvoke(
                        {"messages": [{"role": "user", "content": request.query}]},
                    )
                else:
                    async with asyncio.timeout(remaining):
                        final_state = await agent.ainvoke(
                            {"messages": [{"role": "user", "content": request.query}]},
                        )
            except TimeoutError:
                return _deadline_response(request)
            finally:
                turn_telemetry.close()

        sources_by_tag = {}
        for message in final_state["messages"]:
            # ToolCallLimitMiddleware(exit_behavior="end") injects synthetic
            # ToolMessages (name="search", status="error") with plain-text
            # content when the run_limit is hit — not the tool's JSON output.
            if (
                isinstance(message, ToolMessage)
                and message.name == "search"
                and message.status != "error"
            ):
                for result in parse_tool_message(message):
                    sources_by_tag[result.tag] = result

        structured: LLMFindingsResponse | None = final_state["structured_response"]
        if structured is None:
            # ToolCallLimitMiddleware(exit_behavior="end") jumps straight to
            # END once the limit is hit, so the agent never got to call the
            # final structured-output tool.
            raise ToolCallLimitReachedError(
                "search tool call limit reached before the model produced a structured response"
            )
        findings: list[Finding] = []
        for raw_finding in structured.findings:
            matched = sources_by_tag.get(raw_finding.source_tag)
            if matched is None:
                raise GroundingError(
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
                        content=matched.content,
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


def _remaining_seconds(deadline_at: datetime | None) -> float | None:
    if deadline_at is None:
        return None
    normalized = deadline_at.replace(tzinfo=UTC) if deadline_at.tzinfo is None else deadline_at
    return (normalized - datetime.now(UTC)).total_seconds()


def _deadline_response(request: ResearcherInput) -> dict[str, object]:
    return ResearcherOutput(
        **copy_request_metadata(request),
        status=ContractStatus.FAILED,
        error=ContractError(
            code=ErrorCode.DEADLINE_EXCEEDED,
            message="Researcher deadline exceeded",
            retryable=True,
        ),
    ).model_dump(mode="json")


def build_graph(config: RunnableConfig):
    """Create the graph when invoked by LangGraph Server.

    LangGraph Server invokes graph factories with its runtime configuration as
    their sole argument. Application settings always come from the service
    environment; treating the server config as ``DemoSettings`` makes live runs
    fail before the first model request.
    """
    del config
    return build_graph_for_settings(DemoSettings.from_environment())


def build_graph_for_settings(runtime_settings: DemoSettings):
    """Create a graph with explicit settings for unit tests."""
    return _build_graph(runtime_settings)
