from datetime import UTC, datetime, timedelta

import pytest
from distributed_agent_contracts import ErrorCode
from orchestrator.config import AgentPolicy
from orchestrator.errors import AgentCallError
from orchestrator.retry import invoke_with_retry


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_retries_transient_error_and_propagates_attempt() -> None:
    attempts: list[int] = []

    async def operation(attempt: int) -> str:
        attempts.append(attempt)
        if attempt < 3:
            raise AgentCallError(
                ErrorCode.UPSTREAM_UNAVAILABLE,
                "transient",
                retryable=True,
            )
        return "ok"

    async def no_sleep(_: float) -> None:
        return None

    result = await invoke_with_retry(
        operation,
        AgentPolicy(timeout_seconds=1, max_attempts=3, backoff_seconds=0),
        None,
        sleep=no_sleep,
    )

    assert result.value == "ok"
    assert result.attempts == 3
    assert attempts == [1, 2, 3]


@pytest.mark.anyio
async def test_expired_workflow_deadline_prevents_call() -> None:
    called = False

    async def operation(_: int) -> str:
        nonlocal called
        called = True
        return "unexpected"

    with pytest.raises(AgentCallError) as error:
        await invoke_with_retry(
            operation,
            AgentPolicy(timeout_seconds=1, max_attempts=3, backoff_seconds=0),
            datetime.now(UTC) - timedelta(seconds=1),
        )

    assert error.value.code is ErrorCode.DEADLINE_EXCEEDED
    assert called is False
