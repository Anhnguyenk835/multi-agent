"""Market Agent-owned, redacted LangSmith tracing helpers."""

import os
import re
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from functools import lru_cache
from typing import Any

import langsmith as ls
from langsmith import Client
from langsmith.run_helpers import get_current_run_tree

_SENSITIVE_VALUE = re.compile(r"(?:sk-[\w-]+|bearer\s+\S+|AIza[\w-]+)", re.IGNORECASE)
_SENSITIVE_KEYS = {
    "api_key",
    "authorization",
    "cookie",
    "password",
    "secret",
    "token",
    "access_token",
    "refresh_token",
    "id_token",
}


def _is_sensitive_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return normalized in _SENSITIVE_KEYS or normalized.endswith("_api_key")


def tracing_enabled() -> bool:
    return (
        os.getenv("LANGSMITH_TRACING", "false").lower() == "true"
        and bool(os.getenv("LANGSMITH_API_KEY"))
    )


def redact(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): "[REDACTED]" if _is_sensitive_key(str(key)) else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list | tuple):
        return [redact(item) for item in value]
    if isinstance(value, str):
        return _SENSITIVE_VALUE.sub("[REDACTED]", value)
    return value


@lru_cache(maxsize=1)
def client() -> Client:
    return Client(
        anonymizer=redact,
        hide_inputs=os.getenv("LANGSMITH_HIDE_INPUTS", "true").lower() == "true",
        hide_outputs=os.getenv("LANGSMITH_HIDE_OUTPUTS", "true").lower() == "true",
        hide_metadata=redact,
    )


def current_headers() -> dict[str, str]:
    run_tree = get_current_run_tree()
    return run_tree.to_headers() if run_tree is not None else {}


def _parent_headers(headers: Mapping[str, str] | None) -> dict[str, str]:
    if not headers:
        return {}
    return {
        key.lower(): value
        for key, value in headers.items()
        if key.lower() in {"langsmith-trace", "baggage"}
    }


@contextmanager
def trace_operation(
    name: str,
    *,
    metadata: Mapping[str, Any] | None = None,
    parent_headers: Mapping[str, str] | None = None,
    run_type: str = "chain",
    inputs: Mapping[str, Any] | None = None,
) -> Iterator[Any | None]:
    if not tracing_enabled():
        yield None
        return

    context_kwargs: dict[str, Any] = {
        "client": client(),
        "project_name": os.getenv("LANGSMITH_PROJECT", "distributed-agents-demo"),
        "metadata": redact(dict(metadata or {})),
    }
    if parent := _parent_headers(parent_headers):
        context_kwargs["parent"] = parent

    with ls.tracing_context(**context_kwargs), ls.trace(
        name,
        run_type=run_type,
        inputs=redact(dict(inputs or {})),
        metadata=redact(dict(metadata or {})),
        client=client(),
    ) as run:
        yield run
