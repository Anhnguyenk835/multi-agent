import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from distributed_agent_contracts import ErrorCode

from orchestrator.config import AgentPolicy
from orchestrator.errors import AgentCallError


@dataclass(frozen=True, slots=True)
class InvocationResult[T]:
    value: T
    attempts: int


async def invoke_with_retry[T](
    operation: Callable[[int], Awaitable[T]],
    policy: AgentPolicy,
    deadline_at: datetime | None,
    *,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    on_retry: Callable[[AgentCallError, int], None] | None = None,
) -> InvocationResult[T]:
    last_error: AgentCallError | None = None
    for attempt in range(1, policy.max_attempts + 1):
        timeout_seconds = _effective_timeout(policy.timeout_seconds, deadline_at)
        if timeout_seconds <= 0:
            raise AgentCallError(
                ErrorCode.DEADLINE_EXCEEDED,
                "workflow deadline exceeded",
                retryable=False,
                attempts=attempt,
            )

        try:
            async with asyncio.timeout(timeout_seconds):
                return InvocationResult(await operation(attempt), attempt)
        except TimeoutError:
            last_error = AgentCallError(
                ErrorCode.DEADLINE_EXCEEDED,
                "agent call timed out",
                retryable=True,
                attempts=attempt,
            )
        except AgentCallError as error:
            last_error = error.after_attempt(attempt)

        if not last_error.retryable or attempt == policy.max_attempts:
            raise last_error

        if on_retry is not None:
            on_retry(last_error, attempt)

        delay = policy.backoff_seconds * (2 ** (attempt - 1))
        remaining = _remaining_seconds(deadline_at)
        if remaining is not None and delay >= remaining:
            raise AgentCallError(
                ErrorCode.DEADLINE_EXCEEDED,
                "workflow deadline exceeded before retry",
                retryable=False,
                attempts=attempt,
            )
        await sleep(delay)

    raise last_error or RuntimeError("retry loop exited without a result")


def _effective_timeout(configured: float, deadline_at: datetime | None) -> float:
    remaining = _remaining_seconds(deadline_at)
    return configured if remaining is None else min(configured, remaining)


def _remaining_seconds(deadline_at: datetime | None) -> float | None:
    if deadline_at is None:
        return None
    normalized = deadline_at.replace(tzinfo=UTC) if deadline_at.tzinfo is None else deadline_at
    return (normalized - datetime.now(UTC)).total_seconds()
