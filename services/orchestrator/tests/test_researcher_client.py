from distributed_agent_contracts import ErrorCode
from langgraph.pregel.remote import RemoteException
from orchestrator.clients.researcher import _map_researcher_error


def test_remote_invalid_output_preserves_actionable_error() -> None:
    error = RemoteException(
        {
            "error": "InvalidOutputError",
            "message": "model completed without a valid structured findings response",
        }
    )

    mapped = _map_researcher_error(error, streaming=True)

    assert mapped.code is ErrorCode.UPSTREAM_INVALID_RESPONSE
    assert mapped.message == (
        "Researcher model returned invalid structured output: "
        "model completed without a valid structured findings response"
    )
    assert mapped.retryable is False
