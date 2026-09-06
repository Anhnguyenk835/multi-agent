import json
from collections.abc import Callable
from contextlib import nullcontext
from datetime import datetime
from typing import Annotated

from exa_py import AsyncExa
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.config import get_stream_writer

from researcher.search import ExaSearch
from researcher.settings import ResearcherExaSettings
from researcher.telemetry import ReactAgentTelemetry, _json_attribute, operation_span


def _stream_activity(event_type: str, data: dict[str, object]) -> None:
    try:
        get_stream_writer()({"type": event_type, "data": data})
    except (KeyError, RuntimeError):
        pass


def build_search_tool(
    settings: ResearcherExaSettings,
    *,
    client_factory: Callable[[ResearcherExaSettings], AsyncExa] | None = None,
    deadline_at: datetime | None = None,
    telemetry: ReactAgentTelemetry | None = None,
):
    """Build a fresh `search` tool bound to `settings`.

    A fresh tool is built per graph construction (per request) rather than
    shared as a module-level singleton, since its Exa client and settings
    must not leak across concurrent requests.
    """
    search_business = ExaSearch(
        settings,
        client_factory=client_factory,
        deadline_at=deadline_at,
    )

    @tool("search")
    async def search(
        query: str,
        tool_call_id: Annotated[str, InjectedToolCallId],
    ) -> str:
        """Search the web for sources relevant to the research query."""
        _stream_activity(
            "research.search.started",
            {"query_preview": " ".join(query.split())[:160]},
        )
        turn_context = telemetry.tool_context(tool_call_id) if telemetry else nullcontext()
        with turn_context:
            with operation_span(
                "search",
                attributes={
                    "app.agent": "researcher",
                    "app.tool.name": "search",
                    "langfuse.observation.input": _json_attribute({"query": query}),
                },
            ) as search_span:
                with operation_span(
                    "tool.search",
                    observation_type="tool",
                    attributes={
                        "app.agent": "researcher",
                        "app.tool.name": "search",
                        "app.tool.requested_results": settings.exa_max_results,
                    },
                ):
                    results = await search_business.execute(query, tool_call_id)
                tool_output = {"result_count": len(results)}
                search_span.set_attribute(
                    "langfuse.observation.output",
                    _json_attribute(tool_output),
                )
            if telemetry:
                telemetry.complete_tool(tool_call_id, tool_output)
        _stream_activity("research.search.completed", {"result_count": len(results)})
        return json.dumps({"results": results}, default=str)

    return search
