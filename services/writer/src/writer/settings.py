import asyncio
import os
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from dotenv import load_dotenv

# Own .env per service, not a shared root file.
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

_DEFAULT_MODEL_ROUTE = "brief-streaming"
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


@dataclass(frozen=True, slots=True)
class WriterAISettings:
    gateway_api_key: str | None = None
    gateway_base_url: str = _DEFAULT_GATEWAY_BASE_URL
    model_route: str = _DEFAULT_MODEL_ROUTE
    llm_timeout_seconds: float = 30.0
    gateway_max_provider_attempts: int = 4
    llm_max_output_tokens: int = 3_000

    @classmethod
    def from_environment(cls) -> "WriterAISettings":
        gateway_api_key = os.getenv("LLM_GATEWAY_API_KEY") or None
        gateway_base_url = os.getenv("LLM_GATEWAY_BASE_URL") or _DEFAULT_GATEWAY_BASE_URL

        return cls(
            gateway_api_key=gateway_api_key,
            gateway_base_url=gateway_base_url.rstrip("/"),
            model_route=_model_id_from_environment("LLM_MODEL_ROUTE", _DEFAULT_MODEL_ROUTE),
            llm_timeout_seconds=max(1.0, float(os.getenv("LLM_TIMEOUT_SECONDS", "30"))),
            gateway_max_provider_attempts=max(
                1,
                int(os.getenv("LLM_GATEWAY_MAX_PROVIDER_ATTEMPTS", "4")),
            ),
            llm_max_output_tokens=max(1, int(os.getenv("LLM_MAX_OUTPUT_TOKENS", "3000"))),
        )


@dataclass(frozen=True, slots=True)
class DemoSettings:
    failure_mode: FailureMode = FailureMode.NONE
    delay_seconds: float = 0.25
    ai: WriterAISettings = field(default_factory=WriterAISettings)

    @classmethod
    def from_environment(cls) -> "DemoSettings":
        failure_mode = FailureMode(os.getenv("DEMO_FAILURE_MODE", FailureMode.NONE))
        delay_ms = max(0, int(os.getenv("DEMO_FAILURE_DELAY_MS", "250")))
        return cls(
            failure_mode=failure_mode,
            delay_seconds=delay_ms / 1_000,
            ai=WriterAISettings.from_environment(),
        )

    async def apply_delay(self) -> None:
        if self.failure_mode is FailureMode.TIMEOUT:
            await asyncio.sleep(self.delay_seconds)


def _model_id_from_environment(name: str, default: str) -> str:
    return (os.getenv(name) or default).strip().translate(_MODEL_ID_TRANSLATION).lower()
