from datetime import UTC, datetime
from types import SimpleNamespace

import litellm
from market_agent.langsmith_tracing import redact
from market_agent.litellm_langsmith import (
    LangSmithLiteLLMCallback,
    _aware_utc,
    _messages_from_response,
    _metadata,
    _normalized_run_window,
    _provider_and_model,
    _usage_metadata,
    install_litellm_langsmith_callback,
)


def test_redaction_preserves_usage_token_counts() -> None:
    assert redact(
        {
            "token": "private",
            "usage_metadata": {
                "input_tokens": 10,
                "output_tokens": 20,
                "total_tokens": 30,
            },
        }
    ) == {
        "token": "[REDACTED]",
        "usage_metadata": {
            "input_tokens": 10,
            "output_tokens": 20,
            "total_tokens": 30,
        },
    }


def test_litellm_model_provider_metadata_splits_on_first_slash_only() -> None:
    response = SimpleNamespace(
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=20, total_tokens=30)
    )

    metadata = _metadata({"model": "openai/gpt-4o-mini/preview"}, response)

    assert metadata["ls_provider"] == "openai"
    assert metadata["ls_model_name"] == "gpt-4o-mini/preview"
    assert metadata["usage_metadata"] == {
        "input_tokens": 10,
        "output_tokens": 20,
        "total_tokens": 30,
    }


def test_usage_metadata_maps_litellm_usage_to_langsmith_fields() -> None:
    response = {
        "usage": {
            "prompt_tokens": 11,
            "completion_tokens": 22,
            "total_tokens": 33,
        }
    }

    assert _usage_metadata(response) == {
        "input_tokens": 11,
        "output_tokens": 22,
        "total_tokens": 33,
    }


def test_response_messages_extract_assistant_content() -> None:
    response = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "Market demand is increasing.",
                }
            }
        ]
    }

    assert _messages_from_response(response) == [
        {"role": "assistant", "content": "Market demand is increasing."}
    ]


def test_provider_and_model_splits_litellm_provider_prefix() -> None:
    assert _provider_and_model("openai/gpt-4o-mini") == ("openai", "gpt-4o-mini")
    assert _provider_and_model("gpt-4o-mini") == (None, "gpt-4o-mini")


def test_litellm_naive_callback_timestamps_are_normalized_to_utc() -> None:
    normalized = _aware_utc(datetime(2026, 8, 29, 10, 10, 19))  # noqa: DTZ001

    assert normalized.tzinfo is UTC


def test_litellm_run_window_preserves_order_after_parent_clamp() -> None:
    parent = SimpleNamespace(start_time=datetime(2026, 8, 29, 10, 10, 20, tzinfo=UTC))
    start, end = _normalized_run_window(
        parent,
        datetime(2026, 8, 29, 10, 10, 19),  # noqa: DTZ001
        datetime(2026, 8, 29, 10, 10, 21),  # noqa: DTZ001
    )

    assert start == parent.start_time
    assert end == datetime(2026, 8, 29, 10, 10, 22, tzinfo=UTC)
    assert end >= start


def test_litellm_run_window_clamps_negative_duration() -> None:
    parent = SimpleNamespace(start_time=datetime(2026, 8, 29, 10, 10, 20, tzinfo=UTC))
    start, end = _normalized_run_window(
        parent,
        datetime(2026, 8, 29, 10, 10, 21),  # noqa: DTZ001
        datetime(2026, 8, 29, 10, 10, 19),  # noqa: DTZ001
    )

    assert start == end


def test_install_litellm_callback_is_idempotent() -> None:
    before = list(litellm.callbacks)

    try:
        install_litellm_langsmith_callback()
        install_litellm_langsmith_callback()

        installed = [
            callback
            for callback in litellm.callbacks
            if isinstance(callback, LangSmithLiteLLMCallback)
        ]
        assert len(installed) == 1
    finally:
        litellm.callbacks[:] = before
