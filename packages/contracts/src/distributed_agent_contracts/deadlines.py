from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True, slots=True)
class ModelTimeoutBudget:
    provider_attempt_seconds: float
    client_seconds: float


def remaining_seconds(
    deadline_at: datetime | None,
    *,
    now: datetime | None = None,
) -> float | None:
    if deadline_at is None:
        return None
    normalized = deadline_at.replace(tzinfo=UTC) if deadline_at.tzinfo is None else deadline_at
    return (normalized - (now or datetime.now(UTC))).total_seconds()


def model_timeout_budget(
    deadline_at: datetime | None,
    *,
    configured_seconds: float,
    provider_attempts: int,
) -> ModelTimeoutBudget:
    remaining = remaining_seconds(deadline_at)
    if remaining is None:
        return ModelTimeoutBudget(configured_seconds, configured_seconds)

    provider_seconds = (remaining - 2.0) / max(1, provider_attempts)
    return ModelTimeoutBudget(
        min(configured_seconds, provider_seconds),
        remaining - 1.0,
    )
