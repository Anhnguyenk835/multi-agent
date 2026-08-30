import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated
from urllib.parse import urlparse

from exa_py import AsyncExa
from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.config import get_stream_writer

from researcher.settings import ResearcherExaSettings


@dataclass(frozen=True, slots=True)
class ExaSourceResult:
    tag: str
    title: str
    url: str
    publisher: str
    published_at: datetime | None
    retrieved_at: datetime
    content: str


def _default_client_factory(settings: ResearcherExaSettings) -> AsyncExa:
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


def _stream_activity(event_type: str, data: dict[str, object]) -> None:
    try:
        get_stream_writer()({"type": event_type, "data": data})
    except (KeyError, RuntimeError):
        pass


def build_search_tool(
    settings: ResearcherExaSettings,
    *,
    client_factory: Callable[[ResearcherExaSettings], AsyncExa] | None = None,
):
    """Build a fresh `search` tool bound to `settings`.

    A fresh tool is built per graph construction (per request) rather than
    shared as a module-level singleton, since its Exa client and settings
    must not leak across concurrent requests.
    """
    client = (client_factory or _default_client_factory)(settings)

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
                    "tag": f"{tool_call_id}#{position}",
                    "title": result.title or result.url,
                    "url": result.url,
                    "publisher": _publisher_from_url(result.url),
                    "published_at": result.published_date,
                    "retrieved_at": retrieved_at,
                    "content": content,
                }
            )
        _stream_activity("research.search.completed", {"result_count": len(results)})
        return json.dumps({"results": results}, default=str)

    return search


def parse_tool_message(message: ToolMessage) -> list[ExaSourceResult]:
    payload = json.loads(message.content)
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
