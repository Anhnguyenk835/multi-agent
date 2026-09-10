import asyncio
import os
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from dotenv import load_dotenv

# Own .env per service, not a shared root file.
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

_DEFAULT_MODEL_ROUTE = "market-standard"
_DEFAULT_GATEWAY_BASE_URL = "http://llm-gateway:4000/v1"
_MODEL_ID_TRANSLATION = str.maketrans(
    {
        "\u2010": "-",
        "\u2011": "-",
        "\u2012": "-",
        "\u2013": "-",
        "\u2014": "-",
        "\u2212": "-",
    }
)


class FailureMode(StrEnum):
    NONE = "none"
    TIMEOUT = "timeout"
    TRANSIENT_ERROR = "transient_error"
    INVALID_RESPONSE = "invalid_response"


@dataclass(frozen=True)
class CompetitorAISettings:
    gateway_api_key: str | None = None
    gateway_base_url: str = _DEFAULT_GATEWAY_BASE_URL
    model_route: str = _DEFAULT_MODEL_ROUTE
    llm_timeout_seconds: float = 60.0
    gateway_max_provider_attempts: int = 4
    llm_max_output_tokens: int = 8_000

    @classmethod
    def from_environment(cls) -> "CompetitorAISettings":
        gateway_api_key = os.getenv("LLM_GATEWAY_API_KEY") or None
        gateway_base_url = os.getenv("LLM_GATEWAY_BASE_URL") or _DEFAULT_GATEWAY_BASE_URL

        return cls(
            gateway_api_key=gateway_api_key,
            gateway_base_url=gateway_base_url.rstrip("/"),
            model_route=_model_id_from_environment("LLM_MODEL_ROUTE", _DEFAULT_MODEL_ROUTE),
            llm_timeout_seconds=max(1.0, float(os.getenv("LLM_TIMEOUT_SECONDS", "60"))),
            gateway_max_provider_attempts=max(
                1,
                int(os.getenv("LLM_GATEWAY_MAX_PROVIDER_ATTEMPTS", "4")),
            ),
            llm_max_output_tokens=max(1, int(os.getenv("LLM_MAX_OUTPUT_TOKENS", "8000"))),
        )


@dataclass(frozen=True)
class CompetitorSearchSettings:
    exa_api_key: str | None = None
    exa_max_results: int = 4
    # Caps context window/rate-limit exposure across repeated search calls.
    exa_content_max_characters: int = 4_000

    @classmethod
    def from_environment(cls) -> "CompetitorSearchSettings":
        return cls(
            exa_api_key=os.getenv("EXA_API_KEY") or None,
            exa_max_results=max(1, int(os.getenv("EXA_MAX_RESULTS", "4"))),
            exa_content_max_characters=max(
                500, int(os.getenv("EXA_CONTENT_MAX_CHARACTERS", "4000"))
            ),
        )


@dataclass(frozen=True)
class CompetitorWorkflowSettings:
    max_competitors: int = 6
    discovery_search_calls: int = 3
    profile_search_calls: int = 3
    profile_concurrency: int = 3
    max_gap_fill_rounds: int = 1
    discovery_timeout_seconds: float = 45.0
    profile_timeout_seconds: float = 45.0
    synthesis_timeout_seconds: float = 45.0

    @classmethod
    def from_environment(cls) -> "CompetitorWorkflowSettings":
        return cls(
            max_competitors=max(2, int(os.getenv("COMPETITOR_MAX_PROFILES", "6"))),
            discovery_search_calls=max(1, int(os.getenv("DISCOVERY_SEARCH_CALLS", "3"))),
            profile_search_calls=max(1, int(os.getenv("PROFILE_SEARCH_CALLS", "3"))),
            profile_concurrency=max(1, int(os.getenv("PROFILE_CONCURRENCY", "3"))),
            max_gap_fill_rounds=max(0, int(os.getenv("MAX_GAP_FILL_ROUNDS", "1"))),
            discovery_timeout_seconds=max(1.0, float(os.getenv("DISCOVERY_TIMEOUT_SECONDS", "45"))),
            profile_timeout_seconds=max(1.0, float(os.getenv("PROFILE_TIMEOUT_SECONDS", "45"))),
            synthesis_timeout_seconds=max(1.0, float(os.getenv("SYNTHESIS_TIMEOUT_SECONDS", "45"))),
        )


@dataclass(frozen=True)
class DemoSettings:
    failure_mode: FailureMode = FailureMode.NONE
    failure_delay_ms: int = 1_500
    ai: CompetitorAISettings = field(default_factory=CompetitorAISettings)
    search: CompetitorSearchSettings = field(default_factory=CompetitorSearchSettings)
    workflow: CompetitorWorkflowSettings = field(default_factory=CompetitorWorkflowSettings)

    @classmethod
    def from_environment(cls) -> "DemoSettings":
        return cls(
            failure_mode=FailureMode(os.getenv("DEMO_FAILURE_MODE", FailureMode.NONE)),
            failure_delay_ms=int(os.getenv("DEMO_FAILURE_DELAY_MS", "1500")),
            ai=CompetitorAISettings.from_environment(),
            search=CompetitorSearchSettings.from_environment(),
            workflow=CompetitorWorkflowSettings.from_environment(),
        )

    async def apply_delay(self) -> None:
        if self.failure_mode is FailureMode.TIMEOUT:
            await asyncio.sleep(self.failure_delay_ms / 1_000)


def _model_id_from_environment(name: str, default: str) -> str:
    return (os.getenv(name) or default).strip().translate(_MODEL_ID_TRANSLATION).lower()
