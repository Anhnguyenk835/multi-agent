import asyncio
from contextlib import asynccontextmanager

import langsmith as ls
from distributed_agent_contracts import (
    ContractStatus,
    Finding,
    ResearcherInput,
    ResearcherOutput,
    ResearcherRemoteState,
    Source,
    copy_request_metadata,
)
from langchain.agents import create_agent
from langchain.agents.middleware import ToolCallLimitMiddleware
from langchain.agents.structured_output import ToolStrategy
from langchain_core.messages import ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph

from researcher.errors import GroundingError, ToolCallLimitReachedError
from researcher.fixtures import build_findings
from researcher.langsmith_tracing import langchain_tracer
from researcher.llm_schema import LLMFindingsResponse
from researcher.prompts import SYSTEM_PROMPT
from researcher.settings import AIMode, DemoSettings, FailureMode, ResearcherAISettings
from researcher.tools import build_search_tool, parse_tool_message


def _build_chat_model(settings: ResearcherAISettings) -> ChatOpenAI:
    return ChatOpenAI(
        model_name=settings.openai_model,
        openai_api_key=settings.openai_api_key,
        request_timeout=settings.llm_timeout_seconds,
    )


def _build_fixture_graph(runtime_settings: DemoSettings):
    async def collect_findings(
        state: ResearcherRemoteState, config: RunnableConfig
    ) -> dict[str, object]:
        request = ResearcherInput.model_validate(state)
        if runtime_settings.failure_mode is FailureMode.TIMEOUT:
            await asyncio.sleep(runtime_settings.delay_seconds)
        if runtime_settings.failure_mode is FailureMode.TRANSIENT_ERROR:
            raise RuntimeError("simulated transient Researcher failure")
        if runtime_settings.failure_mode is FailureMode.INVALID_RESPONSE:
            return {"status": "invalid", "findings": "not-a-list"}

        response = ResearcherOutput(
            **copy_request_metadata(request),
            status=ContractStatus.SUCCESS,
            findings=build_findings(request.query),
        )
        return response.model_dump(mode="json")

    builder = StateGraph(
        ResearcherRemoteState,
        input_schema=ResearcherInput,
        output_schema=ResearcherOutput,
    )
    builder.add_node("collect_findings", collect_findings)
    builder.add_edge(START, "collect_findings")
    builder.add_edge("collect_findings", END)
    return builder.compile()


_RESEARCHER_INPUT_FIELDS = set(ResearcherInput.model_fields)


def _extract_request(state: dict[str, object]) -> ResearcherInput:
    return ResearcherInput.model_validate(
        {key: value for key, value in state.items() if key in _RESEARCHER_INPUT_FIELDS}
    )


def _langsmith_headers(config: RunnableConfig) -> dict[str, str]:
    configurable = config.get("configurable", {})
    return {
        key: value
        for key, value in configurable.items()
        if key in {"langsmith-trace", "baggage"} and isinstance(value, str)
    }


def _build_live_graph(runtime_settings: DemoSettings):
    ai_settings = runtime_settings.ai

    async def run_react_agent(
        state: ResearcherRemoteState, config: RunnableConfig
    ) -> dict[str, object]:
        request = _extract_request(state)
        search_tool = build_search_tool(runtime_settings.exa)
        agent = create_agent(
            model=_build_chat_model(ai_settings),
            tools=[search_tool],
            system_prompt=SYSTEM_PROMPT,
            response_format=ToolStrategy(LLMFindingsResponse),
            middleware=[
                ToolCallLimitMiddleware(tool_name="search", run_limit=3, exit_behavior="end"),
            ],
        )
        callbacks = [tracer] if (tracer := langchain_tracer()) is not None else []
        final_state = await agent.ainvoke(
            {"messages": [{"role": "user", "content": request.query}]},
            config={"callbacks": callbacks},
        )

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


def build_graph(settings: DemoSettings | None = None):
    runtime_settings = settings or DemoSettings.from_environment()
    if runtime_settings.ai.ai_mode is AIMode.LIVE:
        return _build_live_graph(runtime_settings)
    return _build_fixture_graph(runtime_settings)


@asynccontextmanager
async def graph(config: RunnableConfig):
    """Accept LangGraph Server's distributed LangSmith context for the graph run.

    The server creates the top-level ``researcher`` run before it enters graph
    nodes. Setting the parent here, rather than in an individual node, makes
    that whole run a child of ``call_researcher`` in the Orchestrator trace.
    """
    configurable = config.get("configurable", {})
    parent_trace = configurable.get("langsmith-trace")
    project_name = configurable.get("langsmith-project")
    metadata = configurable.get("langsmith-metadata")
    tags = configurable.get("langsmith-tags")

    with ls.tracing_context(
        parent=parent_trace if isinstance(parent_trace, str) else None,
        project_name=project_name if isinstance(project_name, str) else None,
        metadata=metadata if isinstance(metadata, dict) else None,
        tags=tags if isinstance(tags, list) and all(isinstance(tag, str) for tag in tags) else None,
    ):
        yield build_graph()
