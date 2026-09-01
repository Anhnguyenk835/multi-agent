import asyncio
import os
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from dotenv import load_dotenv

from market_agent.errors import ProviderConfigurationError

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


class AIMode(StrEnum):
    FIXTURE = "fixture"
    LIVE = "live"


class FailureMode(StrEnum):
    NONE = "none"
    TIMEOUT = "timeout"
    TRANSIENT_ERROR = "transient_error"
    INVALID_RESPONSE = "invalid_response"


@dataclass(frozen=True)
class MarketAISettings:
    ai_mode: AIMode = AIMode.FIXTURE
    gateway_api_key: str | None = None
    gateway_base_url: str = _DEFAULT_GATEWAY_BASE_URL
    model_route: str = _DEFAULT_MODEL_ROUTE
    llm_timeout_seconds: float = 60.0
    llm_max_output_tokens: int = 1_800

    @classmethod
    def from_environment(cls) -> "MarketAISettings":
        ai_mode = AIMode(os.getenv("AI_MODE", AIMode.FIXTURE.value))
        gateway_api_key = os.getenv("LLM_GATEWAY_API_KEY") or None
        gateway_base_url = os.getenv("LLM_GATEWAY_BASE_URL") or _DEFAULT_GATEWAY_BASE_URL

        if ai_mode is AIMode.LIVE and not gateway_api_key:
            raise ProviderConfigurationError("AI_MODE=live requires LLM_GATEWAY_API_KEY to be set")

        return cls(
            ai_mode=ai_mode,
            gateway_api_key=gateway_api_key,
            gateway_base_url=gateway_base_url.rstrip("/"),
            model_route=_model_id_from_environment("LLM_MODEL_ROUTE", _DEFAULT_MODEL_ROUTE),
            llm_timeout_seconds=max(1.0, float(os.getenv("LLM_TIMEOUT_SECONDS", "60"))),
            llm_max_output_tokens=max(1, int(os.getenv("LLM_MAX_OUTPUT_TOKENS", "1800"))),
        )


@dataclass(frozen=True)
class MarketExaSettings:
    exa_api_key: str | None = None
    exa_max_results: int = 4
    # Caps context window/rate-limit exposure across repeated search calls.
    exa_content_max_characters: int = 4_000

    @classmethod
    def from_environment(cls) -> "MarketExaSettings":
        return cls(
            exa_api_key=os.getenv("EXA_API_KEY") or None,
            exa_max_results=max(1, int(os.getenv("EXA_MAX_RESULTS", "4"))),
            exa_content_max_characters=max(
                500, int(os.getenv("EXA_CONTENT_MAX_CHARACTERS", "4000"))
            ),
        )


@dataclass(frozen=True)
class DemoSettings:
    failure_mode: FailureMode = FailureMode.NONE
    failure_delay_ms: int = 1_500
    ai: MarketAISettings = field(default_factory=MarketAISettings)
    exa: MarketExaSettings = field(default_factory=MarketExaSettings)

    @classmethod
    def from_environment(cls) -> "DemoSettings":
        return cls(
            failure_mode=FailureMode(os.getenv("DEMO_FAILURE_MODE", FailureMode.NONE)),
            failure_delay_ms=int(os.getenv("DEMO_FAILURE_DELAY_MS", "1500")),
            ai=MarketAISettings.from_environment(),
            exa=MarketExaSettings.from_environment(),
        )

    async def apply_delay(self) -> None:
        if self.failure_mode is FailureMode.TIMEOUT:
            await asyncio.sleep(self.failure_delay_ms / 1_000)


def _model_id_from_environment(name: str, default: str) -> str:
    return (os.getenv(name) or default).strip().translate(_MODEL_ID_TRANSLATION).lower()
