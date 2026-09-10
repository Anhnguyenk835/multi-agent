import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BackendSettings:
    database_url: str
    allowed_origins: tuple[str, ...]
    pool_min_size: int = 1
    pool_max_size: int = 5
    internal_api_token: str | None = None
    market_analyst_base_url: str = "http://market-analyst:8001"
    market_report_analyst_assistant_id: str = "market_report_analyst"
    review_action_timeout_seconds: int = 180

    @classmethod
    def from_environment(cls) -> "BackendSettings":
        origins = tuple(
            origin.strip()
            for origin in os.getenv("BACKEND_ALLOWED_ORIGINS", "http://localhost:5173").split(",")
            if origin.strip()
        )
        return cls(
            database_url=os.getenv(
                "BACKEND_DATABASE_URL",
                "postgresql://dashboard:dashboard@localhost:54321/dashboard",
            ),
            allowed_origins=origins,
            pool_min_size=int(os.getenv("BACKEND_DB_POOL_MIN_SIZE", "1")),
            pool_max_size=int(os.getenv("BACKEND_DB_POOL_MAX_SIZE", "5")),
            internal_api_token=os.getenv("BACKEND_INTERNAL_API_TOKEN") or None,
            market_analyst_base_url=os.getenv(
                "MARKET_ANALYST_BASE_URL", "http://market-analyst:8001"
            ).rstrip("/"),
            market_report_analyst_assistant_id=os.getenv(
                "MARKET_REPORT_ANALYST_ASSISTANT_ID", "market_report_analyst"
            ),
            review_action_timeout_seconds=max(
                30, int(os.getenv("REVIEW_ACTION_TIMEOUT_SECONDS", "180"))
            ),
        )
