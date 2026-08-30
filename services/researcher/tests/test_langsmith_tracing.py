import pytest
from researcher.graph import _langsmith_headers, graph
from researcher.langsmith_tracing import redact


def test_graph_extracts_only_langsmith_parent_context() -> None:
    headers = _langsmith_headers(
        {
            "configurable": {
                "thread_id": "workflow-1",
                "langsmith-trace": "trace-header",
                "baggage": "langsmith-project=demo",
                "unrelated": "ignored",
            }
        }
    )

    assert headers == {
        "langsmith-trace": "trace-header",
        "baggage": "langsmith-project=demo",
    }


def test_researcher_redaction_hides_credentials_without_hiding_content_or_usage() -> None:
    assert redact(
        {
            "content": "do not trace",
            "token": "private",
            "count": 2,
            "usage_metadata": {
                "input_tokens": 10,
                "output_tokens": 20,
                "total_tokens": 30,
            },
        }
    ) == {
        "content": "do not trace",
        "token": "[REDACTED]",
        "count": 2,
        "usage_metadata": {
            "input_tokens": 10,
            "output_tokens": 20,
            "total_tokens": 30,
        },
    }


@pytest.mark.anyio
async def test_graph_entry_point_is_an_async_context_manager() -> None:
    async with graph({"configurable": {}}) as remote_graph:
        assert remote_graph is not None
