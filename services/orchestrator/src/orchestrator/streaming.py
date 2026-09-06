"""Safe, UI-facing workflow stream events owned by the Orchestrator."""

import json
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from langgraph.config import get_stream_writer

_SECRET = re.compile(r"(?:sk-[\w-]+|bearer\s+\S+|AIza[\w-]+|[\w.+-]+@[\w.-]+)", re.IGNORECASE)


def sanitize_query(value: str) -> str:
    """Produce a short UI preview, never a raw prompt or credential."""
    compact = " ".join(value.split())[:160]
    return _SECRET.sub("[redacted]", compact)


def safe_source_url(value: str) -> str | None:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or "@" in parsed.path:
        return None
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def emit_event(
    event_type: str,
    *,
    request_id: str,
    trace_id: str,
    agent: str | None = None,
    data: Mapping[str, Any] | None = None,
) -> None:
    """Publish one custom LangGraph event when the graph is streamed."""
    event: dict[str, Any] = {
        "version": "v1",
        "type": event_type,
        "request_id": request_id,
        "trace_id": trace_id,
        "timestamp": datetime.now(UTC).isoformat(),
        "data": dict(data or {}),
    }
    if agent:
        event["agent"] = agent
    try:
        get_stream_writer()(event)
    except RuntimeError:
        # The normal unary endpoint runs the same nodes without stream mode.
        pass


def encode_sse(event: Mapping[str, Any]) -> str:
    """Encode a JSON event without allowing SSE frame injection."""
    return (
        f"event: {event['type']}\ndata: {json.dumps(event, default=str, separators=(',', ':'))}\n\n"
    )
