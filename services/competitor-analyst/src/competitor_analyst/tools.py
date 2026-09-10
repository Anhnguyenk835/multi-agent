import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlparse

from distributed_agent_contracts import remaining_seconds
from exa_py import AsyncExa
from google.adk.tools import ToolContext

from competitor_analyst.errors import ProviderConfigurationError
from competitor_analyst.settings import CompetitorSearchSettings
from competitor_analyst.telemetry import (
    operation_span,
    set_observation_input,
    set_observation_output,
)


@dataclass(frozen=True, slots=True)
class ExaSourceResult:
    tag: str
    title: str
    url: str
    publisher: str
    published_at: datetime | None
    retrieved_at: datetime
    content: str


def _default_client_factory(settings: CompetitorSearchSettings) -> AsyncExa:
    if not settings.exa_api_key:
        raise ProviderConfigurationError("EXA_API_KEY is required")
    return AsyncExa(api_key=settings.exa_api_key)


def _publisher_from_url(url: str) -> str:
    netloc = urlparse(url).netloc
    return netloc.removeprefix("www.") or "unknown"


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def build_search_function(
    settings: CompetitorSearchSettings,
    *,
    client_factory: Callable[[CompetitorSearchSettings], AsyncExa] | None = None,
    deadline_at: datetime | None = None,
    max_calls: int = 3,
    state_key: str = "search_call_count",
    phase: str = "research",
):
    """Build a fresh `search` function bound to `settings`.

    A fresh function is built per agent construction (per request) rather
    than shared as a module-level singleton, matching Market Analyst's tool.
    """
    client = (client_factory or _default_client_factory)(settings)

    async def search(query: str, tool_context: ToolContext) -> dict[str, object]:
        """Search the web for sources relevant to the market query.

        Args:
            query: The search query.
        """
        call_count = tool_context.state.get(state_key, 0) + 1
        tool_context.state[state_key] = call_count
        if call_count > max_calls:
            return {
                "results": [],
                "error": (
                    f"Search budget of {max_calls} calls exhausted. "
                    "Submit the grounded evidence gathered so far."
                ),
            }

        with operation_span(
            "tool.search",
            observation_type="tool",
            attributes={
                "app.agent": "competitor_analyst",
                "app.workflow.phase": phase,
                "app.tool.name": "search",
                "app.tool.requested_results": settings.exa_max_results,
            },
        ) as span:
            set_observation_input(span, {"query": query})
            remaining = remaining_seconds(deadline_at)
            if remaining is None:
                response = await client.search(
                    query,
                    num_results=settings.exa_max_results,
                    contents={"text": {"maxCharacters": settings.exa_content_max_characters}},
                )
            else:
                if remaining <= 1.0:
                    raise TimeoutError("competitor analyst deadline reached before search")
                async with asyncio.timeout(remaining - 1.0):
                    response = await client.search(
                        query,
                        num_results=settings.exa_max_results,
                        contents={"text": {"maxCharacters": settings.exa_content_max_characters}},
                    )

            retrieved_at = datetime.now(UTC).isoformat()
            results: list[dict[str, object]] = []
            for position, result in enumerate(response.results[: settings.exa_max_results]):
                content = result.text or ""
                if not content:
                    continue
                results.append(
                    {
                        "tag": f"{tool_context.function_call_id}#{position}",
                        "title": result.title or result.url,
                        "url": result.url,
                        "publisher": _publisher_from_url(result.url),
                        "published_at": result.published_date,
                        "retrieved_at": retrieved_at,
                        "content": content,
                    }
                )
            set_observation_output(span, {"result_count": len(results)})
        return {"results": results}

    return search


def parse_function_response(payload: dict[str, object]) -> list[ExaSourceResult]:
    return [
        ExaSourceResult(
            tag=entry["tag"],
            title=entry["title"],
            url=entry["url"],
            publisher=entry["publisher"],
            published_at=_parse_datetime(entry.get("published_at")),
            retrieved_at=_parse_datetime(entry["retrieved_at"]) or datetime.now(UTC),
            content=entry["content"],
        )
        for entry in payload["results"]
    ]
