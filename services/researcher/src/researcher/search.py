import asyncio
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlparse

from exa_py import AsyncExa
from langchain_core.messages import ToolMessage

from researcher.errors import ProviderConfigurationError
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


def default_client_factory(settings: ResearcherExaSettings) -> AsyncExa:
    if not settings.exa_api_key:
        raise ProviderConfigurationError("EXA_API_KEY is required")
    return AsyncExa(api_key=settings.exa_api_key)


class ExaSearch:
    """Business search implementation independent of LangGraph and telemetry."""

    def __init__(
        self,
        settings: ResearcherExaSettings,
        *,
        client_factory: Callable[[ResearcherExaSettings], AsyncExa] | None = None,
        deadline_at: datetime | None = None,
    ) -> None:
        self._settings = settings
        self._client = (client_factory or default_client_factory)(settings)
        self._deadline_at = deadline_at

    async def execute(self, query: str, tool_call_id: str) -> list[dict[str, object]]:
        settings = self._settings
        if self._deadline_at is None:
            response = await self._search(query)
        else:
            normalized = (
                self._deadline_at.replace(tzinfo=UTC)
                if self._deadline_at.tzinfo is None
                else self._deadline_at
            )
            remaining = (normalized - datetime.now(UTC)).total_seconds() - 1.0
            if remaining <= 0:
                raise TimeoutError("researcher deadline reached before search")
            async with asyncio.timeout(remaining):
                response = await self._search(query)

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
        return results

    async def _search(self, query: str):
        return await self._client.search(
            query,
            num_results=self._settings.exa_max_results,
            contents={"text": {"maxCharacters": self._settings.exa_content_max_characters}},
        )


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
