"""Market Agent-owned LiteLLM -> LangSmith instrumentation.

Google ADK invokes LiteLLM internally, so the service cannot wrap the model call
directly. This module installs one LiteLLM callback and uses a request-scoped
context variable to attach each internal `acompletion` call as a LangSmith LLM
child run under the active Market Agent run.
"""

from __future__ import annotations

import contextvars
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import litellm
from langsmith.run_trees import RunTree
from litellm.integrations.custom_logger import CustomLogger

from market_agent.langsmith_tracing import client, current_headers, redact, tracing_enabled


@dataclass(frozen=True)
class LiteLLMTraceContext:
    request_id: str
    parent_headers: dict[str, str]


_trace_context: contextvars.ContextVar[LiteLLMTraceContext | None] = contextvars.ContextVar(
    "market_agent_litellm_trace_context",
    default=None,
)
_callback: LangSmithLiteLLMCallback | None = None


def _as_mapping(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return dict(value)
    if hasattr(value, "model_dump"):
        dumped = value.model_dump()
        return dict(dumped) if isinstance(dumped, Mapping) else {}
    if hasattr(value, "dict"):
        dumped = value.dict()
        return dict(dumped) if isinstance(dumped, Mapping) else {}
    return {}


def _get_value(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(key, default)
    return getattr(value, key, default)


def _provider_and_model(model: str | None) -> tuple[str | None, str | None]:
    if not model:
        return None, None
    if "/" not in model:
        return None, model
    provider, model_name = model.split("/", 1)
    return provider or None, model_name or model


def _usage_metadata(response_obj: Any) -> dict[str, int]:
    usage = _get_value(response_obj, "usage")
    if usage is None:
        return {}

    prompt_tokens = _get_value(usage, "prompt_tokens")
    completion_tokens = _get_value(usage, "completion_tokens")
    total_tokens = _get_value(usage, "total_tokens")

    usage_metadata: dict[str, int] = {}
    if isinstance(prompt_tokens, int):
        usage_metadata["input_tokens"] = prompt_tokens
    if isinstance(completion_tokens, int):
        usage_metadata["output_tokens"] = completion_tokens
    if isinstance(total_tokens, int):
        usage_metadata["total_tokens"] = total_tokens
    return usage_metadata


def _response_cost(kwargs: Mapping[str, Any], response_obj: Any) -> float | None:
    hidden_params = _as_mapping(_get_value(response_obj, "_hidden_params"))
    for source in (hidden_params, kwargs):
        value = source.get("response_cost") or source.get("cost")
        if isinstance(value, int | float):
            return float(value)
    return None


def _messages_from_kwargs(kwargs: Mapping[str, Any]) -> list[dict[str, Any]]:
    messages = kwargs.get("messages")
    if not isinstance(messages, list):
        return []
    return [redact(_as_mapping(message) or message) for message in messages]


def _choice_message(choice: Any) -> dict[str, Any]:
    message = _get_value(choice, "message")
    if message is not None:
        return redact(_as_mapping(message) or {"message": str(message)})
    text = _get_value(choice, "text")
    if text is not None:
        return {"content": redact(str(text))}
    return redact(_as_mapping(choice) or {"choice": str(choice)})


def _messages_from_response(response_obj: Any) -> list[dict[str, Any]]:
    choices = _get_value(response_obj, "choices")
    if not isinstance(choices, list):
        return []
    return [_choice_message(choice) for choice in choices]


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _normalized_run_window(
    parent: RunTree,
    start_time: datetime,
    end_time: datetime,
) -> tuple[datetime, datetime]:
    start = _aware_utc(start_time)
    end = _aware_utc(end_time)
    duration = max(end - start, timedelta(0))

    if parent.start_time is not None:
        parent_start = _aware_utc(parent.start_time)
        if start < parent_start:
            start = parent_start
            end = start + duration

    return start, max(end, start)


def _metadata(kwargs: Mapping[str, Any], response_obj: Any | None = None) -> dict[str, Any]:
    model = kwargs.get("model")
    provider, model_name = _provider_and_model(str(model) if model is not None else None)
    metadata: dict[str, Any] = {
        "service": "market-agent",
        "adapter": "google-adk-litellm",
        "call_type": kwargs.get("call_type") or "acompletion",
    }
    context = _trace_context.get()
    if context is not None:
        metadata["request_id"] = context.request_id
    if provider:
        metadata["ls_provider"] = provider
    if model_name:
        metadata["ls_model_name"] = model_name
        metadata["model"] = model_name
    if response_obj is not None:
        if usage := _usage_metadata(response_obj):
            metadata["usage_metadata"] = usage
        if cost := _response_cost(kwargs, response_obj):
            metadata["ls_model_cost"] = cost
    return redact(metadata)


def _parent_run() -> RunTree | None:
    context = _trace_context.get()
    if context is None:
        return None
    parent = RunTree.from_headers(context.parent_headers, ls_client=client())
    if parent is not None:
        return parent
    current = current_headers()
    return RunTree.from_headers(current, ls_client=client()) if current else None


def _end_child_run(
    *,
    kwargs: Mapping[str, Any],
    response_obj: Any | None,
    start_time: datetime,
    end_time: datetime,
    error: str | None = None,
) -> None:
    if not tracing_enabled():
        return
    parent = _parent_run()
    if parent is None:
        return

    usage_metadata = _usage_metadata(response_obj) if response_obj is not None else {}
    outputs: dict[str, Any] = {}
    if response_obj is not None:
        outputs["messages"] = _messages_from_response(response_obj)
    if usage_metadata:
        outputs["usage_metadata"] = usage_metadata
    if cost := _response_cost(kwargs, response_obj):
        outputs["cost"] = cost
    if error:
        outputs["error"] = error

    child_start_time, child_end_time = _normalized_run_window(parent, start_time, end_time)
    child = parent.create_child(
        "market-agent.llm",
        run_type="llm",
        inputs={"messages": _messages_from_kwargs(kwargs)},
        outputs=redact(outputs),
        error=error,
        start_time=child_start_time,
        end_time=child_end_time,
        extra={"metadata": _metadata(kwargs, response_obj)},
        tags=["service:market-agent", "google-adk", "litellm"],
    )
    child.post()


class LangSmithLiteLLMCallback(CustomLogger):
    async def async_log_success_event(
        self,
        kwargs: dict[str, Any],
        response_obj: Any,
        start_time: datetime,
        end_time: datetime,
    ) -> None:
        _end_child_run(
            kwargs=kwargs,
            response_obj=response_obj,
            start_time=start_time,
            end_time=end_time,
        )

    async def async_log_failure_event(
        self,
        kwargs: dict[str, Any],
        response_obj: Any,
        start_time: datetime,
        end_time: datetime,
    ) -> None:
        error = kwargs.get("exception") or response_obj
        _end_child_run(
            kwargs=kwargs,
            response_obj=None,
            start_time=start_time,
            end_time=end_time,
            error=f"{type(error).__name__}: {error}",
        )

    def log_success_event(
        self,
        kwargs: dict[str, Any],
        response_obj: Any,
        start_time: datetime,
        end_time: datetime,
    ) -> None:
        _end_child_run(
            kwargs=kwargs,
            response_obj=response_obj,
            start_time=start_time,
            end_time=end_time,
        )

    def log_failure_event(
        self,
        kwargs: dict[str, Any],
        response_obj: Any,
        start_time: datetime,
        end_time: datetime,
    ) -> None:
        error = kwargs.get("exception") or response_obj
        _end_child_run(
            kwargs=kwargs,
            response_obj=None,
            start_time=start_time,
            end_time=end_time,
            error=f"{type(error).__name__}: {error}",
        )


def install_litellm_langsmith_callback() -> None:
    global _callback
    if _callback is None:
        _callback = LangSmithLiteLLMCallback()
    if _callback not in litellm.callbacks:
        litellm.callbacks.append(_callback)


@contextmanager
def litellm_trace_context(request_id: str) -> Iterator[None]:
    if not tracing_enabled():
        yield
        return
    install_litellm_langsmith_callback()
    token = _trace_context.set(
        LiteLLMTraceContext(
            request_id=request_id,
            parent_headers=current_headers(),
        )
    )
    try:
        yield
    finally:
        _trace_context.reset(token)
