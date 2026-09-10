import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")


@dataclass(frozen=True, slots=True)
class AgentPolicy:
    timeout_seconds: float
    max_attempts: int
    backoff_seconds: float


@dataclass(frozen=True, slots=True)
class OrchestratorSettings:
    market_analyst_url: str = "http://localhost:8001"
    competitor_analyst_address: str = "localhost:50051"
    # Cloud Run always terminates TLS at its ingress; only plaintext Docker
    # Compose networking can use an insecure channel.
    competitor_analyst_use_tls: bool = False
    analyst_url: str = "http://localhost:8002"
    writer_url: str = "http://localhost:8003"
    checkpoint_database_url: str = (
        "postgresql://distributed_agents:distributed_agents@localhost:5434/"
        "distributed_agents?sslmode=disable"
    )
    # Must stay above each service's own LLM_TIMEOUT_SECONDS, or the
    # orchestrator cancels the call before the service can finish.
    market_analyst_policy: AgentPolicy = AgentPolicy(90.0, 1, 0.5)
    # Covers discovery + two profile waves + one gap-fill pass + synthesis.
    competitor_analyst_policy: AgentPolicy = AgentPolicy(300.0, 1, 0.5)
    analyst_policy: AgentPolicy = AgentPolicy(90.0, 1, 0.5)
    writer_policy: AgentPolicy = AgentPolicy(90.0, 1, 0.5)

    @classmethod
    def from_environment(cls) -> "OrchestratorSettings":
        defaults = cls()
        return cls(
            market_analyst_url=os.getenv("MARKET_ANALYST_URL", defaults.market_analyst_url),
            competitor_analyst_address=os.getenv(
                "COMPETITOR_ANALYST_ADDRESS",
                defaults.competitor_analyst_address,
            ),
            competitor_analyst_use_tls=os.getenv(
                "COMPETITOR_ANALYST_USE_TLS", str(defaults.competitor_analyst_use_tls)
            ).lower()
            == "true",
            analyst_url=os.getenv("ANALYST_URL", defaults.analyst_url),
            writer_url=os.getenv("WRITER_URL", defaults.writer_url),
            checkpoint_database_url=os.getenv(
                "CHECKPOINT_DATABASE_URL",
                defaults.checkpoint_database_url,
            ),
            market_analyst_policy=_policy_from_environment(
                "MARKET_ANALYST", defaults.market_analyst_policy
            ),
            competitor_analyst_policy=_policy_from_environment(
                "COMPETITOR_ANALYST", defaults.competitor_analyst_policy
            ),
            analyst_policy=_policy_from_environment("ANALYST", defaults.analyst_policy),
            writer_policy=_policy_from_environment("WRITER", defaults.writer_policy),
        )


def _policy_from_environment(prefix: str, default: AgentPolicy) -> AgentPolicy:
    return AgentPolicy(
        timeout_seconds=max(
            0.001,
            float(os.getenv(f"{prefix}_TIMEOUT_SECONDS", str(default.timeout_seconds))),
        ),
        max_attempts=max(
            1,
            int(os.getenv(f"{prefix}_MAX_ATTEMPTS", str(default.max_attempts))),
        ),
        backoff_seconds=max(
            0,
            float(os.getenv(f"{prefix}_BACKOFF_SECONDS", str(default.backoff_seconds))),
        ),
    )
