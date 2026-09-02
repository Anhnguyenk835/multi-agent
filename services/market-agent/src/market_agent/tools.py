from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlparse

from exa_py import AsyncExa
from google.adk.tools import ToolContext

from market_agent.errors import ProviderConfigurationError
from market_agent.settings import MarketExaSettings
from market_agent.telemetry import operation_span

MAX_SEARCH_CALLS = 3
_CALL_COUNT_STATE_KEY = "search_call_count"


@dataclass(frozen=True, slots=True)
class ExaSourceResult:
    tag: str
    title: str
    url: str
    publisher: str
    published_at: datetime | None
    retrieved_at: datetime
    content: str


def _default_client_factory(settings: MarketExaSettings) -> AsyncExa:
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
    settings: MarketExaSettings,
    *,
    client_factory: Callable[[MarketExaSettings], AsyncExa] | None = None,
):
    """Build a fresh `search` function bound to `settings`.

    A fresh function is built per agent construction (per request) rather
    than shared as a module-level singleton, matching Researcher's tool.
    """
    client = (client_factory or _default_client_factory)(settings)

    async def search(query: str, tool_context: ToolContext) -> dict[str, object]:
        """Search the web for sources relevant to the market query.

        Args:
            query: The search query.
        """
        call_count = tool_context.state.get(_CALL_COUNT_STATE_KEY, 0) + 1
        tool_context.state[_CALL_COUNT_STATE_KEY] = call_count
        if call_count > MAX_SEARCH_CALLS:
            return {
                "results": [],
                "error": (
                    f"Search budget of {MAX_SEARCH_CALLS} calls exhausted. "
                    "Use `submit_market_analysis` with what you have gathered so far."
                ),
            }

        with operation_span(
            "tool.search",
            observation_type="tool",
            attributes={
                "app.agent": "market",
                "app.tool.name": "search",
                "app.tool.requested_results": settings.exa_max_results,
            },
        ):
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
