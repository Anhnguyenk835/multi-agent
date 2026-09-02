from distributed_agent_contracts import (
    ContractStatus,
    WriterRequest,
    WriterResponse,
    copy_request_metadata,
    render_citation_links,
)

from writer import llm_client
from writer.llm_schema import LLMBrief
from writer.prompts import SYSTEM_PROMPT, build_user_prompt
from writer.settings import WriterAISettings


async def write_brief_live(request: WriterRequest, settings: WriterAISettings) -> WriterResponse:
    result = await llm_client.generate_structured(
        schema=LLMBrief,
        system_prompt=SYSTEM_PROMPT,
        user_prompt=build_user_prompt(request),
        settings=settings,
    )
    content = render_citation_links(result.content, request.citations)
    return WriterResponse(
        **copy_request_metadata(request),
        status=ContractStatus.SUCCESS,
        warnings=request.warnings,
        content=content,
        citations=request.citations,
    )


async def stream_brief_live(request: WriterRequest, settings: WriterAISettings):
    renderer = _BriefStreamRenderer()
    async for chunk in llm_client.generate_structured_stream(
        schema=LLMBrief,
        system_prompt=SYSTEM_PROMPT,
        user_prompt=build_user_prompt(request),
        settings=settings,
    ):
        if chunk.kind == "raw_delta":
            text = renderer.add(chunk.text)
            if text:
                yield {"type": "writer.delta", "data": {"text": text}}
        elif chunk.kind == "completed":
            assert chunk.result is not None
            content = render_citation_links(chunk.result.content, request.citations)
            response = WriterResponse(
                **copy_request_metadata(request),
                status=ContractStatus.SUCCESS,
                warnings=request.warnings,
                content=content,
                citations=request.citations,
            )
            yield {"type": "writer.completed", "data": {"response": response.model_dump(mode="json")}}


def _display_chunks(content: str) -> list[str]:
    return [content[index : index + 24] for index in range(0, len(content), 24)]


class _BriefStreamRenderer:
    """Incrementally reveal the `content` field from raw JSON output.

    The preview is unlinked (bare `[N]` markers) — the authoritative,
    citation-linked content only arrives with the `writer.completed` event.
    """

    def __init__(self) -> None:
        self._raw = ""
        self._displayed = ""

    def add(self, raw_delta: str) -> str:
        self._raw += raw_delta
        content = _partial_json_string(self._raw, "content") or ""
        if not content.startswith(self._displayed):
            return ""
        delta = content[len(self._displayed) :]
        self._displayed = content
        return delta


def _partial_json_string(value: str, field: str) -> str | None:
    marker = f'"{field}"'
    start = value.find(marker)
    if start < 0:
        return None
    colon = value.find(":", start + len(marker))
    quote = value.find('"', colon + 1) if colon >= 0 else -1
    if quote < 0:
        return ""
    output: list[str] = []
    index = quote + 1
    escapes = {'"': '"', "\\": "\\", "/": "/", "b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t"}
    while index < len(value):
        character = value[index]
        if character == '"':
            return "".join(output)
        if character != "\\":
            output.append(character)
            index += 1
            continue
        if index + 1 >= len(value):
            break
        escaped = value[index + 1]
        if escaped == "u":
            if index + 5 >= len(value):
                break
            try:
                output.append(chr(int(value[index + 2 : index + 6], 16)))
            except ValueError:
                return "".join(output)
            index += 6
        elif escaped in escapes:
            output.append(escapes[escaped])
            index += 2
        else:
            return "".join(output)
    return "".join(output)
